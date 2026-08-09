from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

def key_func(request: Request) -> str:
    api_key = request.headers.get("X-Api-Key")
    if api_key:
        return f"rate:{api_key}"
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return f"rate:{auth[7:]}"
    return f"rate:{get_remote_address(request)}"


limiter = Limiter(key_func=key_func)
