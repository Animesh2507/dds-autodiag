# RAG & AI pipeline

The assistant uses **retrieval-augmented generation (RAG)**: before a model answers, AutoDiag retrieves the most
relevant passages from curated official documentation and puts them, together with your current findings, into the
prompt. Answers are grounded in real sources and cite them.

--8<-- "assets/diagrams/rag.svg"

## 1. Knowledge base

`autodiag/kb/` holds about 40 short summaries, written for AutoDiag, each linking the official page it is based on:

- **ROS 2 concepts:** nodes, topics, services, actions, parameters, interfaces, launch, remapping and namespaces,
  discovery, tf2, executors and callback groups, composition, lifecycle nodes, logging, time and `use_sim_time`,
  rosbag2, workspaces and colcon, the environment, `ros2 doctor`, RViz and rqt;
- **communication troubleshooting:** QoS, domain IDs, discovery ranges, RMW implementations and Zenoh, Fast DDS,
  Cyclone DDS, Docker networking and shared memory, Linux namespaces, intra-process communication and security.

Each entry is a JSON document:

```json
{
  "id": "ros-qos",
  "title": "ROS 2 Quality of Service (QoS)",
  "url": "https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html",
  "keywords": "qos best_effort reliable volatile transient_local compatibility",
  "text": "Reliability is request/offered: a best-effort publisher cannot serve a reliable subscriber..."
}
```

Only HTTPS links are accepted; entries are curated from official sources. To add knowledge, add a JSON file and restart the server.

## 2. Query

AutoDiag searches twice: for **your question**, and for the **codes and summaries of the current findings**. Pages
for your question come first, so a general question ("what are actions?") isn't drowned out by the findings, but one
of the three places always goes to the best page about the current findings, so the diagnosed problem stays covered.

## 3. Retrieve

| Method | When | How |
|---|---|---|
| **BM25** | Always (offline) | Keyword ranking over title (counted twice), text and keywords. Stop words are ignored, plurals folded ("actions" finds "action") and underscores split, so the code `DOMAIN_MISMATCH` finds text about a domain mismatch |
| **Hybrid** | When *Semantic search* is enabled | BM25 blended 50/50 with cosine similarity of local `nomic-embed-text` embeddings |

**Only relevant pages are used.** The best match must share a fairly distinctive word with the query (BM25 score of
at least 1.2), and every other result needs at least 35 % of the best score. With embeddings, a page without a keyword
match needs a cosine similarity of at least 0.55. If nothing passes, the dashboard says that no documentation matched,
and the model is told so instead of being handed unrelated pages.

Document embeddings are cached on disk. If the embedding model isn't available, retrieval falls back to BM25
automatically.

## 4. Ground

The top three excerpts go into the prompt, marked as **data, not instructions**, which guards against prompt
injection from documents or findings. Excerpts are referenced by id (`[ros-qos]`) instead of URL, so small models
can't garble the links. For cloud providers, node names, the hostname, IP addresses and home paths in the findings
are masked first; see [Security model](security.md#data-sent-to-ai-providers).

## 5. Generate

Any configured provider streams the answer as NDJSON events (`context`, `meta`, `thinking`, `token`, `done`/`error`), so the
first words appear within a second or two. Earlier turns of the conversation are included for follow-up questions.

## 6. Answer

`[id]` citations in the answer become links to the real documentation pages, and the retrieved sources are listed
under the answer. The rule-based findings stay the source of truth; the answer is labeled as advice.

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
