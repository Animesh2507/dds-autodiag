# AI providers

AI is optional. Every diagnosis is rule-based; AI explains findings and plans RViz views. You can run fully offline
or link a cloud provider.

| Provider | Setup | Default model | Typical speed |
|---|---|---|---|
| **Local Ollama** | `ollama pull qwen3:4b-instruct` | `qwen3:4b-instruct` (an installed `qwen3:4b` is used if the instruct build is missing) | First words in 1–2 s, answer in ~10–15 s on a CPU |
| **Claude** | API key + `pip install ".[cloud]"` | `claude-opus-5-5` (low effort) | Answer in ~3–7 s |
| **ChatGPT** | API key | `gpt-5-mini` | Seconds |
| **Gemini** | API key (free tier available) | `gemini-2.5-flash` | Seconds |
| **OpenAI-compatible** | Base URL + API key | your choice | Depends on the service |

## Linking an API key

1. Open the dashboard → **Settings → AI providers**.
2. Paste the key into the provider's card and press **Save**. The badge changes to **READY**.
3. Press **Test** to confirm it works.
4. Optionally press **Make default**.
5. Choose the provider and model in the **Assistant** tab or the RViz panel.

The **Model** dropdown lists the models your account actually offers (fetched live once a key is saved); **Other…**
accepts any model name, and **↻ refresh** reloads the list.

Base URLs for the OpenAI-compatible provider:

=== "Groq"

    Base URL `https://api.groq.com/openai/v1`

=== "OpenRouter"

    Base URL `https://openrouter.ai/api/v1`

=== "Mistral"

    Base URL `https://api.mistral.ai/v1`

=== "LM Studio (local)"

    Base URL `http://localhost:1234/v1`, any key

## Keys and privacy

- Keys are stored on the server in `$XDG_CONFIG_HOME/dds-autodiag/ai-providers.json` (by default
  `~/.config/dds-autodiag/ai-providers.json`) with file mode `0600` (only your user can read it). They're never sent
  back to the browser; the UI shows only the last four characters.
- Environment variables take precedence: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` /
  `GOOGLE_API_KEY`, `AUTODIAG_COMPAT_API_KEY`.
- What a model receives:

| Feature | Sent | Never sent |
|---|---|---|
| Assistant | Your question; earlier turns of the conversation (your questions and previous answers); code, severity and summary of each finding; the top three documentation excerpts; only with **Include the topic** (RViz panel) or for a live topic your question names (dashboard): topic name, message type, endpoint counts and QoS | Snapshots, message contents, node names (to cloud providers), hostnames, IP addresses, home paths, API keys |
| Configure RViz | Your request; earlier turns; display names, types, topics, properties and status; Fixed Frame; TF frame names; live topic names and types; diagnosed QoS facts | Snapshots, message contents, node names, hostnames, IP addresses, home paths, API keys |

- For cloud providers, everything AutoDiag adds is masked first: node names become `publisher 1`, `subscriber 1`, …,
  and this machine's hostname, IP addresses and home paths are replaced with tokens. Local Ollama gets the real names,
  and the UI always shows the real names. In the assistant, your question is sent as you typed it.

## Fast local answers

`qwen3:4b` on Ollama is Qwen3-4B-*Thinking*, which always reasons before it answers, about a minute on a CPU.
`qwen3:4b-instruct` is the same size and answers directly:

```bash
ollama pull qwen3:4b-instruct
```

AutoDiag prefers it automatically once installed and keeps the model loaded between questions. If you choose the
thinking model anyway, a live progress counter shows how many characters it has reasoned so far; the reasoning text
itself isn't shown, only the final answer. Run
`ollama ps` to see whether the model uses the CPU or the GPU.

## Advice, not authority

The AI explains; it doesn't decide. Findings come from deterministic rules, every answer is labeled as advice, and
in Configure RViz every proposed change is validated and shown to you before it's applied.
