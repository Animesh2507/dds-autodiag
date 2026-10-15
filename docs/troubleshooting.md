# Troubleshooting

??? question "\"ros2 CLI found, but the ROS 2 environment is not sourced\""
    Run `source /opt/ros/<distro>/setup.bash` **in the same terminal** that starts AutoDiag, then restart it. For
    the systemd service, check `ROS_SETUP` in the unit file.

??? question "Node and topic counts change between refreshes"
    DDS discovery takes time, and graph queries only wait a limited time. Increase `AUTODIAG_DISCOVERY_SECONDS`,
    for example to `4`.

??? question "Topic is visible but \"No message within N s\""
    1. The publisher may simply be idle. Check with `ros2 topic hz`.
    2. Try the other reliability setting in **Read one sample**; a QoS mismatch shows up immediately.
    3. Between containers on one host, shared memory needs `--ipc=host` or a shared IPC namespace.

    See [Debugging "topic visible, no data"](concepts/diagnosis.md#debugging-topic-visible-no-data).

??? question "RViz display stays empty"
    Open the AutoDiag panel's **Topic** tab: the display's topic is listed first, with ⚠ if RViz reports a
    problem. **Inspect** shows QoS mismatches. Or ask **Configure RViz** *"my laser scan shows nothing"*, and it
    adds the diagnosed fix.

??? question "Panel says \"Cannot reach the AutoDiag server\""
    Start the server with `dds-autodiag serve` and check the URL in the panel (default `http://127.0.0.1:8080`).
    For a permanent setup, use the [systemd service](guides/deployment.md#systemd-user-service).

??? question "Lots of `GET /api/... 404` lines in the server log"
    Usually another application's browser tab polling the same address and port. Close that tab, or run AutoDiag
    on another port with `--port 8090`.

??? question "\"Host header not allowed\""
    Add the hostname you use to `AUTODIAG_ALLOWED_HOSTS`, for example `robot1.local`.

??? question "Docker section says permission denied"
    Add your user to the `docker` group, or ignore it: Docker is optional.

??? question "Local AI unreachable or slow"
    - Unreachable: `ollama serve`, then `ollama pull qwen3:4b-instruct`. Documentation search works without it.
    - Slow: install `qwen3:4b-instruct` (direct answers instead of long reasoning) and check `ollama ps` for CPU vs
      GPU.

??? question "Claude: \"the reply could not be processed locally\""
    A local library problem, not a network one. Update the package (`pip install -U ".[cloud]"`) and check the
    server log for the named error.

??? question "Configure RViz returns \"No changes proposed\""
    Read the grey summary: it explains why, and lists rejected suggestions with reasons. Describe the result you
    want concretely, for example *"Add a LaserScan display on /scan"*. Display types from extra plugins aren't
    supported yet.

## Still stuck?

Run `dds-autodiag check --report report.md` and open an issue with the report attached. Use `--redact` when
collecting snapshots to share.
