# Command line

Everything the dashboard does for diagnosis is also available as `dds-autodiag`, with readable output by default and
`--json` for scripts.

```text
dds-autodiag doctor                          check prerequisites and print fixes
dds-autodiag check   [--peer PEER.json]      diagnose this host
                     [--snapshot FILE.json] [--transport MODE] [--report FILE.md] [--json]
dds-autodiag collect [--redact] [--salt S] [-o FILE]   save a snapshot of this host (salt default: random)
dds-autodiag compare PEER.json [OTHER.json]  compare this host (or OTHER) with PEER
dds-autodiag topics                          list topics visible in the ROS graph
dds-autodiag inspect /topic                  endpoints, QoS and incompatibilities
dds-autodiag sample  /topic [--timeout 1-15] [--reliability auto|best_effort|reliable]
dds-autodiag demo    [--no-wait]             start two broken demo topics and diagnose them
dds-autodiag selftest                        run every rule against its synthetic faults
dds-autodiag serve   [--host H] [--port P] [--open]   start the dashboard
                     [--log-level LEVEL] [--insecure-no-auth]
```

## Try it: `demo`

```bash
dds-autodiag demo
```

Starts two deliberately broken topics under `/autodiag_demo/` (a reliability mismatch and latched data with a
volatile subscriber), diagnoses them, and keeps them running so you can explore them in the dashboard or RViz.
Ctrl+C stops everything. `--no-wait` exits right after the diagnosis (exit code `0` when both problems are found),
which also makes a quick smoke test for a new installation. The demo never touches your own topics.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | No problem found |
| `1` | At least one problem (error severity; for `inspect`: any finding), a failed sample or self-test, or `doctor` not ready |
| `2` | Usage or input error, e.g. a missing file or invalid topic name |

That makes AutoDiag usable as a CI gate:

```bash
dds-autodiag check --peer robot.json --json > result.json || echo "Configuration problem found"
```

## Common tasks

=== "Is this machine ready?"

    ```bash
    dds-autodiag doctor
    ```

=== "Why is a topic silent?"

    ```bash
    dds-autodiag inspect /scan
    dds-autodiag sample /scan --reliability best_effort --timeout 5
    ```

=== "Expecting shared memory?"

    ```bash
    dds-autodiag check --transport dds_shm
    ```

=== "Write a report for a ticket"

    ```bash
    dds-autodiag check --peer robot.json --report report.md
    ```

## Transport modes

`--transport` tells the rules what you *expect*, which enables mode-specific checks:

| Mode | Use when |
|---|---|
| `auto` | Default, no assumption |
| `intra_process` | Publisher and subscriber should share one process |
| `dds_shm` | DDS shared memory between processes or containers on one host |
| `dds_udp` / `dds_tcp` | Network transport between hosts |

## Starting the server

```bash
dds-autodiag serve                         # 127.0.0.1:8080
dds-autodiag serve --port 8090 --open
AUTODIAG_UI_TOKEN=$(openssl rand -hex 24) AUTODIAG_ALLOWED_HOSTS=<hostname-or-ip> \
  dds-autodiag serve --host 0.0.0.0
```

On a non-loopback address the dashboard token is mandatory: `serve` refuses to start without `AUTODIAG_UI_TOKEN`
unless you pass `--insecure-no-auth` (isolated networks only). `AUTODIAG_ALLOWED_HOSTS` lists the hostnames or IPs
clients use; other `Host` headers are rejected. See [Security model](../concepts/security.md).

!!! note "Pre-1.0 flags"
    The old flags (`--collect`, `--compare`, `--health`, `--transport`) still work, so existing scripts keep
    running.
