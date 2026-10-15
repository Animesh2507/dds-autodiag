# v0.6 Evaluation and known limitations

## Run controlled offline cases

`python -m unittest discover -s tests -v`

`GET /api/v06/fixture/domain_mismatch` runs a SYNTHETIC configuration comparison; it is not evidence that any ROS 2 network has been inspected.

## Live ROS 2 Jazzy validation protocol (operator-run)

1. On two independently controlled Ubuntu 24.04 hosts, source `/opt/ros/jazzy/setup.bash`.
2. Start test publishers/subscribers using `demo_nodes_cpp`, one pair using Fast DDS and one using Cyclone DDS, while maintaining the same domain ID. Confirm samples with `ros2 topic echo` and `ros2 topic hz`.
3. Capture AutoDiag local snapshots and `ros2 topic info <topic> --verbose` output; compare findings with observed sample delivery.
4. Inject one fault at a time: mismatched ROS_DOMAIN_ID, incompatible offered/requested reliability, changed interfaces, Docker bridge versus host networking. Reset after each case.
5. Measure confirmed detection, false positives, missed failures, diagnostic latency, and conditions where evidence is insufficient.
6. Validate against baseline `ros2 doctor`, `rqt_graph`, `ros2 topic info`, and vendor diagnostics before marketing improvements.

## Status
No live Jazzy, Docker or remote-PC end-to-end validation is provided by these offline tests.
The collector may not see the effective environment of a different PID/container.
RAG outputs are advisory; no model-generated explanation proves root cause.
Automatic modifications/restarts are intentionally disabled.

## Source and license policy
Knowledge items are short independently authored summaries plus official links, not scraped documentation.
Operators should check version relevance and availability of referenced vendor docs.
