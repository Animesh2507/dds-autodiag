"""Read-only C++ diagnostic process bridge; caller supplies endpoint descriptions.
This intentionally does not execute arbitrary user commands or shell strings.
"""
import json
import os
import subprocess
from pathlib import Path


def binary_path():
    configured = os.getenv('AUTODIAG_CPP_BINARY')
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / 'cpp' / 'build' / 'autodiag_core_cli'


def check_endpoint(a: dict, b: dict):
    binary = binary_path()
    if not binary.is_file():
        return {'state': 'unavailable', 'reason': 'Build the portable C++ core first (cmake -S cpp -B cpp/build && cmake --build cpp/build).'}
    def get(src, key):
        value = str(src.get(key, ''))
        if len(value) > 256 or '\x00' in value:
            raise ValueError('Invalid endpoint field')
        return value
    args = [str(binary)] + [get(a, 'domain'), get(b, 'domain'), get(a, 'topic'), get(b, 'topic'),
                            get(a, 'type'), get(b, 'type'), get(a, 'reliability').lower(),
                            get(b, 'reliability').lower(), get(a, 'durability').lower(),
                            get(b, 'durability').lower(), get(a, 'vendor'), get(b, 'vendor')]
    result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=True)
    return json.loads(result.stdout)
