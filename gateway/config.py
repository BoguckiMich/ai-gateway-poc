import os
from dataclasses import dataclass, field


def _keys(raw: str) -> dict[str, str]:
    out = {}
    for pair in filter(None, (p.strip() for p in raw.split(","))):
        key, _, name = pair.partition(":")
        out[key.strip()] = name.strip() or key[:6]
    return out


@dataclass
class Settings:
    upstream_url: str = field(default_factory=lambda: os.getenv("UPSTREAM_URL", "https://api.anthropic.com").rstrip("/"))
    anthropic_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    gateway_keys: dict[str, str] = field(default_factory=lambda: _keys(os.getenv("GATEWAY_KEYS", "")))
    mode: str = field(default_factory=lambda: os.getenv("GATEWAY_MODE", "enforce"))
    daily_token_limit: int = field(default_factory=lambda: int(os.getenv("DAILY_TOKEN_LIMIT", "0")))
    max_input_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_INPUT_TOKENS", "0")))
    exact_count: bool = field(default_factory=lambda: os.getenv("EXACT_TOKEN_COUNT", "0") == "1")
    audit_log: str = field(default_factory=lambda: os.getenv("AUDIT_LOG", "audit.jsonl"))
