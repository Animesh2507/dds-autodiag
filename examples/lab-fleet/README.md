# Isolated lab fleet

A multi-container ROS 2 Jazzy lab for exercising AutoDiag: Cyclone, Fast DDS and Zenoh, plus deliberate QoS and
domain faults. Host networking; **domain 87** so the lab does not join the host graph on domain 0.

```bash
./run-lab.sh
# or: docker compose -f compose.yml up -d --build
```

Collector token for every lab `serve`: `lab-collector-token`.

| Container | URL | RMW | Domain | Role |
|---|---|---|---|---|
| collector | http://127.0.0.1:18087 | Cyclone | 87 | Extra Cyclone collector |
| laptop | http://127.0.0.1:18088 | Fast DDS | 87 | Wrong RMW vs the Cyclone robot |
| robot | http://127.0.0.1:18089 | Cyclone | 87 | Sensors (`/lab/scan`, `/lab/map`, …) |
| stack | http://127.0.0.1:18090 | Cyclone | 87 | Subscribers (QoS / type faults) |
| isolated | http://127.0.0.1:18091 | Cyclone | 91 | LOCALHOST — should not see the fleet |
| shm-twin | http://127.0.0.1:18092 | Cyclone | 87 | Same hostname as robot, different IPC |
| zenoh | http://127.0.0.1:18093 | Zenoh | 87 | Own router; never discovers DDS topics |

Your **laptop dashboard** (`dds-autodiag serve --open`, usually http://127.0.0.1:8080) is a separate process on
domain 0 / Fast DDS. That UI is “this host”. Connect a lab URL under Hosts to make it the peer.

## What to expect

- Laptop (8080) vs robot (18089): `DOMAIN_MISMATCH` (0 vs 87) and `RMW_MISMATCH` (Fast DDS vs Cyclone, warning).
- Robot vs stack: same domain and RMW — they share `/lab/…`. Graph on 18089 shows reliability, type and latched-map faults.
- Isolated (18091): domain 91 and LOCALHOST.
- Robot vs shm-twin, Transport = DDS shared memory: `SHM_IPC_NAMESPACE_DIFFERENCE`.
- Laptop vs zenoh (18093): `RMW_MISMATCH` as an **error** (Zenoh cannot talk to DDS). Topics on 18093 show `/lab/zenoh`, not `/lab/scan`.

The Docker table on a lab collector cannot list the host PC (no Docker CLI in the image). Stay on the laptop UI to
scan containers, or type the other collector URL by hand.

```bash
docker compose -f compose.yml down
```
