# Read-only topic sample viewer (v0.8.1)

The Live ROS 2 Topic Diagnostics section already discovers topics with their message types. This update adds a **Read one raw message** button and optional auto-refresh.

The backend executes `ros2 topic echo <topic> --once` as a bounded subprocess (up to 8 seconds from the GUI). The probe accepts only validated topic names and known reliability options. Sample displays are limited to 16 KB.

**Limitations:** Sampling very large messages (images, point clouds) can be expensive; text may be truncated. Each auto-refresh cycle is a new one-shot subscription, not a persistent high-rate monitor. The tool does not decode custom binary payloads, prove SHM transport selection, or inspect topics invisible to the selected ROS domain/RMW. Probe QoS must be compatible with publisher QoS.

This is intended for local, trusted development systems only. Topic payloads may contain sensitive information; do not expose the dashboard to untrusted networks.
