import json
import time
import uuid

from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mediaforge.config import get_settings
from mediaforge.logging import trace_id_var

# Paths that carry binary/streaming bodies — skip body logging for these
_SKIP_BODY_PATHS = {"/outputs"}
_SKIP_BODY_PREFIXES = ("/outputs/",)

# Truncate large bodies to this many chars in the log
_BODY_MAX_CHARS = 2000


def _should_log_body(path: str) -> bool:
    if path in _SKIP_BODY_PATHS:
        return False
    for prefix in _SKIP_BODY_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


def _truncate(s: str, n: int = _BODY_MAX_CHARS) -> str:
    return s if len(s) <= n else s[:n] + f"…(+{len(s)-n})"


def _fmt_body(raw: bytes) -> str:
    if not raw:
        return ""
    try:
        obj = json.loads(raw)
        # Redact sensitive fields
        for key in ("password", "password_hash", "token", "access_token", "refresh_token"):
            if key in obj:
                obj[key] = "***"
        return _truncate(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return _truncate(raw.decode("utf-8", errors="replace"))


class ObservabilityMiddleware:
    """Pure-ASGI observability middleware.

    Avoids `BaseHTTPMiddleware` so long-lived streaming responses (SSE from
    /api/v1/agent/chat) don't hit its internal receive-queue bug that raises
    `RuntimeError: Unexpected message received: http.request`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        trace_id = (
            next(
                (v.decode() for k, v in headers.items() if k == b"x-trace-id"),
                None,
            )
            or str(uuid.uuid4())
        )
        trace_id_var.set(trace_id)

        scope.setdefault("state", {})
        scope["state"]["trace_id"] = trace_id

        path: str = scope.get("path", "")
        method: str = scope.get("method", "")
        query: str = scope.get("query_string", b"").decode()
        log_body = _should_log_body(path)

        # ── Capture request body ──────────────────────────────────────────────
        req_body = b""
        req_body_chunks: list[bytes] = []

        async def receive_wrapper() -> Message:
            nonlocal req_body
            msg = await receive()
            if msg["type"] == "http.request" and log_body:
                req_body_chunks.append(msg.get("body", b""))
                if not msg.get("more_body", False):
                    req_body = b"".join(req_body_chunks)
            return msg

        # ── Capture response body ─────────────────────────────────────────────
        start = time.monotonic()
        status_code = 500
        resp_body_chunks: list[bytes] = []
        is_streaming = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, is_streaming
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                raw_headers = list(message.get("headers") or [])
                settings = get_settings()
                raw_headers.append((b"x-trace-id", trace_id.encode()))
                raw_headers.append(
                    (b"x-langsmith-project", settings.langsmith_project.encode())
                )
                # Detect SSE / streaming — don't buffer the body
                for k, v in raw_headers:
                    if k == b"content-type" and b"event-stream" in v:
                        is_streaming = True
                message = {**message, "headers": raw_headers}
            elif message["type"] == "http.response.body" and log_body and not is_streaming:
                resp_body_chunks.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            elapsed = time.monotonic() - start
            resp_body = b"".join(resp_body_chunks) if not is_streaming else b""

            # Build log extras
            parts = [f"{method} {path}"]
            if query:
                parts.append(f"?{query}")
            parts.append(f"→ {status_code}  ({elapsed:.3f}s)")

            req_str = _fmt_body(req_body) if req_body else ""
            resp_str = _fmt_body(resp_body) if resp_body else ""

            if req_str:
                parts.append(f"\n  REQ  {req_str}")
            if resp_str:
                parts.append(f"\n  RESP {resp_str}")
            if is_streaming:
                parts.append("\n  RESP [SSE stream]")

            log_level = "WARNING" if status_code >= 400 else "INFO"
            logger.log(log_level, "{}", " ".join(parts))
