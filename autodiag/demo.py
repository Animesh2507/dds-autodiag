"""`dds-autodiag demo`: start two deliberately broken topics so AutoDiag can be tried without a robot.

Everything runs under /autodiag_demo/ with the standard `ros2` CLI, so the demo never touches the user's own
topics. Processes are stopped when the demo ends or on Ctrl+C.
"""
from __future__ import annotations
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass

PREFIX = '/autodiag_demo'


@dataclass(frozen=True)
class Scenario:
    topic: str
    title: str
    explanation: str
    expected: str
    pub_qos: tuple[str, str]   # reliability, durability
    sub_qos: tuple[str, str]


SCENARIOS = (
    Scenario(f'{PREFIX}/chatter', 'Topic visible, but no data arrives',
             'The publisher offers Best Effort; the subscriber requests Reliable. They never match.',
             'RELIABILITY_MISMATCH', ('best_effort', 'volatile'), ('reliable', 'volatile')),
    Scenario(f'{PREFIX}/map', 'Latched data missed by a late subscriber',
             'The publisher latches its data (Transient Local); the subscriber asks for Volatile, '
             'so anything published before it started is lost (the classic empty map in RViz).',
             'LATCHED_DATA_VOLATILE_SUBSCRIBER', ('reliable', 'transient_local'), ('reliable', 'volatile')),
)


def _qos_args(qos):
    return ['--qos-reliability', qos[0], '--qos-durability', qos[1]]


def commands(scenario: Scenario) -> list[list[str]]:
    """The publisher and subscriber commands for one scenario."""
    name = scenario.topic.rsplit('/', 1)[-1]
    pub = ['ros2', 'topic', 'pub', '-r', '1', '-n', f'autodiag_demo_{name}_publisher', *_qos_args(scenario.pub_qos),
           scenario.topic, 'std_msgs/msg/String', f'data: "AutoDiag demo on {scenario.topic}"']
    sub = ['ros2', 'topic', 'echo', *_qos_args(scenario.sub_qos), scenario.topic, 'std_msgs/msg/String']
    return [pub, sub]


class Demo:
    """Starts the scenario processes; use as a context manager so they are always stopped."""

    def __init__(self, scenarios=SCENARIOS):
        self.scenarios = scenarios
        self.processes: list[subprocess.Popen] = []

    def __enter__(self):
        # Ctrl+C must work even if the shell started us with SIGINT ignored, and `kill` / closing the terminal
        # must also stop the demo topics: turn SIGTERM and SIGHUP into the same clean shutdown.
        self._previous = {}
        for sig, handler in ((signal.SIGINT, signal.default_int_handler), (signal.SIGTERM, _interrupt),
                             (signal.SIGHUP, _interrupt)):
            try:
                self._previous[sig] = signal.signal(sig, handler)
            except ValueError:  # not in the main thread (e.g. tests)
                pass
        env = {**os.environ, 'ROS2CLI_DISABLE_DAEMON': '1'}
        for scenario in self.scenarios:
            for cmd in commands(scenario):
                # Own process group, so the demo can stop each ros2 process and its children cleanly.
                self.processes.append(subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                                                       stderr=subprocess.DEVNULL, start_new_session=True))
        return self

    def alive(self) -> bool:
        return all(p.poll() is None for p in self.processes)

    def __exit__(self, *exc):
        for p in self.processes:
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 5
        for p in self.processes:
            try:
                p.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
        for sig, handler in self._previous.items():
            signal.signal(sig, handler)
        return False


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def available() -> str | None:
    """None if the demo can run, else the reason it can't."""
    if not shutil.which('ros2'):
        return 'ros2 CLI not found. Install ROS 2 and source /opt/ros/<distro>/setup.bash.'
    if not os.environ.get('ROS_DISTRO'):
        return 'ROS 2 is not sourced. Run: source /opt/ros/<distro>/setup.bash'
    return None
