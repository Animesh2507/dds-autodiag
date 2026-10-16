# Configuration

Settings are environment variables, read when the server or CLI starts. For the systemd service, put them in
`~/.config/dds-autodiag.env`. The one exception is AI provider setup made in the dashboard (API keys, models, the
OpenAI-compatible base URL and the default provider), which is saved to `ai-providers.json` in the config directory
(see `AUTODIAG_CONFIG_DIR` below).

## Server

| Variable | Default | Purpose |
|---|---|---|
| `AUTODIAG_HOST` | `127.0.0.1` | Bind address for `serve` |
| `AUTODIAG_PORT` | `8080` | Port for `serve` |
| `AUTODIAG_UI_TOKEN` | — | Require this token for the dashboard and API. Mandatory for non-loopback binds unless `serve --insecure-no-auth` |
| `AUTODIAG_ALLOWED_HOSTS` | — | Extra hostnames/IPs accepted in the `Host` header, comma-separated |
| `AUTODIAG_AGENT_TOKEN` | — | Enables `/api/agent/snapshot` so another AutoDiag can compare against this host |
| `AUTODIAG_LOG_LEVEL` | `INFO` | Server log level |

## Diagnosis

| Variable | Default | Purpose |
|---|---|---|
| `AUTODIAG_DISCOVERY_SECONDS` | `2` | How long ROS graph queries wait for DDS discovery (0.1–10). Raise on slow networks |
| `AUTODIAG_CPP_BINARY` | `cpp/build/autodiag_core_cli` | Native endpoint checker |
| `AUTODIAG_BT_BINARY` | `cpp/build/autodiag_bt` | BehaviorTree.CPP trace runner |

## AI

| Variable | Default | Purpose |
|---|---|---|
| `AUTODIAG_OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama; loopback only |
| `AUTODIAG_OLLAMA_MODEL` | auto | Local model. Auto picks `qwen3:4b-instruct`, then `qwen3:4b`. A model saved in the dashboard overrides it |
| `AUTODIAG_EMBED_MODEL` | `nomic-embed-text` | Embedding model for semantic search |
| `AUTODIAG_EMBED_CACHE` | `~/.cache/dds-autodiag/embeddings` | Embedding cache |
| `AUTODIAG_CONFIG_DIR` | `$XDG_CONFIG_HOME/dds-autodiag`, else `~/.config/dds-autodiag` | Where `ai-providers.json` (linked keys, models) is stored |
| `ANTHROPIC_API_KEY` | — | Claude key (overrides the stored key) |
| `OPENAI_API_KEY` | — | ChatGPT key |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | — | Gemini key |
| `AUTODIAG_COMPAT_API_KEY` | — | Key for the OpenAI-compatible provider |

## RViz panel

The panel stores its server URL, provider, model, topic, "Include the topic" and "every 30 s" in the `.rviz` file.
A saved URL overrides `AUTODIAG_SERVER_URL` (set automatically by the launch file); without one the panel uses
`AUTODIAG_SERVER_URL`, else `http://127.0.0.1:8080`. It reads
`AUTODIAG_UI_TOKEN` from the environment at startup; the token itself is never saved to the `.rviz` file.

## Example

```bash title="~/.config/dds-autodiag.env"
ROS_DOMAIN_ID=7
AUTODIAG_HOST=0.0.0.0
AUTODIAG_PORT=8090
AUTODIAG_DISCOVERY_SECONDS=4
AUTODIAG_UI_TOKEN=change-me-to-a-long-random-string
AUTODIAG_ALLOWED_HOSTS=robot1.local,192.168.1.20
```
