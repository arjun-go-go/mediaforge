from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from mediaforge.auth.tenant import TenantResolver


def key_func(request: Request) -> str:
    api_key = request.headers.get("X-Api-Key")
    if api_key:
        return f"rate:{api_key}"
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return f"rate:{auth[7:]}"
    return f"rate:{get_remote_address(request)}"


limiter = Limiter(key_func=key_func)


def get_limit_for_tenant(api_key: str) -> str:
    resolver = TenantResolver()
    tenant = resolver.get_tenant(api_key)
    mapping = {"starter": "10/minute", "pro": "100/minute", "enterprise": "10000/minute"}
    return mapping[tenant.plan.value]
