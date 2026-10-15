# Behavior Tree Visualizer (v0.8)

Run the dashboard (`uvicorn autodiag.server:app --host 127.0.0.1 --port 8080`) and scroll to **Behavior Tree Visualizer**. Start a normal run or a QoS fault run; replay, pause and change animation speed.

**Execution sources:** The UI labels actual `autodiag_bt` subprocess events as **Native C++ trace**, and its deterministic fallback as **SIMULATED**. Both use sample endpoint configurations. Neither represents live ROS 2 transport measurements. To build native traces, install BehaviorTree.CPP v4 and compile with `cmake -S cpp -B cpp/build && cmake --build cpp/build`. If needed, set `AUTODIAG_BT_BINARY` to the full path of the executable.

The sample diagnostic always ticks all three nodes. Green SUCCESS means a check executed, not that communication is healthy. `issue_count` reports sample detected mismatches separately. The backend invokes only a configured local executable with a fixed `--fault` flag; it does not accept shell commands from users.

Future work: streaming transitions directly from running ROS 2 diagnostic tree over a separate management connection.
