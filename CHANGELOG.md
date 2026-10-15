# Changelog

## 1.1.0

### Added
- RViz panel **Configure RViz** tab: AI-planned display changes (`POST /api/rviz/plan`), validated against live topics, TF frames and a catalog of RViz2 display types; deterministic QoS fixes from AutoDiag's own topic inspection; checklist preview, apply on confirmation, retry for data-dependent settings, and one-step Undo.
- RViz2 panel (`ros2/rviz_autodiag_panel`): health findings, topic QoS inspection (RViz display topics first) and the streamed AI assistant with topic context.
- `/api/assistant/stream` accepts `topic` (adds that topic's live endpoints and QoS findings as context) and collects the local snapshot itself when `host_a` is omitted.
- Streamed AI explanations (`POST /api/assistant/stream`, NDJSON): the first words appear within about a second instead of after the whole answer.
- Linkable cloud providers: Claude (official Anthropic SDK, `[cloud]` extra), ChatGPT, Gemini, and any OpenAI-compatible API. Keys are stored server-side with mode 0600, never returned to the browser, and can be tested and removed from the dashboard (`/api/ai/providers`).
- Model warm-up (`POST /api/ai/warmup`) keeps the local model loaded.

### Fixed
- Local AI took about 70 s per answer with `qwen3:4b`: its hidden reasoning was generated and then discarded. Answers now stream with thinking off. `qwen3:4b-instruct` is preferred when installed, and the thinking-only model is detected and shown with live reasoning progress instead of leaking its reasoning into the answer.

## 1.0.0

### Added
- CLI subcommands `doctor`, `check`, `collect`, `compare`, `topics`, `inspect`, `sample`, `selftest` and `serve`, with readable output, `--json`, and exit codes 0/1/2. The pre-1.0 flags still work.
- New rules: `ROS_ENV_NOT_SOURCED`, `INVALID_DOMAIN_ID`, `DOMAIN_ID_OUTSIDE_SAFE_RANGE`, `DISCOVERY_DISABLED`, `DISCOVERY_RANGE_RESTRICTED`, `ROS_LOCALHOST_ONLY_DEPRECATED`, `RMW_MISMATCH`, `DISTRO_MISMATCH`.
- A synthetic fixture for every rule, plus a rule self-test (CLI, API `/api/selftest`, and the dashboard).
- Markdown report (`/api/report`, `check --report`) and snapshot redaction (`collect --redact`, `/api/snapshot?redact=true`).
- `/api/healthz`, `/api/version`, `/api/endpoint-check` (native C++ core with Python fallback).
- Optional dashboard token (`AUTODIAG_UI_TOKEN`) with a sign-in page, Host-header allow-list, Origin check, strict CSP and security headers.
- Dockerfile, systemd user unit, GitHub Actions CI.

### Changed
- Redesigned dashboard: light/dark themes, mobile layout, readable findings with evidence and documentation, endpoint QoS table, topic filter, side-by-side host comparison, snapshot file upload, error toasts that show the server's message, and remembered preferences. Scripts moved to `static/` (no inline JavaScript).
- The overview runs its probes in parallel and caches the `ros2 doctor` result (about 3 s instead of about 6 s).
- Remote collector errors now say what went wrong (refused, timed out, bad token).

### Fixed
- Graph queries returned partial node/topic lists because `--no-daemon` didn't wait for discovery. They now wait `AUTODIAG_DISCOVERY_SECONDS` (default 2).
- RMW detection always returned "unknown" because the `ros2 doctor` output was cut off before its middleware section.
- The C++ build failed whenever ROS 2's BehaviorTree.CPP package was installed (wrong CMake target name).
- `index_legacy.html` was missing from the package data, so `/legacy` failed on non-editable installs.
- A dead documentation link in the knowledge base (`ros-daemon`).
- Inconsistent version numbers (0.1.0 / 0.7.0 / 0.9.0) unified to a single source.

## 0.9
Task-oriented dashboard, RMW detection via `ros2 doctor`, `/dev/shm` prerequisite checks, Docker container listing, Ollama status.

## 0.8
Behavior Tree visualizer (native BehaviorTree.CPP trace or labelled simulation).

## 0.7
Portable C++20 core (observer, health state machine, strategy registry), CTest, Python bridge.

## 0.6
Hybrid BM25 and local-embedding retrieval, version-annotated knowledge base, synthetic fault fixtures.

## 0.5
Offline documentation retrieval and optional local Ollama explanations.

## 0.4
Deterministic diagnostic assistant with evidence and next tests.

## 0.3
Live endpoint/QoS inspector, authenticated remote collector, cross-host snapshot comparison.
