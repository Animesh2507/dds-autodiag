# RViz planner

**Module:** `rviz_agent.py` · **Endpoint:** `POST /api/rviz/plan`

The planner turns a plain-language request into a list of RViz actions that are safe to apply. The model only
*proposes*; the planner decides what reaches the user.

--8<-- "assets/diagrams/configure-rviz.svg"

## Pipeline

```mermaid
flowchart TB
    req["Request + panel state<br/>(displays, Fixed Frame, TF frames, history)"]
    req --> ctx
    subgraph ctx["1 · Build context (parallel)"]
        t["Live topics + types<br/>(cached 15 s)"]
        q["QoS facts per display topic<br/>(up to 6 inspected)"]
    end
    ctx --> prompt["2 · Compact text prompt<br/>state · topics · relevant display types · diagnosed problems · history"]
    prompt --> model["3 · complete_json()<br/>PLAN_SCHEMA enforced"]
    model --> validate["4 · validate()<br/>reject impossible actions with reasons"]
    validate --> complete["5 · _complete()<br/>add dependencies + diagnosed fixes, dedupe"]
    complete --> out["Plan: actions · rejected · notes"]
```

## The action vocabulary

The model can only use seven actions, each with the same flat schema (unused fields are empty strings):

| Action | Required fields |
|---|---|
| `add_display` | `display_type`, `topic` (empty for TF, Grid, Axes), `display` (name) |
| `remove_display` | `display` |
| `set_topic` | `display`, `topic` |
| `set_property` | `display`, `property`, `value` |
| `set_enabled` | `display`, `value` (`true`/`false`) |
| `rename_display` | `display`, `value` |
| `set_fixed_frame` | `frame` |

A flat schema is easy for small local models to follow and works with every provider's structured-output mode.

## Display catalog

`CATALOG` maps 24 RViz2 display types to their `rviz_default_plugins` class id, accepted message types, topic
property, and the settable properties with allowed values. Only types that matter for the current system are put into
the prompt: types already in use, common ones, those matching visible topics, and topic-less types (TF, Grid, Axes).
This keeps prompts small, which matters for local models. For cloud providers the finished prompt is passed through
`redact.mask_for_cloud()`, which replaces this machine's hostname, IP addresses and home paths with tokens.

## Validation

| Check | Result |
|---|---|
| Unknown action or display type | Rejected with reason |
| Target display doesn't exist | Rejected, unless it's added earlier in the same plan; names match loosely (`laser_scan` = `LaserScan`) |
| Topic exists with the wrong message type | Rejected, naming the topic's type (and, on `add_display`, the types the display accepts) |
| Topic doesn't exist (yet) | Allowed, marked **not publishing yet** |
| Missing topic on `add_display` | The single live topic of that type, else a conventional default (`/scan`, `/points`, …) |
| Property unknown to the display | Rejected when an existing display reported its properties and the name is in neither those nor the catalog; any property passes for a display added in the same plan. Nested paths like `Color Transformer/Axis` are normalized |
| Frame not in the TF tree | Allowed with a note |

## Deterministic completion

After validation, `_complete()` adds what the model tends to miss, each marked as automatic:

- **Dependencies:** `Axis` needs `Color Transformer: AxisColor`; `Color` needs `FlatColor`.
- **Diagnosed QoS fixes:** if a display requests Reliable from a Best Effort publisher (or Transient Local from a
  Volatile one), the fix is added, and a model-proposed "disable this display" is unchecked. A Volatile display on a
  latched (Transient Local) publisher, which misses data published before it started, gets Transient Local.
- **Requested frame:** if the request mentions "frame" and exactly one TF frame name from the tree appears in it,
  that frame is applied when the model skipped it.
- **Deduplication:** repeated settings of the same property keep the first.

## Conversation context

The last four turns are summarized for the model, including what *really* happened: applied, skipped by the user,
failed (with reason), waiting for data, or undone. The live context remains the source of truth.
