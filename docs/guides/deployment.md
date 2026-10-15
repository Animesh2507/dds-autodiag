# Deployment

For daily use you'll want the server running in the background, so the RViz panel and dashboard are always ready.

## systemd user service

```bash
cp deploy/dds-autodiag.service ~/.config/systemd/user/
cp deploy/dds-autodiag.env.example ~/.config/dds-autodiag.env      # then edit
systemctl --user daemon-reload
systemctl --user enable --now dds-autodiag
journalctl --user -u dds-autodiag -f                               # logs
```

The unit sources ROS 2 before starting. Adjust `ROS_SETUP` and `AUTODIAG_VENV` in the unit if your paths differ, and
put settings such as `ROS_DOMAIN_ID` or `AUTODIAG_UI_TOKEN` in `~/.config/dds-autodiag.env`.

## Docker

```bash
docker build -t ros2-dds-autodiag .
docker run --rm --net=host --ipc=host ros2-dds-autodiag            # dashboard on 127.0.0.1:8080
docker run --rm --net=host --ipc=host ros2-dds-autodiag check      # one-shot check
```

!!! info "Why `--net=host --ipc=host`?"
    The container must see the same DDS graph and shared memory as your nodes. Without them, AutoDiag would only
    diagnose its own isolated network and IPC namespace.

The image is based on `ros:jazzy-ros-base`, builds the native core and BehaviorTree.CPP runner, runs as a non-root
user, and has a health check on `/api/healthz`.

## Remote access

Keep the server on `127.0.0.1` and use an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 robot
```

To listen on the network instead, a token is mandatory:

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
| `GET /api/selftest` | All rules against synthetic faults |
