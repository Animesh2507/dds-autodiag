#!/usr/bin/env bash
# Bring the isolated lab up, collect snapshots, compare, and inspect live topics.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-/tmp/autodiag-lab}
AD=${AD:-}
mkdir -p "$OUT"

if [[ -z "$AD" ]]; then
  if command -v dds-autodiag >/dev/null; then
    AD=$(command -v dds-autodiag)
  else
    AD="$HERE/../../.venv/bin/dds-autodiag"
  fi
fi

cd "$HERE"
echo "== build image once, then start lab (domain 87, Cyclone + Fast DDS + Zenoh) =="
docker compose -f compose.yml build
docker compose -f compose.yml up -d --no-build

echo "== wait for /lab topics =="
SRC='source /opt/ros/jazzy/setup.bash'
for i in $(seq 1 30); do
  if docker exec autodiag-lab-collector bash -lc "$SRC && ros2 topic list --no-daemon" 2>/dev/null | grep -q '/lab/scan'; then
    break
  fi
  sleep 1
done

echo "== collect snapshots from each container =="
for name in robot laptop isolated shm-twin zenoh collector; do
  docker exec "autodiag-lab-$name" bash -lc "$SRC && dds-autodiag collect -o /tmp/$name.json"
  docker cp "autodiag-lab-$name:/tmp/$name.json" "$OUT/$name.json"
  echo "  wrote $OUT/$name.json"
done

echo "== live inspect from the Cyclone collector =="
docker exec autodiag-lab-collector bash -lc "$SRC && dds-autodiag topics" || true
docker exec autodiag-lab-collector bash -lc "$SRC && dds-autodiag inspect /lab/scan" || true
docker exec autodiag-lab-collector bash -lc "$SRC && dds-autodiag inspect /lab/map" || true

echo "== compare: cyclone robot vs Fast DDS laptop =="
"$AD" compare "$OUT/robot.json" "$OUT/laptop.json" || true

echo "== compare: robot vs isolated (domain 87 vs 91) =="
"$AD" compare "$OUT/robot.json" "$OUT/isolated.json" || true

echo "== compare: robot vs shm-twin (same host name, different IPC, expect SHM) =="
"$AD" compare "$OUT/robot.json" "$OUT/shm-twin.json" --transport dds_shm || true

echo "== compare: laptop vs zenoh (DDS vs Zenoh — expect RMW_MISMATCH error) =="
"$AD" compare "$OUT/laptop.json" "$OUT/zenoh.json" || true

echo "== single-host check of laptop (wrong RMW + missing Cyclone XML) =="
"$AD" check --snapshot "$OUT/laptop.json" || true

echo "== single-host check of isolated (missing XML + LOCALHOST discovery) =="
"$AD" check --snapshot "$OUT/isolated.json" || true

echo "== live collector HTTP =="
curl -sS -o /dev/null -w "healthz %{http_code}\n" http://127.0.0.1:18087/api/healthz
curl -sS -H "X-Autodiag-Token: lab-collector-token" http://127.0.0.1:18087/api/agent/snapshot | python3 -c \
  'import json,sys; s=json.load(sys.stdin); e=s["environment"]; c=s["container"]; print("collector env", {k:e.get(k) for k in ("ROS_DOMAIN_ID","RMW_IMPLEMENTATION","ROS_DISTRO")}); print("container", c.get("detected"), "ipc", c.get("ipc_namespace")); print("keys", sorted(s))'

echo "== snapshots in $OUT =="
ls -l "$OUT"
echo "Collector token: lab-collector-token"
echo "Dashboards: collector 18087 · Fast DDS laptop 18088 · robot 18089 · stack 18090"
echo "            isolated 18091 · shm-twin 18092 · zenoh 18093"
echo "Host UI (this PC): http://127.0.0.1:8080  — connect a lab URL under Hosts"
echo "Stop with: docker compose -f $HERE/compose.yml down"
