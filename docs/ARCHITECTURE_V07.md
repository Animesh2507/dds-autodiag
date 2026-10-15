# C++ v0.7 architecture and limitations

## Implemented
- Portable C++20 diagnostic rule engine, health-state transitions, synchronous thread-safe observer/event bus.
- Strategy interface/registry with a working generic DDS endpoint compatibility strategy.
- Optional compiled BehaviorTree.CPP v4 coordinator demonstrating Collection -> QoS diagnosis -> Report.
- CTest unit tests and controlled command-line JSON output.
- Fixed-argument Python/FastAPI bridge and GUI entry point. Previous Python collectors, RAG and GUI remain available.

## Not yet implemented
- Production C++ rclcpp live graph monitor, actual DDS vendor-specific strategy plugins, multi-host executable agents, active transport probes, DDS sample reception checks, live BT trace streaming, automated repairs.
- The C++ CLI currently diagnoses **operator-provided endpoint configuration**, not actual remote DDS telemetry. Results without findings retain **unknown**, never verified healthy.
- C++ BT target requires BehaviorTree.CPP v4 available to CMake. The portable engine/test target can build without ROS 2 or BT.

## Architecture
1. Python FastAPI serves the existing web UI and knowledge engine.
2. C++ core handles compatibility findings via a fixed-argument CLI invoked by a restricted bridge.
3. EventBus notifies health state transitions; state machine avoids equating daemon health and data delivery.
4. StrategyRegistry supports future vendor-specific checks without changes to the coordinator.
5. The optional BT target demonstrates correct semantics: node SUCCESS = diagnostic test completed, NOT communication healthy.

## Safety
Read-only. Do not attach to employer systems or expose the development server publicly. Endpoint data sent to the C++ CLI is not interpreted as shell commands.
