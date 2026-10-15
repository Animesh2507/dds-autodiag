# REST API

Everything the dashboard and RViz panel do goes through this API. The interactive reference with request and
response schemas is built into the server at **`/api/docs`**.

When `AUTODIAG_UI_TOKEN` is set, send `Authorization: Bearer <token>`.

## Service

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/healthz` | Liveness probe; runs no diagnostics |
| `GET` | `/api/version` | Version, settings (without secrets), native components |

## Snapshots & diagnosis

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v09/overview` | Snapshot, summary, health, findings and capabilities in one call |
| `GET` | `/api/snapshot` | This host's snapshot; `?redact=true` for sharing |
| `POST` | `/api/snapshot/redact` | Redact one or two snapshots with a shared salt |
| `GET` | `/api/health` | Health and findings for this host |
| `POST` | `/api/compare` | Findings for `host_a` (and optional `host_b`) |
| `POST` | `/api/remote-compare` | Fetch a live collector and compare |
| `POST` | `/api/report` | Markdown report |
| `POST` | `/api/endpoint-check` | Check a hand-described publisher/subscriber pair |
| `GET` | `/api/selftest` | Run every rule against its synthetic fault |
| `GET` | `/api/agent/snapshot` | Collector endpoint for peers (requires `X-Autodiag-Token`) |

## Live ROS graph

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/topics` | Topics and types |
| `GET` | `/api/topic-inspect?topic=/x` | Endpoints, QoS and incompatibilities |
| `GET` | `/api/topic-sample?topic=/x&timeout=8&reliability=auto` | Read one live message |
| `GET` | `/api/v09/environments` | Local Docker containers |
| `GET` | `/api/v09/shm` | Shared-memory prerequisites |

## AI

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/assistant/stream` | Streamed, grounded explanation (NDJSON) |
| `POST` | `/api/v06/explain` | Documentation retrieval without streaming |
| `POST` | `/api/rviz/plan` | Validated RViz configuration plan |
| `GET` | `/api/rviz/catalog` | Display types and properties the planner knows |
| `GET` | `/api/ai/providers` | Provider status (keys never returned) |
| `PUT` | `/api/ai/providers/{provider}` | Link a key, set the model or base URL, make default |
| `DELETE` | `/api/ai/providers/{provider}/key` | Remove a stored key |
| `GET` | `/api/ai/providers/{provider}/models` | Live model list (`?refresh=true`) |
| `POST` | `/api/ai/providers/{provider}/test` | Connection test |
| `POST` | `/api/ai/warmup` | Load the local model in the background |
| `GET` | `/api/v09/ollama` | Local Ollama status |

## Streaming format

`POST /api/assistant/stream` returns one JSON object per line:

```json
{"type": "context", "issues": [...], "sources": [...], "retrieval_mode": "bm25", "health": {...}}
{"type": "meta", "provider": "ollama", "label": "Local Ollama", "model": "qwen3:4b-instruct", "cloud": false}
{"type": "token", "text": "**Likely cause** ..."}
{"type": "done", "seconds": 12.4, "first_token_seconds": 1.8}
```

`thinking` events report progress of reasoning models, and `error` replaces `done` on failure.

```bash title="Example"
curl -N -X POST http://127.0.0.1:8080/api/assistant/stream \
  -H 'Content-Type: application/json' \
  -d '{"question": "Why is /scan empty?", "topic": "/scan", "provider": "ollama"}'
```

`host_a` is optional; without it the server collects the local snapshot itself. `history` carries earlier turns
(`[{"role": "user"|"assistant", "content": "..."}]`).

## Compatibility endpoints

Earlier releases' endpoints (`/api/diagnose`, `/api/rag/*`, `/api/v06/fixture*`, `/api/v07/cpp-diagnose`,
`/api/v08/bt/*`) remain available, as does the previous UI at `/legacy`.
