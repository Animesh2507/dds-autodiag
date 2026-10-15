# Local RAG setup (v0.5)

The dashboard's **Find official documentation** feature works offline, requires no credentials, and uses BM25 keyword retrieval over a small manually curated JSON knowledge base in `docs/kb/`. It is not an exhaustive document crawler or a trained model. The links point to official project documentation; verify against the version you use.

## Optional local generative explanation

1. Install Ollama separately: https://ollama.com/download (review license and hardware requirements).
2. Start `ollama serve` if Ollama is not already running.
3. Download a model: `ollama pull qwen3:4b` (requires internet once; significant download).
4. Optionally set `AUTODIAG_OLLAMA_MODEL=qwen3:4b`.
5. Start AutoDiag GUI and click **Explain using local Ollama**.

The Ollama URL defaults to `http://127.0.0.1:11434`. Only localhost loopback URLs are accepted. Without Ollama or the model, documentation retrieval still works. No API key or subscription is required. The chosen model may have additional license terms.

## Extending documentation

Create a JSON file in `docs/kb/` with `id`, `title`, `url` (official HTTPS reference), `keywords` and `text`. The material here is a brief manually written summary, not a downloaded or copied full documentation page. After editing a document, restart the server.

## Safety and limitations

- Rule-based diagnostics remain authoritative; retrieved sources explain possible causes, not proof.
- A model's output is a hypothesis and might contain errors or unsupported claims; always verify against collected data and cited official docs.
- Diagnostic snapshots and user questions may contain sensitive hostnames or network details. The optional model receives sanitized finding summaries and the user question: keep the Ollama service local.
- No changes to DDS configuration, running nodes, Docker, or network settings are performed.
- The knowledge base is small and static; stale URLs or version mismatch are possible.
