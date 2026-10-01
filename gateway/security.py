"""Skanowanie promptow: wycieki sekretow i proste proby prompt injection."""
import re

RULES: list[tuple[str, re.Pattern]] = [
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("prompt_injection", re.compile(
        r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts)"
        r"|disregard (?:your|the) (?:system prompt|instructions)"
        r"|ignoruj (?:wszystkie )?(?:poprzednie|wcze[sś]niejsze) (?:instrukcje|polecenia)",
        re.I)),
]

# klucze, ktorych zawartosc to nie tekst uzytkownika (base64 obrazow, id itd.)
SKIP_KEYS = {"data", "type", "role", "id", "tool_use_id", "media_type", "name", "cache_control"}


def iter_texts(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_texts(item)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in SKIP_KEYS:
                yield from iter_texts(v)


def prompt_text(body: dict) -> str:
    return "\n".join(iter_texts([body.get("system", ""), body.get("messages", [])]))


def scan(text: str) -> list[str]:
    return sorted({name for name, rx in RULES if rx.search(text)})
