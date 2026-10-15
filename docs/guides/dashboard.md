# Web dashboard

```bash
dds-autodiag serve --open      # http://127.0.0.1:8080
```

The dashboard runs locally and is organized by task. Light and dark themes follow your system, and it works on a
phone-sized screen.

## Overview

The landing page answers "is this machine set up correctly?":

- **Status banner:** a configuration problem, or *"no confirmed problems, data flow not yet verified"*.
- **Key facts:** host, ROS distro, domain ID, effective RMW (detected with `ros2 doctor`), discovery range, node and
  topic counts, and whether AutoDiag runs inside a container.
- **Findings:** sorted by severity, each with evidence, the next step and links to official documentation.
- **What has been verified?:** which checks passed and which are still *not tested* or *not verified*.

## Topics

1. **Discover topics** lists everything visible in the ROS graph, with a filter.
2. Click a topic to see every publisher and subscriber with reliability, durability and history.
   Incompatible pairs appear as findings.
3. **Read one sample** waits up to 3–15 s for a real message, using *Auto*, *Best effort* or *Reliable*. Tick
   **Repeat every 3 s** to watch a topic. A received message proves delivery to the probe; a timeout tells you
   where to look next.

## Compare hosts

Compare this machine with another PC, robot or container: load a snapshot file, paste JSON, or connect to a live,
token-protected collector. A side-by-side table highlights domain, RMW, distro and discovery differences. See
[Compare hosts & containers](compare-hosts.md).

## Transport

Pick the transport you expect your nodes to use (intra-process, DDS shared memory, UDP or TCP) and run the checks.
For shared memory, AutoDiag also inspects `/dev/shm`, free space and the IPC namespace.

!!! warning "Not verified"
    Configuration checks can't tell which transport DDS actually selected at runtime. AutoDiag says so explicitly
    instead of guessing.

## Assistant

Ask in plain language. AutoDiag combines your current findings with the most relevant curated documentation and,
if you choose, a streamed AI explanation. Follow-up questions keep the conversation. See
[AI providers](ai-providers.md) and [RAG & AI pipeline](../concepts/rag.md).

## Tools & self-test

- **Rule self-test:** runs every rule against a synthetic fault and shows pass/fail per rule.
- **Endpoint QoS checker:** describe a publisher/subscriber pair by hand (e.g. from a design doc) and check it,
  using the native C++ core when built, else the Python rules.
- **Behavior Tree viewer:** replays the diagnosis behavior tree (native BehaviorTree.CPP trace or a labelled
  simulation).

## About & settings

Version, enabled features, and **AI providers**: link or remove API keys, pick models from live lists, test a
provider, and choose the default.

## Header actions

| Button | What it does |
|---|---|
| **Theme** | Switches light/dark |
| **Export snapshot** | Downloads this machine's snapshot, redacted by default |
| **Download report** | Markdown report of the current comparison, ready for a ticket |
| **Refresh** | Re-collects everything |

The previous interface is still available at `/legacy`, and the interactive API reference at `/api/docs`.
