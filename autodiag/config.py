"""Runtime settings, read from AUTODIAG_* environment variables.

Settings are read on each call so tests and long-running servers pick up changes
without a restart-sensitive global.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

LOOPBACK_HOSTS = ('127.0.0.1', 'localhost', '::1')


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(x.strip().lower() for x in (value or '').split(',') if x.strip())


@dataclass(frozen=True)
class Settings:
    ui_token: str = ''
    agent_token: str = ''
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)
    ollama_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'qwen3:4b'
    embed_model: str = 'nomic-embed-text'
    embed_cache: Path = Path.home() / '.cache' / 'dds-autodiag' / 'embeddings'
    log_level: str = 'INFO'

    @property
    def auth_enabled(self) -> bool:
        return bool(self.ui_token)


def discovery_seconds() -> str:
    """How long --no-daemon ROS CLI queries wait for DDS discovery. Too short gives partial graphs."""
    try:
        value = float(os.environ.get('AUTODIAG_DISCOVERY_SECONDS', '2'))
    except ValueError:
        value = 2.0
    return str(min(max(value, 0.1), 10.0))


def settings() -> Settings:
    env = os.environ
    return Settings(
        ui_token=env.get('AUTODIAG_UI_TOKEN', ''),
        agent_token=env.get('AUTODIAG_AGENT_TOKEN', ''),
        allowed_hosts=_csv(env.get('AUTODIAG_ALLOWED_HOSTS')),
        ollama_url=env.get('AUTODIAG_OLLAMA_URL', 'http://127.0.0.1:11434'),
        ollama_model=env.get('AUTODIAG_OLLAMA_MODEL', 'qwen3:4b'),
        embed_model=env.get('AUTODIAG_EMBED_MODEL', 'nomic-embed-text'),
        embed_cache=Path(env.get('AUTODIAG_EMBED_CACHE', str(Path.home() / '.cache' / 'dds-autodiag' / 'embeddings'))),
        log_level=env.get('AUTODIAG_LOG_LEVEL', 'INFO').upper(),
    )


def public_settings() -> dict:
    """Configuration safe to show in the UI: never includes token values."""
    s = settings()
    return {'ui_auth_enabled': s.auth_enabled, 'agent_token_configured': bool(s.agent_token),
            'allowed_hosts': list(s.allowed_hosts), 'ollama_url': s.ollama_url,
            'ollama_model': _effective_ollama_model(), 'embed_model': s.embed_model}


def _effective_ollama_model() -> str:
    from .llm import model_for  # local import: llm depends on this module
    try:
        return model_for('ollama')
    except Exception:
        return settings().ollama_model
