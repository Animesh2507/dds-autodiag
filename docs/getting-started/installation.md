# Installation

DDS AutoDiag is a Python package with an optional RViz2 plugin and an optional native C++ core. Start with the
Python package; add the rest when you need it.

!!! info "Version 0.1.0"
    This documentation describes **DDS AutoDiag 0.1.0**, the upcoming first public release. Check your installed
    version with `dds-autodiag --version`. See the [Changelog](../changelog.md) for what's included.

## Requirements

| | Required | Notes |
|---|---|---|
| OS | Linux | Tested on Ubuntu 24.04 |
| Python | 3.10+ | Tested on 3.12 |
| `python3-venv` | Required | `sudo apt install python3-venv`; Ubuntu and ROS 2 don't install it by default |
| ROS 2 | For live inspection | Tested on **Jazzy**. Without ROS 2, snapshot comparison, reports and the tool check (synthetic self-test) still work |
| `iproute2` | Recommended | Network interface checks (`ip -j addr`) |
| Docker CLI | Optional | Lists local containers |
| Ollama | Optional | Local, offline AI explanations |

## 1. Install the package

ROS 2 must be **sourced in the same shell** that creates the virtual environment and later runs AutoDiag.

```bash
sudo apt install python3-venv        # once
source /opt/ros/jazzy/setup.bash
git clone https://github.com/Animesh2507/dds-autodiag.git
cd dds-autodiag
python3 -m venv --system-site-packages .venv   # (1)!
source .venv/bin/activate
pip install .
```

1. `--system-site-packages` lets the virtual environment see ROS 2's own Python packages.

Optional extras:

=== "Claude support"

    ```bash
    pip install ".[cloud]"      # official Anthropic SDK
    ```

    ChatGPT, Gemini and OpenAI-compatible providers need no extra packages.

=== "Development"

    ```bash
    pip install -e ".[dev,cloud]"
    python -m pytest -q
    ```

=== "Documentation"

    ```bash
    pip install ".[docs]"
    mkdocs serve                 # http://127.0.0.1:8000
    ```

## 2. Check the machine

```bash
dds-autodiag doctor
```

`doctor` lists every prerequisite with a fix for anything missing. Required items must pass; optional ones (Docker,
Ollama, native core) only unlock extra features.

!!! tip "Seeing `✖ ROS 2 environment sourced`?"
    `ROS_DISTRO` is not set in this shell. Run `source /opt/ros/jazzy/setup.bash` in the same
    terminal, then start AutoDiag again.

## 3. Optional components

=== "RViz2 panel"

    ```bash
    cd ros2
    colcon build --packages-select rviz_autodiag_panel
    source install/setup.bash
    rviz2
    ```

    Then **Panels → Add New Panel → rviz_autodiag_panel → AutoDiag**. See the
    [RViz2 panel guide](../guides/rviz-panel.md).

=== "Local AI (Ollama)"

    ```bash
    ollama pull qwen3:4b-instruct     # fast answers
    ollama pull nomic-embed-text      # optional semantic search
    ```

    AutoDiag picks `qwen3:4b-instruct` automatically when installed. See [AI providers](../guides/ai-providers.md).

=== "Native C++ core"

    ```bash
    cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
    cmake --build cpp/build
    ctest --test-dir cpp/build
    ```

    With `ros-jazzy-behaviortree-cpp` installed, this also builds the BehaviorTree.CPP trace runner.

=== "Docker"

    ```bash
    docker build -t ros2-dds-autodiag .
    docker run --rm --net=host --ipc=host ros2-dds-autodiag
    ```

    See [Deployment](../guides/deployment.md).

Next: [Quick start](quickstart.md) :material-arrow-right:
