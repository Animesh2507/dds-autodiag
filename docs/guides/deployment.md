# Deployment

For daily use you'll want the server running in the background, so the RViz panel and dashboard are always ready.

## systemd user service

```bash
mkdir -p ~/.config/systemd/user
cp deploy/dds-autodiag.service ~/.config/systemd/user/
cp deploy/dds-autodiag.env.example ~/.config/dds-autodiag.env      # then edit
systemctl --user daemon-reload
systemctl --user enable --now dds-autodiag
journalctl --user -u dds-autodiag -f                               # logs
```

The unit sources ROS 2 before starting. `AUTODIAG_VENV` defaults to `%h/dds-autodiag/.venv`, the `.venv` from the
[installation guide](../getting-started/installation.md) when the repository is cloned into your home directory; set
it in the unit if you cloned elsewhere, and adjust `ROS_SETUP` for your distro. Put settings such as `ROS_DOMAIN_ID` or
`AUTODIAG_UI_TOKEN` in `~/.config/dds-autodiag.env`.

A systemd *user* service starts when you log in. To start it at boot without a login, run
`loginctl enable-linger $USER` once.

## Docker

Released images are published to the GitHub Container Registry, so you don't need to install anything:

```bash
docker run --rm --net=host --ipc=host ghcr.io/animesh2507/dds-autodiag:0.1.0          # dashboard on 127.0.0.1:8080
docker run --rm --net=host --ipc=host ghcr.io/animesh2507/dds-autodiag:0.1.0 check    # one-shot check
```

Tags: `X.Y.Z`, `X.Y` and `latest`. To build the image yourself instead:

```bash
docker build -t ros2-dds-autodiag .
docker run --rm --net=host --ipc=host ros2-dds-autodiag
```

!!! info "Why `--net=host --ipc=host`?"
    The container must see the same DDS graph and shared memory as your nodes. Without them, AutoDiag would only
    diagnose its own isolated network and IPC namespace.

The image is based on `ros:jazzy-ros-base`, builds the native core and BehaviorTree.CPP runner, runs as a non-root
user, and has a health check on `/api/healthz`.

For a local multi-RMW fleet (Cyclone, Fast DDS, Zenoh, domain and QoS faults) see `examples/lab-fleet/`
(`./run-lab.sh`). That lab uses host networking and domain **87**; it is not the production image.

## Remote access

Keep the server on `127.0.0.1` and use an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 robot
```

To listen on the network instead, a dashboard token is mandatory (`serve` refuses to start without one unless you pass
`--insecure-no-auth`, for isolated networks only). Set `AUTODIAG_AGENT_TOKEN` as well if another AutoDiag should
connect to this process under Hosts:

```bash
AUTODIAG_UI_TOKEN=$(openssl rand -hex 24) \
AUTODIAG_ALLOWED_HOSTS=robot1.local,192.168.1.20 \
dds-autodiag serve --host 0.0.0.0
```

AutoDiag has no TLS of its own; put a TLS reverse proxy in front of it for anything beyond a trusted network.

## Health and monitoring

| Endpoint | Use |
|---|---|
| `GET /api/healthz` | Liveness probe (no diagnostics run) |
| `GET /api/version` | Version and enabled features |
| `GET /api/selftest` | Tool check: every rule against its synthetic faults (27 fixtures) |
| `POST /api/live-rules` | Live rule check: every published rule on this host + optional peer + this host’s graph |
