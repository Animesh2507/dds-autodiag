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
| Documentation | `mkdocs serve` (preview), `mkdocs build --strict` (the docs check) |
| Rule reference | `python -m autodiag.rules_doc > docs/reference/rules.md` (regenerate; never edit by hand) |

## Adding a rule

1. Add the check, with evidence, a next step and a documentation key from `autodiag/knowledge.py`:
    - **Snapshot rules** go in `autodiag/transport.py` (`_issue(...)` in `transport_diagnose` or
      `_environment_rules`), with a fixture of one or two snapshots in `autodiag/validation.py`.
    - **Live topic rules** go in `autodiag/live.py` (`_qos_findings`), with a fixture in `autodiag/validation.py`
      that has `endpoints`.

    The fixture is what `selftest` runs.

2. Add a next-test hint in `autodiag/agent.py`.
3. Add the rule's row to `SECTIONS` in `autodiag/rules_doc.py` and regenerate
   [Diagnostic rules](reference/rules.md) with `python -m autodiag.rules_doc > docs/reference/rules.md`; a test fails
   if the page drifts from the code.
4. Add tests.

## Workflow

- Branch from `main` (`feat/…`, `fix/…`, `docs/…`) and open a pull request; CI must pass.
- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat(rviz): add Nav2 durability fix`,
  `fix(llm): …`, `docs: …`.
- Keep pull requests focused, with tests for behavior changes.
- AutoDiag is read-only by design. Features that change a robot's configuration or behavior need an explicit
  opt-in and user confirmation.

## Releasing

1. Make sure `main` is green (CI and Docs).
2. Set the version in `autodiag/__init__.py`, `ros2/rviz_autodiag_panel/package.xml` and `cpp/CMakeLists.txt`, and
   in the docs that name it: the badge and status line in `README.md`, the badge in `docs/index.md` and the version
   note in `docs/getting-started/installation.md`.
3. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and start a new empty `## [Unreleased]`.
4. Run a clean install from a fresh clone, then `dds-autodiag doctor`, `dds-autodiag selftest` and
   `dds-autodiag demo --no-wait`.
5. Merge, then tag: `git tag -a vX.Y.Z -m "vX.Y.Z"` and `git push origin vX.Y.Z`.
6. Create the GitHub Release from the tag, with the changelog section as release notes.
