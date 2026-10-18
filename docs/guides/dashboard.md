# Web dashboard

```bash
dds-autodiag serve --open      # http://127.0.0.1:8080
```

The dashboard runs locally and is laid out like a console: a status bar on top, the sections in the rail on the left
and an event log at the bottom. Colour only ever means health (red, amber, green); everything else stays black and
white. It opens dark unless your system is set to light, **Theme** switches, and the fonts ship with AutoDiag, so it
looks the same offline. It also works on a phone-sized screen.

## Status bar and event log

- **Status bar:** domain ID, RMW, distro, node and topic counts, and the problems and warnings found so far. The
  counts add up the host checks and the graph; click one to open where they were found. The dot next to the name
  turns red as soon as anything is broken.
- **Event log:** every check you run (overview, graph, topic inspection) with its time, level, topic and rule, newest
  first. Click an entry to open that topic in the inspector. **Hide** folds the log away, and the dashboard remembers
  it.

## Overview

The landing page answers "is this machine set up correctly?":

- **Status banner:** a configuration problem, or *"no confirmed problems, data flow not yet verified"*.
- **Key facts:** host, ROS distro, domain ID, effective RMW (detected with `ros2 doctor`), discovery range, node and
  topic counts, and whether AutoDiag runs inside a container.
- **Findings:** sorted by severity, each with evidence, the next step and links to official documentation where one
  applies.
- **What has been verified?:** which checks passed and which are still *not tested* or *not verified*.

## Topics

1. **Discover topics** lists everything visible in the ROS graph, with a filter.
2. Click a topic to see every publisher and subscriber with reliability, durability and history.
   Incompatible pairs appear as findings.
3. **Read one sample** waits up to 3–15 s for a real message, using *Auto*, *Best effort* or *Reliable*. Tick
   **Repeat every 3 s** to watch a topic. A received message proves delivery to the probe; a timeout tells you
   where to look next.

## Graph

**Check connections** draws every publisher → subscriber connection on the visible topics and checks each one with
the same QoS and type rules as the topic inspector:

![Diagnosis graph: lidar_driver to rviz on /scan in red with a break mark, map_server to rviz on /map in amber, dashed
lines for subscribers nobody publishes to, and the selected link's QoS side by side](../assets/media/diagnosis-graph.png)

- **Red, with a break mark:** a problem; no data gets through (e.g. best-effort publisher, reliable subscriber).
- **Amber:** a warning, e.g. a Volatile subscriber that misses latched (Transient Local) data such as a map.
- **Green, with moving dots:** compatible QoS and types. The dots stand still if your system asks for reduced motion.
- **Dashed:** a subscriber is waiting, but nobody publishes the topic (from this machine's point of view).

Every link has its own port on each node, so you can follow it from end to end. The worst link opens straight away
in the inspector on the right: its state, the offered and requested QoS side by side with the policy at fault
marked, the finding, the fix and a link to the topic inspector. Click any other link to switch. Discovery runs once
for the whole graph (about 3 s); `/rosout` and `/parameter_events` are hidden, optional companion topics such as
`/map_updates` are never reported as waiting, nodes started with `ros2 topic pub/echo` are shown as such, and tf2's
internal listener nodes appear as *TF listener*. A problem is reported once per connection, even if a node (like RViz)
holds several endpoints on the same topic. Like the topic inspector, the graph shows which endpoints exist and whether
they are compatible, not that messages are delivered.

## Hosts

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
if you choose, a streamed AI explanation. If your question names a live topic ("why does my map stay empty" →
`/map`), its live endpoints and QoS findings are included too, and the answer says which topic it used. Follow-up
questions keep the conversation. See
[AI providers](ai-providers.md) and [RAG & AI pipeline](../concepts/rag.md).

## Tools

- **Rule self-test:** runs every rule against its synthetic faults (27 fixtures) and shows pass/fail per fixture.
- **Endpoint QoS checker** *(experimental)*: describe a publisher/subscriber pair by hand (e.g. from a design doc)
  and check it, using the native C++ core when built, else the Python rules. Both report the same rule codes.
- **Behavior Tree viewer** *(experimental)*: replays the diagnosis behavior tree (native BehaviorTree.CPP trace or a
  labeled simulation).

## Settings

Version, enabled features, and **AI providers**: link or remove API keys, pick models from live lists, test a
provider, and choose the default.

## Status bar actions

| Button | What it does |
|---|---|
| **Theme** (half-filled circle) | Switches dark/light |
| **Export** | Downloads this machine's snapshot, redacted by default |
| **Report** | Markdown report of the current comparison, ready for a ticket |
| **Check again** | Re-collects everything |

The previous interface is still available at `/legacy` *(experimental, may be removed before 1.0)*, and the
interactive API reference at `/api/docs`.
