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
- **Diagnosis graph.** A dashboard tab that draws every publisher → subscriber connection, colored by the QoS/type
  rules (red: no data gets through, orange: warning, green: compatible, dashed: nobody publishes), with the finding
  and fix one click away (`/api/graph`).
- **Demo.** `dds-autodiag demo`: two deliberately broken demo topics, diagnosed in about a minute without a robot.
- **Comparison.** Host and container comparison from redacted snapshot files or a token-protected live collector.
- **Sharing.** Markdown reports and snapshot redaction (random salt unless `--salt` is given).
- **CLI.** `doctor`, `check`, `collect`, `compare`, `topics`, `inspect`, `sample`, `selftest`, `demo`, `serve`, with
  `--json` and exit codes 0/1/2.
- **Web dashboard.** Overview, topics, host comparison, transport checks, assistant, tools and settings; light/dark
  themes and a mobile layout.
- **RViz2 panel** (`ros2/rviz_autodiag_panel`) with Health, Topic, AI assistant and Configure RViz tabs, and a launch
  file that starts the server and RViz with the panel together.
- **REST API** with OpenAPI docs at `/api/docs`.
- **AI assistant.** Retrieval over a curated knowledge base of official ROS 2, DDS and Docker documentation (BM25,
  optional local embeddings), cited answers, streamed responses and conversation memory.
- **AI providers.** Local Ollama (offline), Claude (`[cloud]` extra), ChatGPT, Gemini and any OpenAI-compatible API,
  with live model lists. Keys are stored server-side (mode 0600) and never returned to the browser.
- **Configure RViz with AI.** Plans display changes, validates them against live topics, message types, TF frames
  and a display catalog, adds diagnosed QoS fixes, and applies only confirmed items, with Undo.
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
