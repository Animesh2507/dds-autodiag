# Contributing

Contributions are welcome, especially test reports from setups other than Jazzy with Fast DDS: Humble, Rolling,
Cyclone DDS, Zenoh, multi-host networks, Docker and Kubernetes.

## Ways to help

- **Try it and report.** Open an issue with your ROS distro, RMW and OS. A missed problem or a false alarm is just as
  valuable as a bug.
- **Add a diagnostic rule.** Most real ROS 2 failures follow a pattern; capture one as a rule.
- **Improve the knowledge base.** Add a curated JSON entry to `autodiag/kb/` with an official HTTPS source.
- **Extend the RViz planner.** Add display types or properties to the catalog.

## Development setup

```bash
git clone https://github.com/Animesh2507/dds-autodiag.git
cd dds-autodiag
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev,cloud,docs]"
```

| Task | Command |
|---|---|
| Python tests | `python -m pytest -q` |
| Rule self-test | `dds-autodiag selftest` |
| C++ core | `cmake -S cpp -B cpp/build && cmake --build cpp/build && ctest --test-dir cpp/build` |
| RViz panel | `cd ros2 && colcon build --packages-select rviz_autodiag_panel` |
| Documentation | `mkdocs serve` |

## Adding a rule

1. Add the check to `autodiag/transport.py`, with evidence, a next step and a documentation key from
   `autodiag/knowledge.py`.
2. Add a synthetic fixture to `autodiag/validation.py`, so `selftest` covers it.
3. Add a next-test hint in `autodiag/agent.py`.
4. Add tests, and document the rule in [Diagnostic rules](reference/rules.md).

## Workflow

- Branch from `main` (`feat/…`, `fix/…`, `docs/…`) and open a pull request; CI must pass.
- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat(rviz): add Nav2 durability fix`,
  `fix(llm): …`, `docs: …`.
- Keep pull requests focused, with tests for behaviour changes.
- AutoDiag is read-only by design. Features that change a robot's configuration or behaviour need an explicit
  opt-in and user confirmation.
