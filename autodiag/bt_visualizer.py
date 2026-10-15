"""BT visualization: native BehaviorTree.CPP runs or clearly labelled simulated trace."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess

TREE = {"id":"root", "label":"DDS Diagnosis", "kind":"Sequence", "children":[
    {"id":"collect","label":"Collect Evidence","kind":"Action", "children":[]},
    {"id":"qos","label":"Diagnose QoS","kind":"Action", "children":[]},
    {"id":"report","label":"Generate Report","kind":"Action", "children":[]}
]}


def _binary():
    root = Path(__file__).resolve().parent.parent
    configured = os.getenv("AUTODIAG_BT_BINARY")
    p = Path(configured) if configured else root / "cpp" / "build" / "autodiag_bt"
    return p if p.is_file() and os.access(p, os.X_OK) else None


def simulate(fault=False):
    # Explicit simulation: not collected from a real ROS installation.
    seq = [(n, s) for n in ("root", "collect", "qos", "report") for s in ("RUNNING", "SUCCESS")]
    events = [{"event":"bt_transition", "seq": i, "node": n, "status": s}
              for i, (n,s) in enumerate(seq, 1)]
    events.append({"event":"diagnosis", "issue_count": 1 if fault else 0})
    return events


def run_trace(fault=False):
    binary = _binary()
    if binary is None:
        return {"source":"simulated", "warning":"BehaviorTree.CPP executable unavailable. This is a simulated animation, not a live BT run.",
                "tree": TREE, "events": simulate(fault), "diagnosis": {"issue_count": 1 if fault else 0}}
    try:
        process = subprocess.run([str(binary)] + (["--fault"] if fault else []),
                                 capture_output=True, text=True, timeout=8, check=False)
        if process.returncode != 0:
            raise RuntimeError("native BT runner exited unsuccessfully")
        events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith('{')]
        diagnosis = next((e for e in events if e.get('event') == 'diagnosis'), {})
        if not any(e.get('event') == 'bt_transition' for e in events):
            raise RuntimeError("native BT runner emitted no transitions")
        return {"source":"native", "warning":"BT executed on sample endpoint data, not live ROS traffic.",
                "tree": TREE, "events": events, "diagnosis": diagnosis}
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return {"source":"error", "warning":f"Native BT execution failed: {type(exc).__name__}",
                "tree":TREE, "events":[], "diagnosis":{}}
