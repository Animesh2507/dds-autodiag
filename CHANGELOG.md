# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Versions below 1.0 may still change interfaces between minor releases.

## 0.1.0 - Unreleased

Upcoming first public release. Not tagged yet.

### Diagnostics
- 22 read-only diagnostic rules for ROS 2 / DDS: domain IDs, discovery range and localhost-only settings, RMW
  mismatches (including Zenoh vs DDS), distro mismatches, DDS XML files, QoS reliability/durability/type
  incompatibilities, shared memory between containers (IPC namespaces), intra-process expectations, multicast, and
  an unsourced ROS environment. Every finding has evidence, a next step and official documentation.
- A synthetic fault fixture for every rule, plus a rule self-test (`dds-autodiag selftest`, `/api/selftest`).
- Environment collector: ROS variables, effective RMW via `ros2 doctor`, network interfaces, container namespaces,
  and ROS graph queries that wait for DDS discovery (`AUTODIAG_DISCOVERY_SECONDS`).
- Live topic inspection (endpoints and QoS) and one-shot message sampling.
- Host and container comparison from redacted snapshot files or a token-protected live collector.
- Markdown reports and snapshot redaction for sharing.

### Interfaces
- CLI: `doctor`, `check`, `collect`, `compare`, `topics`, `inspect`, `sample`, `selftest`, `serve`, with `--json`
  and exit codes 0/1/2.
- Web dashboard: overview, topics, host comparison, transport checks, assistant, tools and settings; light/dark
  themes and a mobile layout.
- RViz2 panel (`ros2/rviz_autodiag_panel`) with Health, Topic, AI assistant and Configure RViz tabs.
- REST API with OpenAPI docs at `/api/docs`.

### AI
- Grounded assistant: retrieval over a curated knowledge base of official ROS 2, DDS and Docker documentation
  (BM25, optional local embeddings), cited answers, streamed responses and conversation memory.
- Providers: local Ollama (offline), Claude (`[cloud]` extra), ChatGPT, Gemini and any OpenAI-compatible API, with
  live model lists. Keys are stored server-side (mode 0600) and never returned to the browser.
- Configure RViz with AI: plans display changes, validates them against live topics, message types, TF frames and a
  display catalog, adds diagnosed QoS fixes, and applies only confirmed items, with Undo.

### Native
- C++20 diagnostic core with CTest, and a BehaviorTree.CPP trace viewer.

### Security
- Read-only by design. Loopback binding by default, optional token login, Host-header allow-list (DNS-rebinding
  protection), Origin checks, strict Content-Security-Policy and security headers.

### Deployment & documentation
- Docker image, systemd user service and GitHub Actions CI.
- Documentation site (MkDocs Material) with guides, concepts and reference.

### Development history

Before this first public release, the project went through several internal prototypes. They introduced, in order:
cross-host snapshot comparison and the live QoS inspector; the deterministic diagnostic assistant; offline
documentation retrieval with optional local AI; hybrid retrieval and synthetic fault fixtures; the C++ core; the
Behavior Tree viewer; and the task-oriented dashboard. Their notes are kept in `docs/archive/`.
