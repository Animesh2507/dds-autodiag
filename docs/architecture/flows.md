# Runtime flows

How the main features work at runtime, step by step.

## Compare with a live collector

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant D as Dashboard
    participant S as Local server
    participant P as Peer server
    U->>D: Collector URL + token
    D->>S: POST /api/remote-compare
    S->>S: URL check: http(s), numeric private/loopback IP, no credentials
    S->>P: GET /api/agent/snapshot (X-Autodiag-Token, no proxy, no redirects)
    P->>P: Constant-time token check
    P-->>S: Peer snapshot
    S->>S: Size cap (300 kB) and schema check
    S->>S: transport_diagnose(local, peer)
    S-->>D: Findings + side-by-side summaries
```

Failures name the cause: connection refused, timeout, rejected token, or an unexpected HTTP status.

## Ask the AI assistant

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant C as Dashboard / panel
    participant S as Server
    participant K as Knowledge base
    participant M as Model
    U->>C: Question (+ topic, + earlier turns)
    C->>S: POST /api/assistant/stream
    S->>S: Snapshot (collected if not sent), findings, topic QoS
    S->>K: Retrieve (BM25 ± embeddings)
    S-->>C: context event (findings + sources)
    opt cloud provider
        S->>S: mask_for_cloud (node names, hostname, IPs, home paths)
    end
    S->>M: System prompt + history + grounded prompt
    S-->>C: meta event
    loop streaming
        M-->>S: text chunk
        S-->>C: token event
        C->>C: Render Markdown, link [doc-id] citations
    end
    S-->>C: done (timings)
    C->>C: Append turn to conversation history
```

## Configure RViz: plan, apply, undo

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant P as Panel
    participant S as Server
    participant R as RViz display tree
    U->>P: Request
    P->>R: Read displays, properties, Fixed Frame, TF frames
    P->>S: POST /api/rviz/plan (+ history)
    S-->>P: actions, rejected, notes
    P-->>U: Checklist
    U->>P: Apply checked
    P->>R: save() root group + Fixed Frame (undo point)
    loop each checked action
        P->>R: create display / set property / set frame
    end
    opt some properties not created yet
        P->>R: Retry pending actions every 1 s, up to 30 s
    end
    P->>P: Record results in history
    opt Undo
        U->>P: Undo
        P->>R: load() saved state
    end
```

## Dashboard overview

```mermaid
sequenceDiagram
    participant D as Dashboard
    participant S as Server
    participant C as Collector
    participant X as Capability probes
    D->>S: GET /api/v09/overview
    par
        S->>C: collect()
    and
        S->>X: ros2 doctor (cached) · docker ps · Ollama · /dev/shm
    end
    S->>S: transport_diagnose · health · summarize
    S-->>D: Everything for the first screen in one response
```
