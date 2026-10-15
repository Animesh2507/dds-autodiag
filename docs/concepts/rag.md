# RAG & AI pipeline

The assistant uses **retrieval-augmented generation (RAG)**: before a model answers, AutoDiag retrieves the most
relevant passages from curated official documentation and puts them, together with your current findings, into the
prompt. Answers are grounded in real sources and cite them.

--8<-- "assets/diagrams/rag.svg"

## 1. Knowledge base

`autodiag/kb/` holds short, curated summaries of official ROS 2, Fast DDS, Cyclone DDS, Docker and Linux
documentation. Each entry is a JSON document:

```json
{
  "id": "ros-qos",
  "title": "ROS 2 Quality of Service",
  "url": "https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html",
  "keywords": "qos best_effort reliable volatile transient_local compatibility",
  "text": "Reliability is request/offered: a best-effort publisher cannot serve a reliable subscriber..."
}
```

Only HTTPS links to official sources are accepted. To add knowledge, add a JSON file and restart the server.

## 2. Query

The search query combines **your question** with the **codes and summaries of the current findings**. Retrieval is
therefore driven by the diagnosed problem, not only by your wording.

## 3. Retrieve

| Method | When | How |
|---|---|---|
| **BM25** | Always (offline) | Keyword ranking over title, text and keywords |
| **Hybrid** | When *Semantic search* is enabled | BM25 blended 50/50 with cosine similarity of local `nomic-embed-text` embeddings |

Document embeddings are cached on disk. If the embedding model isn't available, retrieval falls back to BM25
automatically.

## 4. Ground

The top three excerpts go into the prompt, marked as **data, not instructions**, which guards against prompt
injection from documents or findings. Excerpts are referenced by id (`[ros-qos]`) instead of URL, so small models
can't garble the links.

## 5. Generate

Any configured provider streams the answer as NDJSON events (`context`, `meta`, `token`, `done`/`error`), so the
first words appear within a second or two. Earlier turns of the conversation are included for follow-up questions.

## 6. Answer

`[id]` citations in the answer become links to the real documentation pages, and the retrieved sources are listed
under the answer. The rule-based findings stay the source of truth; the answer is labelled as advice.

## Configure RViz: grounding without documents

The RViz planner uses the same principle with a different source. Instead of documents, it grounds the model in the
**live system**: current displays and their settings, visible topics and types, TF frames, diagnosed QoS facts, and a
catalog of RViz display types with their exact property names. The model must answer in a strict JSON schema, and
every proposed action is then validated. See [Configure RViz with AI](../guides/configure-rviz.md).

## Speed

| Measure | Effect |
|---|---|
| Streaming | First words in ~1–2 s instead of waiting for the full answer |
| `qwen3:4b-instruct` preferred | Direct answers; the thinking variant spends most of its time reasoning |
| Model kept loaded (`keep_alive`) + warm-up | No reload delay between questions |
| Bounded context and output | Short prompts, ~180-word answers |
| Low effort on cloud models | Fast, concise answers |
