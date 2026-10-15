# Design decisions

Short architecture decision records (ADRs): the context, the decision, and its consequences. They explain *why* the
system looks the way it does.

## ADR-001: Read-only by design

**Context.** A diagnostics tool runs on robots that may be in operation. Any automatic "fix" (restarting daemons,
changing QoS, editing DDS XML) could make things worse or be unsafe.

**Decision.** AutoDiag only observes. The single exception is the RViz *view*, changed only after explicit
confirmation and reversible with Undo.

**Consequences.** Users can run it anywhere without fear, including on production robots. Fixes are recommendations
the user applies. Features that would act on the robot (for example sending Nav2 goals) need a separate, opt-in,
confirmation-gated mode.

## ADR-002: Deterministic rules decide, AI explains

**Context.** Language models are helpful at explaining and planning but can be confidently wrong, and small local
models make frequent mistakes.

**Decision.** Findings come only from deterministic, tested rules. AI explains findings with retrieved
documentation, and AI-proposed RViz changes are validated and completed by deterministic code before the user sees
them.

**Consequences.** Results are reproducible and testable with fixtures; the AI can be swapped or switched off without
losing diagnosis. Health stays conservative (`insufficient_evidence`) unless every check is confirmed.

## ADR-003: A local server shared by all clients

**Context.** There are three clients: CLI, browser and RViz panel. Each needs diagnostics, retrieval and AI providers.

**Decision.** One local FastAPI server holds all logic and secrets; the dashboard and panel are thin clients. The CLI
imports the same engines directly.

**Consequences.** One implementation, keys in one place, a small C++ panel. The panel needs the server running, which
the systemd unit and Docker image make easy.

## ADR-004: BM25 first, embeddings optional

**Context.** The knowledge base is small and curated. A vector database or an always-on embedding model adds setup
cost and breaks the offline promise.

**Decision.** Use a small built-in BM25 ranker by default; blend in local embeddings only when semantic search is
enabled and the model is available, with automatic fallback.

**Consequences.** Retrieval works offline with zero setup, and improves when Ollama is present.

## ADR-005: Keys stay on the server

**Context.** Cloud AI keys are sensitive; `.rviz` files and browser storage are often shared or synced.

**Decision.** Keys are stored server-side with file mode `0600` (or read from environment variables) and are never
returned to clients.

**Consequences.** Clients can switch providers without ever handling keys. Changing keys requires access to the
server's settings page or environment.

## ADR-006: Stream everything the user waits for

**Context.** A local 4B model on a CPU needs 10–30 s for a full answer; waiting on a blank screen feels broken.

**Decision.** Answers are streamed as NDJSON events (first words in ~1–2 s); reasoning models report progress.
Instruct models are preferred over thinking-only models for local use.

**Consequences.** Perceived latency dropped from about a minute to one or two seconds. Clients parse a line-based
stream instead of one JSON response.

## ADR-007: Wait for DDS discovery in graph queries

**Context.** `ros2 … --no-daemon` creates a fresh DDS participant per call and often returns before discovery
completes, giving incomplete, changing node and topic lists.

**Decision.** Graph queries pass `--spin-time` (`AUTODIAG_DISCOVERY_SECONDS`, default 2).

**Consequences.** Consistent results at the cost of about two seconds per query; probes run in parallel to keep the
overview at about three seconds.

## ADR-008: Structured plans with a small, flat action vocabulary

**Context.** Free-text plans can't be applied safely, and complex nested schemas confuse small models.

**Decision.** Seven actions, one flat schema, enforced through each provider's structured-output mode, followed by
validation against live topics, types, frames and a display catalog.

**Consequences.** Works with local and cloud models alike; every action can be explained, unticked and undone. New
capabilities mean extending the vocabulary deliberately.

## ADR-009: Prefer gzip for Claude responses

**Context.** In ROS virtual environments created with `--system-site-packages`, an older system `brotli` package is
visible. The SDK's HTTP stack then fails to decode Brotli-compressed replies, which surfaces as a misleading
"connection error".

**Decision.** Claude requests send `Accept-Encoding: gzip, deflate`, and connection errors are classified (timeout,
local decoding failure, network).

**Consequences.** Works regardless of the system's Brotli version; errors name the real cause.
