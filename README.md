# DDS AutoDiag

Find out why your ROS 2 nodes can't talk to each other.

DDS AutoDiag is a **read-only** diagnostics tool for ROS 2 / DDS communication problems: nodes that don't see
each other, topics that appear but never deliver data, containers that can't share memory, mismatched domains,
discovery ranges, RMW implementations and QoS. It comes as a local web dashboard and a CLI, and never changes your
system.

## Quick start

```bash
source /opt/ros/jazzy/setup.bash                    # ROS 2 must be sourced in the same shell
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install .

dds-autodiag doctor                                  # is this machine ready?
dds-autodiag serve --open                            # dashboard at http://127.0.0.1:8080
```

No ROS 2 on the machine? Snapshot comparison, the report generator and the rule self-test still work. Live
topic inspection needs a sourced ROS 2 installation.

## What it does

| Area | What you get |
|---|---|
| **Overview** | Host, distro, domain, effective RMW, discovery range, node/topic counts, and prioritized findings with evidence, next step and official docs. |
| **Topics** | Live topic list with filter, publisher/subscriber endpoints with QoS, QoS-incompatibility detection, and one-shot live message sampling. |
| **Compare hosts** | Compare this machine with another PC or container, either from a snapshot file or a live authenticated collector. Shows a side-by-side table that highlights differences. |
| **Transport** | Checks for intra-process, shared memory (incl. Docker IPC namespaces), UDP and TCP setups. |
| **Assistant** | Offline search across curated official ROS 2 / Fast DDS / Cyclone DDS / Docker documentation, plus a streamed AI explanation from local Ollama (offline) or a linked Claude, ChatGPT, Gemini or OpenAI-compatible API key. |
| **Tools** | Rule self-test, a manual publisher/subscriber QoS checker (native C++ core or Python), and a BehaviorTree.CPP trace viewer. |
| **Reports** | Markdown report download for tickets, and redacted snapshot export (hostnames, IPs and home paths hashed). |

### Diagnostic rules

`dds-autodiag selftest` verifies every rule against a synthetic fault.

| Code | Severity | Detects |
|---|---|---|
| `ROS_ENV_NOT_SOURCED` | problem | `ros2` on PATH but the ROS environment isn't sourced |
| `DOMAIN_MISMATCH` | problem | Peers on different `ROS_DOMAIN_ID` |
| `INVALID_DOMAIN_ID` / `DOMAIN_ID_OUTSIDE_SAFE_RANGE` | problem / warning | Non-numeric domain, or above 101 on Linux |
| `LOCALHOST_ONLY` / `DISCOVERY_RANGE_RESTRICTED` | problem | Discovery limited to localhost while the peer is on another host |
| `DISCOVERY_DISABLED` | warning | `ROS_AUTOMATIC_DISCOVERY_RANGE=OFF` without static peers |
| `ROS_LOCALHOST_ONLY_DEPRECATED` | note | `ROS_LOCALHOST_ONLY` on Jazzy and newer |
| `RMW_MISMATCH` | problem / warning | Zenoh vs DDS (can't communicate) or different DDS vendors |
| `DISTRO_MISMATCH` | warning | Different ROS 2 distributions |
| `RELIABILITY_MISMATCH` / `DURABILITY_MISMATCH` / `TYPE_MISMATCH` | problem | Incompatible endpoints on a live topic |
| `DDS_CONFIG_FILE_MISSING` / `CYCLONE_CONFIG_RMW_MISMATCH` | problem / warning | DDS XML not found, or configured for the wrong RMW |
| `SHM_IPC_NAMESPACE_DIFFERENCE` / `SHM_NAMESPACE_UNVERIFIED` | problem / warning | Containers can't share memory |
| `INTRA_PROCESS_SEPARATE_PROCESSES` | problem | Intra-process expected between two processes |
| `MULTICAST_CAPABILITY_ABSENT` | warning | No multicast-capable interface on either side |

## CLI

```text
dds-autodiag doctor                     check prerequisites and print fixes
dds-autodiag check [--peer PEER.json]   diagnose this host (exit 1 if a problem is found)
          [--transport dds_shm] [--report report.md] [--json]
dds-autodiag collect [--redact] [-o FILE]   save a snapshot to compare elsewhere
dds-autodiag compare PEER.json [OTHER.json] compare this host (or OTHER) with PEER
dds-autodiag topics                     list topics visible in the ROS graph
dds-autodiag inspect /topic             endpoints, QoS and incompatibilities
dds-autodiag sample /topic [--timeout 8] [--reliability best_effort]
dds-autodiag selftest                   verify all diagnostic rules
dds-autodiag serve [--host] [--port] [--open]
```

Exit codes: `0` = no problem found, `1` = problem found, `2` = usage or input error. Add `--json` for scripts and CI.

### Comparing two machines or containers

```bash
# On the robot / inside the container (ROS 2 sourced):
dds-autodiag collect --redact --salt team42 -o robot.json
# On your machine:
dds-autodiag compare robot.json --report report.md
```

Use the same `--salt` on both sides when redacting so hostnames stay comparable. In the dashboard, load the file
under **Compare hosts**. For a live connection, start the peer with `AUTODIAG_AGENT_TOKEN=<secret> dds-autodiag serve
--port 8081` and connect over a private IP or SSH tunnel.

## Configuration

All settings are environment variables.

| Variable | Default | Purpose |
|---|---|---|
| `AUTODIAG_HOST` / `AUTODIAG_PORT` | `127.0.0.1` / `8080` | Default bind address for `serve` |
| `AUTODIAG_UI_TOKEN` | — | Require this token for the dashboard and API (sign-in page or `Authorization: Bearer`). Required for non-loopback binds. |
| `AUTODIAG_ALLOWED_HOSTS` | — | Extra hostnames/IPs accepted in the `Host` header (comma-separated), e.g. `robot1.local,192.168.1.20` |
| `AUTODIAG_AGENT_TOKEN` | — | Enables `/api/agent/snapshot` so another AutoDiag can compare against this host |
| `AUTODIAG_DISCOVERY_SECONDS` | `2` | How long graph queries wait for DDS discovery; raise on slow networks |
| `AUTODIAG_OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama (loopback only) |
| `AUTODIAG_OLLAMA_MODEL` | auto (`qwen3:4b-instruct` → `qwen3:4b`) | Local model for AI explanations |
| `AUTODIAG_CONFIG_DIR` | `~/.config/dds-autodiag` | Where linked AI provider keys and models are stored |
| `AUTODIAG_EMBED_MODEL` | `nomic-embed-text` | Model for semantic search |
| `AUTODIAG_EMBED_CACHE` | `~/.cache/dds-autodiag/embeddings` | Embedding cache |
| `AUTODIAG_CPP_BINARY` / `AUTODIAG_BT_BINARY` | `cpp/build/...` | Paths to the native binaries |
| `AUTODIAG_LOG_LEVEL` | `INFO` | Server log level |

### Optional extras

```bash
# Native C++ core + BehaviorTree.CPP runner (needs ros-$ROS_DISTRO-behaviortree-cpp for the BT runner)
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release && cmake --build cpp/build && ctest --test-dir cpp/build

# Local AI
ollama pull qwen3:4b && ollama pull nomic-embed-text
```

## AI explanations

The assistant streams its answer, so the first words appear within about a second. Pick the model in the
**Assistant** tab, and link keys under **About & settings → AI providers**.

| Provider | Setup | Default model |
|---|---|---|
| Local Ollama (offline) | `ollama pull qwen3:4b-instruct` | `qwen3:4b-instruct` if installed, else `qwen3:4b` |
| Claude | API key; `pip install "ros2-dds-autodiag[cloud]"` (Anthropic SDK) | `claude-opus-5-5` (low effort); `claude-haiku-5-5` is the fastest |
| ChatGPT | API key | `gpt-5-mini` |
| Gemini | API key | `gemini-2.5-flash` |
| OpenAI-compatible (Groq, OpenRouter, Mistral, LM Studio…) | Base URL + API key | your choice |

**Fast local answers:** `qwen3:4b` is Qwen3-4B-*Thinking*-2507, which always reasons before answering (about a
minute on a CPU). `qwen3:4b-instruct` is the same size and answers directly. AutoDiag uses it automatically once it
is installed, and keeps the model loaded between questions. If you do choose the thinking model, its reasoning is
shown as live progress and only the final answer is displayed.

**Keys and privacy:** keys are saved in `~/.config/dds-autodiag/ai-providers.json` (mode 0600), or read from
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY` or `AUTODIAG_COMPAT_API_KEY`
(environment variables win). Keys are never sent back to the browser. Cloud providers receive only the finding codes
and summaries, your question and the documentation excerpts; snapshots, hostnames, IPs and topic data are never sent.
The AI answer is advice; the rule-based findings stay the source of truth.

## RViz2 panel

`ros2/rviz_autodiag_panel` adds an **AutoDiag** panel to RViz2 with three tabs:

- **Health:** the overview status and findings.
- **Topic:** publishers, subscribers and QoS incompatibilities. Topics used by your RViz displays come first, and ⚠ marks displays reporting a problem.
- **AI assistant:** the streamed explanation, with the selected topic's live endpoints and QoS included as context.

The panel is a client of the AutoDiag server, so start `dds-autodiag serve` first. AI providers and API keys stay on the server.

```bash
cd ros2
source /opt/ros/jazzy/setup.bash
colcon build --packages-select rviz_autodiag_panel
source install/setup.bash
rviz2        # Panels → Add New Panel → rviz_autodiag_panel → AutoDiag
```

**Configure RViz with AI (fourth tab).** Describe what you want, for example *"Show the lidar point cloud coloured
by height in base_link, keep it light-weight. My laser scan shows nothing."*, and press **Plan changes**:

- The AI proposes concrete changes: add or remove displays, set topics and properties (style, size, colour, decay,
  QoS), enable or disable displays, and set the Fixed Frame.
- AutoDiag checks every change against your live topics, TF frames and the display types before you see it, and
  adds fixes the model missed. For example, it inspects each display's topic, and if the publisher is Best Effort
  while the display requests Reliable, it adds the QoS fix.
- The plan appears as a checklist. Only checked items are applied, and only when you press **Apply checked**.
  Settings that only exist once data arrives are retried for up to 30 s. **Undo** restores the displays and
  Fixed Frame from before the last Apply.
- Pick the AI **Provider** and **Model** at the top of the tab. It is the same selection as the AI assistant tab,
  so changing it in either place changes both.
- **Follow-ups work.** Both the AI assistant and Configure RViz tabs keep the conversation, so you can say "make
  those points bigger" or "how do I make that permanent?". Configure RViz also remembers which changes were applied,
  skipped, failed or undone. **New conversation** starts fresh. History lives only in the panel for the session and
  is never saved to disk.
- It changes RViz only, never the robot or ROS configuration. With the local model on a CPU, planning takes about
  a minute; cloud models take a few seconds. Cloud models receive display settings, topic names/types and frame
  names.

The server URL, provider, model and topic are saved in the `.rviz` config. The access token is not saved (it is read
from `AUTODIAG_UI_TOKEN` if set).

## Deployment

**systemd (user service):** see [deploy/dds-autodiag.service](deploy/dds-autodiag.service) and
[deploy/dds-autodiag.env.example](deploy/dds-autodiag.env.example).

**Docker:**

```bash
docker build -t ros2-dds-autodiag .
docker run --rm --net=host --ipc=host ros2-dds-autodiag             # dashboard on 127.0.0.1:8080
docker run --rm --net=host --ipc=host ros2-dds-autodiag check       # one-shot check
```

`--net=host --ipc=host` lets the container see the same DDS graph and shared memory as the host.

Liveness probe: `GET /api/healthz`. The REST API is documented at `/api/docs`.

## Security

- Every check is read-only. AutoDiag runs `ros2` introspection commands, `ip`, and `docker ps`; it never restarts
  daemons, changes QoS or edits configuration.
- The server binds to `127.0.0.1` by default. `serve` refuses other addresses unless `AUTODIAG_UI_TOKEN` is set
  (or `--insecure-no-auth` is given explicitly).
- Built-in protections: Host-header allow-list (blocks DNS rebinding), Origin check on state-changing requests,
  a strict Content-Security-Policy with no inline script, `X-Frame-Options: DENY`, and constant-time token checks.
- The dashboard has no TLS of its own. For remote access, prefer an SSH tunnel
  (`ssh -L 8080:127.0.0.1:8080 robot`) or a TLS reverse proxy.
- Snapshots contain hostnames, IPs and paths. Share them with `--redact` or the dashboard's redacted export.
- Remote collectors are only fetched from private or loopback IPs, without proxies or redirects, and with a size limit.
- Local AI uses Ollama on loopback only. Cloud AI is opt-in per provider, and receives only sanitized findings (see AI explanations).

## Troubleshooting

| Symptom | Fix |
|---|---|
| “ros2 CLI found, but the ROS 2 environment is not sourced” | `source /opt/ros/<distro>/setup.bash` in the shell that starts AutoDiag, then restart it |
| Node/topic counts vary between refreshes | Increase `AUTODIAG_DISCOVERY_SECONDS` (e.g. `4`) |
| Topic visible but “No message within N s” | The publisher may be idle. Otherwise try the other reliability setting, then check transport (SHM between containers needs `--ipc=host` or a shared IPC namespace) |
| Docker section says permission denied | Add your user to the `docker` group, or ignore it (Docker is optional) |
| “Host header not allowed” | Add the hostname to `AUTODIAG_ALLOWED_HOSTS` |
| Local AI unreachable | `ollama serve`, then `ollama pull qwen3:4b-instruct`. Documentation search works without it |
| Local AI answers slowly | Install `qwen3:4b-instruct` (see AI explanations). `ollama ps` shows whether it runs on the CPU or GPU |

## Limitations

AutoDiag reports what it can observe and labels everything else as *not verified*:

- Snapshots describe the collector's own environment, not every running node (a node may set its own RMW or domain).
- Graph discovery and QoS compatibility don't prove that messages are delivered; use **Read one sample** for that.
- The DDS transport actually selected (SHM vs UDP) and packet-level reachability aren't measured.
- The Behavior Tree viewer replays a trace on sample data; it isn't a live stream.

## Development

```bash
pip install -e ".[dev]"      # newer Starlette releases may also need: pip install httpx2
python -m pytest -q
dds-autodiag selftest
```

The previous dashboard is still available at `/legacy`. Version history is in [CHANGELOG.md](CHANGELOG.md).
