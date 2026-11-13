#!/bin/bash
# Pull the latest public GitHub release and roll it out.
# /etc/solaredge/solaredge.env is never read or written.
# A failed health check puts the previous binaries back.
set -euo pipefail

ROOT=/opt/solaredge
BIN=$ROOT/bin
REL=$ROOT/releases
CURRENT_FILE=$ROOT/current-release
REPO=lewismc/solaredge-olly
HEALTH_SECONDS="${SOLAREDGE_HEALTH_SECONDS:-300}"
RSS_LIMIT_KB=$((220 * 1024))

STAGE=""
if [ "${1:-}" = "--stage" ]; then
  STAGE="${2:?--stage needs a directory}"
fi

log() { echo "$(date -Is) $*"; }

current_tag() {
  if [ -f "$CURRENT_FILE" ]; then
    tr -d '[:space:]' < "$CURRENT_FILE"
  else
    echo ""
  fi
}

health_check() {
  local start deadline restarts now rss pid ready
  start=$(date +%s)
  deadline=$((start + HEALTH_SECONDS))
  restarts=$(systemctl show -p NRestarts --value alloy.service)
  ready=0
  while [ "$(date +%s)" -lt "$deadline" ]; do
    systemctl is-active --quiet alloy.service || return 1
    now=$(systemctl show -p NRestarts --value alloy.service)
    [ "$now" = "$restarts" ] || return 1
    if journalctl -u alloy.service --since "@${start}" --no-pager | grep -E -q 'panic:|fatal error'; then
      return 1
    fi
    pid=$(systemctl show -p MainPID --value alloy.service)
    rss=$(ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ' || true)
    if [ -n "${rss:-}" ] && [ "$rss" -gt "$RSS_LIMIT_KB" ]; then
      return 1
    fi
    if curl -sf --max-time 3 http://127.0.0.1:12345/-/ready >/dev/null; then
      ready=1
    fi
    sleep 15
  done
  [ "$ready" = 1 ]
}

install_configs() {
  local src="$1"
  [ -f "$src/alloy/config.alloy" ] || return 0
  install -m 0644 "$src/alloy/config.alloy" /etc/alloy/config.alloy
  install -m 0644 "$src/fleet/solaredge.alloy" /etc/alloy/solaredge.alloy
  install -m 0644 "$src/module/metrics.alloy" /etc/alloy/module/metrics.alloy
  if [ -f "$src/geolocate/server.py" ]; then
    install -m 0644 -o geolocate -g geolocate "$src/geolocate/server.py" /opt/solaredge/geolocate/server.py
    systemctl try-restart solaredge-geolocate.service || true
  fi
  if [ -f "$src/sunspec-sim/server.py" ]; then
    install -m 0644 -o sunspec -g sunspec "$src/sunspec-sim/server.py" /opt/solaredge/sim/server.py
  fi
}

exporter_sha() {
  if [ -e "$BIN/solaredge-exporter" ]; then
    sha256sum "$BIN/solaredge-exporter" | awk '{print $1}'
  else
    echo none
  fi
}

point_at() {
  local tag="$1"
  ln -sfn "$REL/$tag/alloy" "$BIN/alloy"
  if [ -f "$REL/$tag/solaredge-exporter" ]; then
    ln -sfn "$REL/$tag/solaredge-exporter" "$BIN/solaredge-exporter"
  fi
}

mkdir -p "$REL" "$BIN"
prev=$(current_tag)

if [ -n "$STAGE" ]; then
  tag="stage-$(date +%s)"
  mkdir -p "$REL/$tag"
  install -m 0755 "$STAGE/alloy" "$REL/$tag/alloy"
  if [ -f "$STAGE/solaredge-exporter" ]; then
    install -m 0755 "$STAGE/solaredge-exporter" "$REL/$tag/solaredge-exporter"
  fi
else
  meta=$(mktemp)
  code=$(curl -sS -o "$meta" -w '%{http_code}' "https://api.github.com/repos/${REPO}/releases/latest")
  if [ "$code" = "404" ]; then
    log "no release published yet"
    rm -f "$meta"
    exit 0
  fi
  if [ "$code" != "200" ]; then
    log "GitHub API returned $code"
    rm -f "$meta"
    exit 1
  fi
  tag=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag_name"])' "$meta")
  if [ "$tag" = "$prev" ]; then
    log "already on $tag"
    rm -f "$meta"
    exit 0
  fi
  work=$(mktemp -d)
  python3 - "$meta" "$work/urls" << 'PY'
import json, sys
release = json.load(open(sys.argv[1]))
wanted = {
    "alloy-linux-armv6",
    "solaredge-exporter-linux-armv6",
    "solaredge-bundle.tar.gz",
    "SHA256SUMS",
}
with open(sys.argv[2], "w") as out:
    for asset in release["assets"]:
        if asset["name"] in wanted:
            out.write(asset["browser_download_url"] + "\n")
PY
  while read -r url; do
    [ -n "$url" ] || continue
    name=${url##*/}
    curl -fsSL -o "$work/$name" "$url"
  done < "$work/urls"
  (cd "$work" && sha256sum -c SHA256SUMS)
  mkdir -p "$REL/$tag"
  install -m 0755 "$work/alloy-linux-armv6" "$REL/$tag/alloy"
  install -m 0755 "$work/solaredge-exporter-linux-armv6" "$REL/$tag/solaredge-exporter"
  tar -C "$work" -xzf "$work/solaredge-bundle.tar.gz"
  install_configs "$work"
  rm -rf "$work" "$meta"
fi

before_exporter=$(exporter_sha)
point_at "$tag"
systemctl restart alloy.service
exporter_restarted=0
after_exporter=$(exporter_sha)
if [ "$before_exporter" != "$after_exporter" ]; then
  systemctl restart solaredge-exporter.service
  exporter_restarted=1
fi

if health_check; then
  printf '%s\n' "$tag" > "$CURRENT_FILE"
  log "installed $tag"
  # Keep the release just installed and the one it replaced.
  if [ -n "$prev" ] && [ -d "$REL/$prev" ]; then
    find "$REL" -mindepth 1 -maxdepth 1 -type d ! -name "$tag" ! -name "$prev" -exec rm -rf {} +
  fi
  exit 0
fi

log "health check failed for $tag, rolling back to ${prev:-none}"
if [ -n "$prev" ] && [ -d "$REL/$prev" ]; then
  point_at "$prev"
  systemctl restart alloy.service
  if [ "$exporter_restarted" = 1 ]; then
    systemctl restart solaredge-exporter.service
  fi
fi
rm -rf "$REL/$tag"
exit 1
