# Geolocation and expected yield

## The product

A Geomap panel plots a series that carries a location. The location and the "what should have been produced" number are not things the inverter reports. A second exporter computes them and Alloy scrapes it as its own job, so the device alerts stay about the device. The model is a forecast, not a measurement. Treat the ratio as a direction.

## This stack

[geolocate/](https://github.com/lewismc/solaredge-olly/tree/main/geolocate) is a small Python exporter on `:9110`. Alloy scrapes it as job `integrations/solaredge-geolocate` and keeps `up` and `Site_*`. The inverter alerts and SLOs on `integrations/solaredge` do not change.

Set `SITE_LAT` and `SITE_LON` to use a fixed location. The exporter then makes no IP lookup. Leave both empty and it looks up the public IP at ipinfo.io once a day, cached so a restart inside a day does not call again. `location_source` on `Site_Location_Info` is `Public IP lookup` or `Set coordinates`. A failed lookup keeps the cached location and retries in an hour. With no location at all, there are no irradiance or expected-power series.

The public IP is sent to ipinfo.io for that lookup and is never a label or a metric. Coordinates keep 4 decimal places (about 11 m), which is the precision ipinfo returns. Rounding to 2 decimals moves the point by up to about 700 m. City, region, and country from ipinfo are also stored as labels. Set both coordinates to avoid the lookup and those labels. The lookup is only accurate to the neighbourhood the address appears to be in.

Open-Meteo gives plane-of-array irradiance (`GTI`) at `PV_TILT` degrees from horizontal and `PV_AZIMUTH` (0 is south, -90 east, 90 west). Expected AC power is `min(GTI × PV_KWP × PV_PR, PV_AC_LIMIT_W)` in watts. The defaults are 25 degrees, south, 4.56 kWp (3.8 kWp × 1.2), PR 0.8, and a 3800 W limit. The model ignores shading, soiling, and temperature, and it clips at the AC limit. Expected power is for the whole site, so read the ratio with all inverters selected.

The Site tab of the dashboard shows actual against expected, a performance-ratio gauge while the sun is up and GTI is above 50 W/m², irradiance, a Geomap, and the PV assumptions. The underperformance alert, on [Alerts](https://github.com/lewismc/solaredge-olly/wiki/Alerts), fires below 0.25 for an hour while GTI is above 200. There is no SLO on expected yield.

The host needs outbound HTTPS to `ipinfo.io` and `api.open-meteo.com`. Open-Meteo data is CC BY 4.0.

**When the marker is wrong.** A VPN, a proxy, or iCloud Private Relay makes ipinfo see another address. Set both coordinates. **When `Site_*` irradiance is missing.** `Site_PV_Config_Info` is always exported. The other series wait for a location and a successful fetch. The exporter logs each failed request.

## Reuse on a customer system

Keep a derived "expected" series on its own job so it cannot trip the device SLO. Never put a public IP in a label. Prefer coordinates the customer sets over a geo-IP guess, and say so on the panel. Publish the model's blind spots next to the number. A ratio threshold belongs below the measured distribution, not at the textbook value of 1.
