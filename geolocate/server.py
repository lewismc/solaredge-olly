#!/usr/bin/env python3
"""Site geolocation and expected-yield exporter for solaredge-olly.

Resolves the site location, fetches tilted irradiance for that location from
Open-Meteo every 15 minutes, and exposes the result on :9110 for Alloy to scrape.

Location source, in order:
  1. SITE_LAT and SITE_LON from the environment (location_source="Set coordinates").
     No IP lookup.
  2. A daily ipinfo.io lookup of the public IP (location_source="Public IP lookup"),
     cached on disk so a restart within 24 hours does not call ipinfo again.

Coordinates keep 4 decimal places, matching the precision ipinfo returns. Rounding
to 2 decimals moves the point by up to about 700 m. Without a location, no Site_*
gauges are exported except the PV configuration and the timestamps.
"""

import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import requests
from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import GaugeMetricFamily

IPINFO_URL = "https://ipinfo.io/json"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

LISTEN_PORT = int(os.environ.get("GEOLOCATE_PORT", "9110"))
LISTEN_ADDR = os.environ.get("GEOLOCATE_LISTEN_ADDR", "0.0.0.0")
CACHE_PATH = os.environ.get("GEOLOCATE_CACHE", "/var/lib/geolocate/location.json")

LOCATION_TTL_S = 24 * 3600      # ipinfo lookup at most once per day
LOCATION_RETRY_S = 3600         # after a failed lookup, try again in an hour
IRRADIANCE_OK_S = 900           # Open-Meteo current values every 15 minutes
IRRADIANCE_RETRY_S = 300        # after a failed fetch, try again in 5 minutes
LOOP_TICK_S = 15
HTTP_TIMEOUT_S = 15
COORD_PLACES = 4
SOURCE_IP = "Public IP lookup"
SOURCE_SET = "Set coordinates"


def log(level, msg, **fields):
    record = {"ts": datetime.now(timezone.utc).isoformat(), "level": level, "msg": msg}
    record.update(fields)
    print(json.dumps(record), flush=True)


def env_float(name, default, lo=None, hi=None):
    raw = os.environ.get(name, "").strip()
    value = float(raw) if raw else float(default)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise SystemExit(f"{name}={value} is outside [{lo}, {hi}]")
    return value


def round_coord(value):
    return round(float(value), COORD_PLACES)


def fmt_coord(value):
    return f"{value:.{COORD_PLACES}f}"


def expected_ac_power_w(gti_wm2, kwp, pr, ac_limit_w):
    """Expected AC watts from plane-of-array irradiance.

    At 1000 W/m2 a kWp array produces kWp kW, so DC watts = kWp * GTI. Multiply by
    the performance ratio and clip at the inverter's AC limit.
    """
    dc_w = max(gti_wm2, 0.0) * kwp
    return min(dc_w * pr, ac_limit_w)


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.location = None          # dict with lat, lon, city, region, country, source
        self.location_ip = None       # public IP, kept only for change detection (never exported)
        self.geolocate_ts = None
        self.irradiance_ts = None
        self.gti = None
        self.ghi = None
        self.is_day = None
        self.expected_w = None
        self.next_location_at = 0.0
        self.next_irradiance_at = 0.0


class SiteCollector:
    def __init__(self, state, pv):
        self.state = state
        self.pv = pv

    def collect(self):
        s = self.state
        with s.lock:
            loc = dict(s.location) if s.location else None
            snapshot = {
                "geolocate_ts": s.geolocate_ts,
                "irradiance_ts": s.irradiance_ts,
                "gti": s.gti,
                "ghi": s.ghi,
                "is_day": s.is_day,
                "expected_w": s.expected_w,
            }

        pv = self.pv
        cfg = GaugeMetricFamily(
            "Site_PV_Config_Info",
            "PV assumptions used for expected power. Value is always 1.",
            labels=["tilt", "azimuth", "kwp", "pr"],
        )
        cfg.add_metric([fmt_num(pv["tilt"]), fmt_num(pv["azimuth"]), fmt_num(pv["kwp"]), fmt_num(pv["pr"])], 1)
        yield cfg

        if loc:
            info = GaugeMetricFamily(
                "Site_Location_Info",
                "Resolved site location. Value is always 1.",
                labels=["lat", "lon", "city", "region", "country", "location_source"],
            )
            info.add_metric(
                [
                    fmt_coord(loc["lat"]),
                    fmt_coord(loc["lon"]),
                    loc.get("city", ""),
                    loc.get("region", ""),
                    loc.get("country", ""),
                    loc["source"],
                ],
                1,
            )
            yield info

        if snapshot["geolocate_ts"] is not None:
            yield GaugeMetricFamily(
                "Site_Geolocate_Last_Success_Timestamp_Seconds",
                "Unix time the site location was last resolved.",
                value=snapshot["geolocate_ts"],
            )
        if snapshot["irradiance_ts"] is not None:
            yield GaugeMetricFamily(
                "Site_Irradiance_Last_Success_Timestamp_Seconds",
                "Unix time Open-Meteo irradiance was last fetched successfully.",
                value=snapshot["irradiance_ts"],
            )
        if snapshot["gti"] is not None:
            yield GaugeMetricFamily(
                "Site_Irradiance_GTI_Wm2",
                "Global tilted (plane-of-array) irradiance at the configured tilt and azimuth.",
                value=snapshot["gti"],
            )
        if snapshot["ghi"] is not None:
            yield GaugeMetricFamily(
                "Site_Irradiance_GHI_Wm2",
                "Global horizontal shortwave irradiance.",
                value=snapshot["ghi"],
            )
        if snapshot["is_day"] is not None:
            yield GaugeMetricFamily(
                "Site_Sun_Is_Day",
                "1 when the sun is above the horizon at the site (Open-Meteo is_day).",
                value=snapshot["is_day"],
            )
        if snapshot["expected_w"] is not None:
            yield GaugeMetricFamily(
                "Site_Expected_AC_Power_W",
                "Expected AC power from irradiance, PV size, performance ratio, and the AC limit.",
                value=snapshot["expected_w"],
            )


def fmt_num(value):
    return f"{value:g}"


def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save_cache(record):
    tmp = CACHE_PATH + ".tmp"
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        os.replace(tmp, CACHE_PATH)
    except OSError as exc:
        log("warn", "could not write location cache", error=str(exc))


def apply_location(state, loc, ip, now):
    """Store a new location. Reset the irradiance timer so the next fetch is immediate."""
    with state.lock:
        changed = state.location is None or (
            state.location["lat"] != loc["lat"] or state.location["lon"] != loc["lon"]
        )
        state.location = loc
        state.location_ip = ip
        state.geolocate_ts = now
        if changed:
            state.next_irradiance_at = 0.0


def resolve_manual(state, lat_raw, lon_raw, now):
    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except ValueError:
        log("error", "SITE_LAT and SITE_LON must be numbers")
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        log("error", "SITE_LAT or SITE_LON is out of range")
        return False
    loc = {"lat": round_coord(lat), "lon": round_coord(lon), "city": "", "region": "", "country": "", "source": SOURCE_SET}
    apply_location(state, loc, None, now)
    log("info", "site location set from environment", location_source=SOURCE_SET)
    return True


def fetch_ipinfo():
    resp = requests.get(IPINFO_URL, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()
    loc_raw = data.get("loc")
    if not loc_raw or "," not in loc_raw:
        raise ValueError("ipinfo response has no loc field (private or reserved address?)")
    lat_s, lon_s = loc_raw.split(",", 1)
    return {
        "ip": data.get("ip", ""),
        "lat": round_coord(lat_s),
        "lon": round_coord(lon_s),
        "city": data.get("city", ""),
        "region": data.get("region", ""),
        "country": data.get("country", ""),
    }


def refresh_location(state, now):
    """Call ipinfo, update the cache, and fall back to the cache when the lookup fails."""
    prev_ip = state.location_ip
    try:
        found = fetch_ipinfo()
    except Exception as exc:  # network, HTTP, or parse error
        log("warn", "ipinfo lookup failed", error=str(exc))
        with state.lock:
            have_location = state.location is not None
            state.next_location_at = now + LOCATION_RETRY_S
        if not have_location:
            cached = load_cache()
            if cached:
                loc = {k: cached[k] for k in ("lat", "lon", "city", "region", "country")}
                loc["source"] = SOURCE_IP
                apply_location(state, loc, cached.get("ip"), cached.get("fetched_at", now))
                log("info", "using cached site location after failed lookup", location_source=SOURCE_IP)
        return

    if prev_ip is not None and prev_ip != found["ip"]:
        log("info", "public IP changed; site location refreshed")
    loc = {k: found[k] for k in ("lat", "lon", "city", "region", "country")}
    loc["source"] = SOURCE_IP
    apply_location(state, loc, found["ip"], now)
    save_cache({**loc, "ip": found["ip"], "fetched_at": now, "places": COORD_PLACES})
    with state.lock:
        state.next_location_at = now + LOCATION_TTL_S
    log("info", "site location resolved from public IP", location_source=SOURCE_IP)


def refresh_irradiance(state, pv, now):
    with state.lock:
        loc = dict(state.location)
    try:
        resp = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "current": "global_tilted_irradiance,shortwave_radiation,is_day",
                "tilt": pv["tilt"],
                "azimuth": pv["azimuth"],
                "timezone": "UTC",
            },
            timeout=HTTP_TIMEOUT_S,
        )
        resp.raise_for_status()
        cur = resp.json()["current"]
        gti = float(cur["global_tilted_irradiance"])
        ghi = float(cur["shortwave_radiation"])
        is_day = int(cur["is_day"])
    except Exception as exc:
        log("warn", "Open-Meteo fetch failed; keeping last good values", error=str(exc))
        with state.lock:
            state.next_irradiance_at = now + IRRADIANCE_RETRY_S
        return

    expected = expected_ac_power_w(gti, pv["kwp"], pv["pr"], pv["ac_limit_w"])
    with state.lock:
        state.gti = gti
        state.ghi = ghi
        state.is_day = is_day
        state.expected_w = expected
        state.irradiance_ts = now
        state.next_irradiance_at = now + IRRADIANCE_OK_S
    log("info", "irradiance updated", gti_wm2=gti, expected_ac_w=round(expected, 1))


def load_pv_config():
    pv = {
        "tilt": env_float("PV_TILT", 25, 0, 90),
        "azimuth": env_float("PV_AZIMUTH", 0, -180, 180),
        "kwp": env_float("PV_KWP", 4.56, 0.001, 1000),
        "pr": env_float("PV_PR", 0.8, 0.01, 1.0),
        "ac_limit_w": env_float("PV_AC_LIMIT_W", 3800, 1, 1e6),
    }
    return pv


def startup_location(state):
    """Use the environment override or the cache at startup. Refresh if the cache is stale."""
    now = time.time()
    lat_raw = os.environ.get("SITE_LAT", "").strip()
    lon_raw = os.environ.get("SITE_LON", "").strip()

    if lat_raw or lon_raw:
        if not (lat_raw and lon_raw):
            raise SystemExit("set both SITE_LAT and SITE_LON, or neither")
        if not resolve_manual(state, lat_raw, lon_raw, now):
            raise SystemExit("SITE_LAT and SITE_LON are invalid")
        with state.lock:
            state.next_location_at = float("inf")  # manual location never calls ipinfo
        return

    cached = load_cache()
    if cached and "fetched_at" in cached:
        loc = {k: cached[k] for k in ("lat", "lon", "city", "region", "country")}
        loc["source"] = SOURCE_IP
        apply_location(state, loc, cached.get("ip"), cached["fetched_at"])
        age = now - cached["fetched_at"]
        # A cache written at coarser precision (the old 2-decimal rounding) is
        # refreshed immediately. places is absent on those files.
        stale_precision = cached.get("places", 2) < COORD_PLACES
        with state.lock:
            state.next_location_at = now if stale_precision or age >= LOCATION_TTL_S else cached["fetched_at"] + LOCATION_TTL_S
        log("info", "loaded cached site location", location_source=SOURCE_IP, age_s=round(age))
    else:
        with state.lock:
            state.next_location_at = now


def run_loop(state, pv, stop):
    while not stop.is_set():
        now = time.time()
        with state.lock:
            due_location = now >= state.next_location_at and state.next_location_at != float("inf")
            due_irradiance = state.location is not None and now >= state.next_irradiance_at
        if due_location:
            refresh_location(state, now)
            with state.lock:
                due_irradiance = state.location is not None and now >= state.next_irradiance_at
        if due_irradiance:
            refresh_irradiance(state, pv, now)
        stop.wait(LOOP_TICK_S)


def main():
    pv = load_pv_config()
    state = State()
    startup_location(state)

    REGISTRY.register(SiteCollector(state, pv))
    start_http_server(LISTEN_PORT, addr=LISTEN_ADDR)
    log("info", "geolocate exporter listening", addr=LISTEN_ADDR, port=LISTEN_PORT, tilt=pv["tilt"], azimuth=pv["azimuth"],
        kwp=pv["kwp"], pr=pv["pr"], ac_limit_w=pv["ac_limit_w"])

    stop = threading.Event()

    def handle_signal(signum, _frame):
        log("info", "stopping", signal=signum)
        stop.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    run_loop(state, pv, stop)
    sys.exit(0)


if __name__ == "__main__":
    main()
