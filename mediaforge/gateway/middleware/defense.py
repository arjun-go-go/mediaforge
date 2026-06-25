import json
import re
import unicodedata

from loguru import logger
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class DefenseResult:
    def __init__(self, blocked: bool, reason: str = ""):
        self.blocked = blocked
        self.reason = reason


class PromptInjectionDefender:
    PATTERNS = [
        r"ignore previous instructions",
        r"ignore all prior",
        r"reveal (?:your|system) (?:prompt|instructions|secrets)",
        r"you are now .* mode",
        r"\{\{.*\}\}",
        r"<%.*%>",
    ]
    CONTROL_CHARS = set(chr(i) for i in range(32)) - {"\n", "\r", "\t"}

    def __init__(self):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in self.PATTERNS]

    def scan(self, obj) -> DefenseResult:
        text = self._extract_text(obj)

        # L1: normalize unicode and remove control chars
        cleaned = unicodedata.normalize("NFKC", text)
        cleaned = "".join(ch for ch in cleaned if ch not in self.CONTROL_CHARS)

        # L2: denylist patterns
        for pattern in self.patterns:
            if pattern.search(cleaned):
                return DefenseResult(blocked=True, reason=f"matched pattern: {pattern.pattern}")

        # L3: structural anomaly (nested injection markers)
        if cleaned.count("{") > 10 or cleaned.count("<") > 20:
            return DefenseResult(blocked=True, reason="structural anomaly")

        # L4: length sanity
        if len(cleaned) > 8000:
            return DefenseResult(blocked=True, reason="input too long")

        return DefenseResult(blocked=False)

    def _extract_text(self, obj) -> str:
        parts = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                parts.append(str(k))
                parts.append(self._extract_text(v))
        elif isinstance(obj, list):
            for item in obj:
                parts.append(self._extract_text(item))
        else:
            parts.append(str(obj))
        return " ".join(parts)


class PromptInjectionMiddleware:
    """Pure-ASGI prompt-injection gate.

    Replaces the old `BaseHTTPMiddleware` version, which broke SSE streams:
    Starlette's `BaseHTTPMiddleware` uses an internal `anyio` receive queue
    that misroutes late `http.request` / `http.disconnect` messages when the
    downstream response is a long-lived `StreamingResponse` (such as
    `/api/v1/agent/chat`), raising `RuntimeError: Unexpected message received`.

    This version buffers only the JSON body, runs the scan, then forwards the
    body to the inner app as one or two `http.request` messages. If the scan
    fails, a `JSONResponse(400)` is sent and the inner app is never called.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.defender = PromptInjectionDefender()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        # Buffer the request body.
        body_chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                # e.g. http.disconnect before body arrived — bail out.
                return
            body_chunks.append(message.get("body", b"") or b"")
            more = message.get("more_body", False)
        body = b"".join(body_chunks)

        # Run the scan on JSON bodies only.
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None

        if payload is not None:
            result = self.defender.scan(payload)
            if result.blocked:
                logger.warning(
                    "Prompt injection blocked: {} path={} body_len={}",
                    result.reason,
                    scope.get("path", ""),
                    len(body),
                )
                response = JSONResponse(
                    status_code=400,
                    content={"detail": f"Prompt injection blocked: {result.reason}"},
                )
                await response(scope, receive, send)
                return

        # Forward the buffered body as a single http.request message, then
        # pass subsequent messages (e.g. http.disconnect) straight through.
        body_sent = False

        async def receive_wrapper() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, receive_wrapper, send)
