import json

import httpx
import pytest

from gateway.config import Settings
from gateway.main import create_app

SSE = (
    b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":12,"output_tokens":1}}}\n\n'
    b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":7}}\n\n'
    b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
)

MSG = {"model": "m", "max_tokens": 10, "messages": [{"role": "user", "content": "czesc"}]}


def upstream(request: httpx.Request) -> httpx.Response:
    assert request.headers["x-api-key"] == "sk-ant-real"
    body = json.loads(request.content)
    if body.get("stream"):
        return httpx.Response(200, stream=httpx.ByteStream(SSE), headers={"content-type": "text/event-stream"})
    return httpx.Response(200, json={"id": "m", "usage": {"input_tokens": 10, "output_tokens": 5}})


@pytest.fixture
async def gw(tmp_path, request):
    limit = getattr(request, "param", 0)
    cfg = Settings(anthropic_key="sk-ant-real", gateway_keys={"k1": "alice"},
                   audit_log=str(tmp_path / "a.jsonl"), daily_token_limit=limit)
    app = create_app(cfg, transport=httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw",
                                     headers={"x-api-key": "k1"}) as c:
            yield app, c


async def test_forward_and_count(gw):
    app, c = gw
    r = await c.post("/v1/messages", json=MSG)
    assert r.status_code == 200
    assert app.state.usage.used("alice") == 15


async def test_stream_usage(gw):
    app, c = gw
    r = await c.post("/v1/messages", json=MSG | {"stream": True})
    assert b"message_stop" in r.content
    assert app.state.usage.used("alice") == 19


async def test_blocks_secret(gw):
    _, c = gw
    bad = MSG | {"messages": [{"role": "user", "content": "klucz AKIAABCDEFGHIJKLMNOP"}]}
    r = await c.post("/v1/messages", json=bad)
    assert r.status_code == 400 and "aws_access_key" in r.json()["error"]["message"]


async def test_bad_key(gw):
    _, c = gw
    assert (await c.post("/v1/messages", json=MSG, headers={"x-api-key": "zly"})).status_code == 401


@pytest.mark.parametrize("gw", [15], indirect=True)
async def test_budget(gw):
    _, c = gw
    assert (await c.post("/v1/messages", json=MSG)).status_code == 200
    assert (await c.post("/v1/messages", json=MSG)).status_code == 429
