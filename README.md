# DDS AutoDiag

**Tells you why your ROS 2 nodes can't talk to each other, and fixes your RViz view for you.**

Topic visible in `ros2 topic list`, but no data arrives? RViz stays empty? DDS AutoDiag checks the usual causes in
seconds (QoS, domain ID, discovery range, RMW, shared memory between containers) and tells you exactly what to
change. It is **read-only**: it never touches your robot or ROS configuration.

<!-- Demo GIF goes here: docs/assets/media/demo.gif -->

## Quick start

```bash
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install .

dds-autodiag doctor            # is this machine ready?
dds-autodiag inspect /scan     # why is this topic silent?
dds-autodiag serve --open      # dashboard at http://127.0.0.1:8080
```

## What's included

| | Feature | |
|---|---|---|
| **Core** | **Diagnosis**: 22 rules with evidence, a next step and official docs; live topic QoS inspection; one-shot message sampling | CLI · dashboard |
| | **RViz2 panel**: health, topic QoS and AI, right next to your displays | `ros2/rviz_autodiag_panel` |
| **AI add-ons** | **Assistant**: answers grounded in official ROS 2 / DDS docs, streamed, with follow-ups | Local Ollama or Claude, ChatGPT, Gemini |
| | **Configure RViz**: describe the view; every change is validated against your live system, applied on confirmation, undoable | RViz panel |
| **Extras** | Compare hosts and containers, Markdown reports, redacted snapshots, Docker image, systemd service | |
| **Experimental** | Native C++ endpoint checker, BehaviorTree.CPP trace viewer, the previous UI at `/legacy` | May change or be removed before 1.0 |

AI is optional: without it, diagnosis and documentation search still work fully offline.

## Documentation

Guides, architecture and reference live in [`docs/`](docs/). To browse them as a website:

```bash
pip install ".[docs]" && mkdocs serve      # http://127.0.0.1:8000
```

Good starting points: [Quick start](docs/getting-started/quickstart.md) ·
[Configure RViz with AI](docs/guides/configure-rviz.md) · [Diagnostic rules](docs/reference/rules.md) ·
[Architecture](docs/architecture/index.md) · [Security model](docs/concepts/security.md)

## Status

Version **0.1.0** (unreleased). Tested on ROS 2 Jazzy with Fast DDS on Ubuntu 24.04. Reports from other distros,
RMWs and setups are very welcome; see [Contributing](docs/contributing.md).

**Related work:** [greenwave_monitor](https://github.com/NVIDIA-ISAAC-ROS/greenwave_monitor) measures *how fast* data
flows (topic rate and latency); DDS AutoDiag explains *why* it doesn't.

## License

MIT. See [LICENSE](LICENSE).
