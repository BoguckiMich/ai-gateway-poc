import httpx


def estimate(text: str) -> int:
    """Heurystyka ~3.5 znaku/token (zaniza dla kodu, ale wystarcza do wstepnej kontroli)."""
    return int(len(text) / 3.5) + 1


async def count_exact(client: httpx.AsyncClient, headers: dict, body: dict) -> int | None:
    """Darmowy endpoint Anthropic /v1/messages/count_tokens. None przy bledzie."""
    payload = {k: body[k] for k in ("model", "messages", "system", "tools", "tool_choice", "thinking") if k in body}
    try:
        r = await client.post("/v1/messages/count_tokens", json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()["input_tokens"]
    except (httpx.HTTPError, KeyError, ValueError):
        pass
    return None
