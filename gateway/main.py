import hashlib
import json
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .config import Settings
from .security import prompt_text, scan
from .tokens import count_exact, estimate
from .usage import Usage

DROP_REQ = {"host", "content-length", "accept-encoding", "connection", "x-api-key", "authorization"}
DROP_RESP = {"content-length", "content-encoding", "transfer-encoding", "connection"}


def anthropic_error(status: int, etype: str, message: str) -> JSONResponse:
    """Bledy w formacie Anthropic, zeby SDK klienta zachowywalo sie naturalnie."""
    return JSONResponse(
        {"type": "error", "error": {"type": etype, "message": f"[DRO AI Gateway] {message}"}},
        status_code=status,
    )


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    cfg = settings or Settings()
    usage = Usage(cfg.audit_log)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http = httpx.AsyncClient(
            base_url=cfg.upstream_url, transport=transport, timeout=httpx.Timeout(600, connect=10)
        )
        yield
        await app.state.http.aclose()

    app = FastAPI(title="DRO AI Gateway", lifespan=lifespan)
    app.state.usage = usage

    def authenticate(request: Request) -> tuple[str | None, str | None, dict]:
        """Zwraca (klient, blad, naglowki auth do upstreamu)."""
        auth = request.headers.get("authorization", "")
        key = request.headers.get("x-api-key") or (auth[7:] if auth.lower().startswith("bearer ") else "")
        if cfg.gateway_keys:
            client = cfg.gateway_keys.get(key)
            if not client:
                return None, "Nieprawidlowy klucz gateway", {}
            if not cfg.anthropic_key:
                return None, "Gateway nie ma skonfigurowanego ANTHROPIC_API_KEY", {}
            return client, None, {"x-api-key": cfg.anthropic_key}
        # passthrough: klient uzywa wlasnych danych dostepowych Anthropic
        if not key:
            return None, "Brak klucza API", {}
        headers = {k: request.headers[k] for k in ("x-api-key", "authorization") if k in request.headers}
        return "anon-" + hashlib.sha256(key.encode()).hexdigest()[:8], None, headers

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "mode": cfg.mode}

    @app.get("/admin/usage")
    async def admin_usage():
        return {"date": usage.today(), "daily_limit": cfg.daily_token_limit, "tokens_by_client": usage.summary()}

    @app.api_route("/v1/{path:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH"])
    async def proxy(path: str, request: Request):
        client, err, auth_headers = authenticate(request)
        if err:
            return anthropic_error(401, "authentication_error", err)

        headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP_REQ} | auth_headers
        raw = await request.body()
        meta = {"path": f"/v1/{path}", "model": None}
        stream = False
        is_messages = request.method == "POST" and path == "messages"

        if is_messages:
            try:
                body = json.loads(raw)
            except ValueError:
                return anthropic_error(400, "invalid_request_error", "Niepoprawny JSON")
            meta["model"] = body.get("model")
            stream = bool(body.get("stream"))

            text = prompt_text(body)
            findings = scan(text)
            if findings:
                blocked = cfg.mode == "enforce"
                usage.record(client, **meta, event="blocked" if blocked else "flagged", findings=findings)
                if blocked:
                    return anthropic_error(
                        400, "invalid_request_error",
                        f"Zapytanie zablokowane przez polityke bezpieczenstwa: {', '.join(findings)}",
                    )

            input_est = await count_exact(app.state.http, headers, body) if cfg.exact_count else None
            if input_est is None:
                input_est = estimate(text)
            meta["input_estimate"] = input_est

            if cfg.max_input_tokens and input_est > cfg.max_input_tokens:
                usage.record(client, **meta, event="blocked", findings=["max_input_tokens"])
                return anthropic_error(
                    400, "invalid_request_error",
                    f"Zapytanie ma ~{input_est} tokenow, limit to {cfg.max_input_tokens}",
                )
            if cfg.daily_token_limit and usage.used(client) + input_est > cfg.daily_token_limit:
                usage.record(client, **meta, event="blocked", findings=["daily_budget"])
                return anthropic_error(429, "rate_limit_error", "Dzienny limit tokenow wyczerpany")

        started = time.monotonic()
        upstream_req = app.state.http.build_request(
            request.method, "/v1/" + path, headers=headers, params=request.query_params, content=raw
        )
        try:
            upstream = await app.state.http.send(upstream_req, stream=True)
        except httpx.HTTPError as e:
            usage.record(client, **meta, event="upstream_error", error=type(e).__name__)
            return anthropic_error(502, "api_error", f"Blad polaczenia z Anthropic: {type(e).__name__}")

        resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in DROP_RESP}

        def log(u: dict):
            usage.record(
                client, **meta, event="request", status=upstream.status_code,
                input_tokens=u.get("input", 0), output_tokens=u.get("output", 0),
                cache_read_tokens=u.get("cache_read", 0), cache_write_tokens=u.get("cache_write", 0),
                latency_ms=int((time.monotonic() - started) * 1000), stream=stream,
            )

        if stream and upstream.status_code == 200:
            async def relay():
                u, buf = {}, b""
                try:
                    async for chunk in upstream.aiter_raw():
                        yield chunk
                        buf += chunk
                        *lines, buf = buf.split(b"\n")
                        for line in lines:
                            _parse_sse_usage(line, u)
                finally:
                    await upstream.aclose()
                    log(u)

            return StreamingResponse(relay(), status_code=200, headers=resp_headers)

        content = await upstream.aread()
        await upstream.aclose()
        if is_messages:
            u = {}
            try:
                _add_usage(u, json.loads(content).get("usage") or {})
            except (ValueError, AttributeError):
                pass
            log(u)
        return Response(content, status_code=upstream.status_code, headers=resp_headers)

    return app


def _add_usage(u: dict, usage: dict):
    # message_start niesie input, message_delta skumulowane output - nadpisujemy tylko podane pola
    if "input_tokens" in usage:
        u["input"] = usage["input_tokens"]
    if "output_tokens" in usage:
        u["output"] = usage["output_tokens"]
    if "cache_read_input_tokens" in usage:
        u["cache_read"] = usage["cache_read_input_tokens"] or 0
    if "cache_creation_input_tokens" in usage:
        u["cache_write"] = usage["cache_creation_input_tokens"] or 0


def _parse_sse_usage(line: bytes, u: dict):
    if not line.startswith(b"data:"):
        return
    try:
        event = json.loads(line[5:])
    except ValueError:
        return
    if event.get("type") == "message_start":
        _add_usage(u, event["message"].get("usage") or {})
    elif event.get("type") == "message_delta":
        _add_usage(u, event.get("usage") or {})
