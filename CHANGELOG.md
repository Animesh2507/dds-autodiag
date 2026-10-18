# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Versions below 1.0 may still change interfaces between minor releases.

## [Unreleased]

Upcoming first public release, 0.1.0. Not tagged yet.

### Added

- **Diagnostics.** 23 read-only diagnostic rules for ROS 2 / DDS: domain IDs, discovery range and localhost-only
  settings, RMW mismatches (including Zenoh vs DDS), distro mismatches, DDS XML files, QoS reliability/durability/type
  incompatibilities, shared memory between containers (IPC namespaces), intra-process expectations, multicast, and
  an unsourced ROS environment. Every finding has evidence, a next step and official documentation where one
  applies.
- **Self-test.** 27 synthetic fault fixtures covering every rule, plus a rule self-test (`dds-autodiag selftest`,
  `/api/selftest`). The rule reference is generated from the same fixtures.
- **Collector.** ROS variables, network interfaces, container namespaces, and ROS graph queries that wait for DDS
  discovery (`AUTODIAG_DISCOVERY_SECONDS`). The dashboard overview also detects the effective RMW via
  `ros2 doctor --report`.
- **Live topics.** Topic inspection (endpoints and QoS) and one-shot message sampling, including a warning when a
  subscriber requests Volatile from latched (Transient Local) data, such as an RViz Map display that stays empty.
- **AI model benchmark.** `dds-autodiag bench` scores models on eight fixed Configure RViz scenarios (correct
  actions, invalid suggestions, time and tokens per plan); results for one machine are in the docs.
- **Faster local planning.** The Configure RViz prompt is slimmed by retrieval (only the display types, topics and
  settings a request needs): about 44% fewer prompt tokens and 35% less time per plan with a local 4B model.
- **Diagnosis graph.** A dashboard tab and an RViz panel tab that draw every publisher → subscriber connection, colored by the QoS/type
  rules (red with a break mark: no data gets through, amber: warning, green: compatible, dashed: nobody publishes).
  Every link has its own ports, and the worst one opens in an inspector with offered and requested QoS side by side,
  the finding and the fix (`/api/graph`).
- **Demo.** `dds-autodiag demo`: two deliberately broken demo topics, diagnosed in about a minute without a robot.
- **Comparison.** Host and container comparison from redacted snapshot files or a token-protected live collector.
- **Sharing.** Markdown reports and snapshot redaction (random salt unless `--salt` is given).
- **CLI.** `doctor`, `check`, `collect`, `compare`, `topics`, `inspect`, `sample`, `selftest`, `demo`, `serve`, with
  `--json` and exit codes 0/1/2.
- **Web dashboard.** A console layout: a status bar with domain, RMW, distro, counts and the problems found so far,
  a section rail, and an event log of every check. Overview, topics, graph, host comparison, transport checks,
  assistant, tools and settings; dark and light themes, bundled IBM Plex fonts (SIL OFL) so it looks the same
  offline, and a mobile layout.
- **RViz2 panel** (`ros2/rviz_autodiag_panel`) with Health, Topic, Graph, AI assistant and Configure RViz tabs, and a launch
  file that starts the server and RViz with the panel together.
- **REST API** with OpenAPI docs at `/api/docs`.
- **AI assistant.** Retrieval over a curated knowledge base of about 80 pages on DDS AutoDiag itself, core ROS 2
  concepts, communication troubleshooting, robotics maths and control, each linking the official documentation (BM25 with a relevance cutoff, optional
  local embeddings; the question first, plus the current findings), cited answers, a check of every dds-autodiag
  command an answer mentions, streamed responses and conversation memory. The dashboard includes the
  live QoS findings of a topic the question names.
- **AI providers.** Local Ollama (offline), Claude (`[cloud]` extra), ChatGPT, Gemini and any OpenAI-compatible API,
  with live model lists. Keys are stored server-side (mode 0600) and never returned to the browser.
- **Configure RViz with AI.** Plans display changes, validates them against live topics, message types, TF frames
  and a display catalog, adds diagnosed QoS fixes, corrects model QoS settings that would receive nothing (such as
  Best Effort on a latched topic), and applies only confirmed items, with Undo.
- **Native.** C++20 diagnostic core with CTest, and a BehaviorTree.CPP trace viewer.
- **Deployment.** Docker image (published to `ghcr.io` on release tags), systemd user service and GitHub Actions CI.
- **Project.** Issue and pull request templates, a security policy, and a documentation site (MkDocs Material) with
  guides, concepts and reference.

### Security

- Read-only by design. Loopback binding by default, token login (mandatory for non-loopback binds unless
  `--insecure-no-auth`), Host-header allow-list (DNS-rebinding protection), Origin checks, strict
  Content-Security-Policy and security headers.
- Cloud AI privacy: before anything reaches a cloud provider, node names become `publisher 1`, `subscriber 1`, …,
  and this machine's hostname, IP addresses and home paths are replaced with tokens. Snapshots, message contents and
  API keys are never sent.

## Development history

Before this first public release, the project went through several internal prototypes. They introduced, in order:
cross-host snapshot comparison and the live QoS inspector; the deterministic diagnostic assistant; offline
documentation retrieval with optional local AI; hybrid retrieval and synthetic fault fixtures; the C++ core; the
Behavior Tree viewer; and the task-oriented dashboard. Their notes are kept in `docs/archive/`.

[Unreleased]: https://github.com/Animesh2507/dds-autodiag/commits/main
