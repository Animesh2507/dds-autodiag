# DDS AutoDiag v0.9 — usability and diagnostic honesty

Starting point: v0.8.1 topic viewer archive. The previous dashboard is available at `/legacy`.

## Improvements
- Reorganized responsive GUI: overview, topics, environments, transport diagnosis, BT trace, and unified AI/documentation assistant.
- Added automatic RMW inspection by parsing `ros2 doctor --report` when ROS 2 CLI is available, with configured-vs-detected distinction and scope disclaimers. Does **not** prove RMW used by every node.
- Added non-disruptive `/dev/shm` prerequisites checks and IPC namespace observation. Does **not** prove that DDS actually selected SHM.
- Added read-only Docker container metadata discovery via accessible `docker ps`; cannot inspect container processes or infer ROS domain without a collector.
- Local Ollama API status on loopback, displaying missing model or unreachable service without needing API keys.
- Unified Ollama + curated documentation search into one assistant panel. Removed legacy duplicate controls from the main UI.
- Preserved topic message types, endpoint QoS, and bounded one-message probes.
- Preserved C++ engine and recorded BT visualization. No claim of live BT events.

## Quick start
```bash
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
python -m uvicorn autodiag.server:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080. Native core: `cmake -S cpp -B cpp/build && cmake --build cpp/build && ctest --test-dir cpp/build --output-on-failure`.

## Not yet implemented
- Autonomous discovery of arbitrary remote hosts across routed networks; manual authenticated remote collectors remain an option.
- Live DDS transport selection / verified SHM data path, remote multicast packet inspections, and vendor instrumentation.
- Live BehaviorTree.CPP execution streaming (present BT view replays native traces or a labeled simulation).
- End-to-end tests with ROS 2 installed, on multiple PCs or in Docker environments. Running unit tests outside ROS 2 is not sufficient.
- Production security review. Keep the server bound to loopback; Docker access is highly privileged.

## Testing
49 Python tests and native C++ CTest passed in a development environment without ROS 2. HTML JavaScript syntax checked with Node.js. API routes smoke-tested with FastAPI's TestClient. Real ROS 2 and Ollama model inference remain untested here.
