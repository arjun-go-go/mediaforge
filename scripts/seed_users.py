"""Seed the database with demo tenants and demo users.

Usage:
    python scripts/seed_users.py

Creates three tenants (Starter / Pro / Enterprise) and one user per tenant:
    starter@mediaforge.dev    / Starter123!
    pro@mediaforge.dev        / Pro123!
    enterprise@mediaforge.dev / Enterprise123!

Passwords are bcrypt-hashed (12 rounds). Idempotent — re-running skips
tenants/users that already exist.
"""

import asyncio
import os
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Fallback JWT secret so settings validation doesn't crash in scripts.
os.environ.setdefault("JWT_SECRET", "seed-script")

from mediaforge.auth.password import hash_password  # noqa: E402
from mediaforge.config import clear_settings_cache, get_settings  # noqa: E402
from mediaforge.db.engine import create_async_engine  # noqa: E402
from mediaforge.db.tables import Base  # noqa: E402
from mediaforge.db.tenant_store import TenantStore  # noqa: E402
from mediaforge.db.user_store import UserStore  # noqa: E402
from mediaforge.models.tenant import TenantPlan  # noqa: E402


DEMO_USERS = [
    {
        "plan": TenantPlan.starter,
        "name": "Starter",
        "email": "starter@mediaforge.dev",
        "password": "Starter123!",
        "display_name": "Starter Demo",
    },
    {
        "plan": TenantPlan.pro,
        "name": "Pro",
        "email": "pro@mediaforge.dev",
        "password": "Pro123!",
        "display_name": "Pro Demo",
    },
    {
        "plan": TenantPlan.enterprise,
        "name": "Enterprise",
        "email": "enterprise@mediaforge.dev",
        "password": "Enterprise123!",
        "display_name": "Enterprise Demo",
    },
]


async def main() -> None:
    clear_settings_cache()
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    # Ensure all tables exist (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    tenant_store = TenantStore(engine)
    user_store = UserStore(engine)

    for entry in DEMO_USERS:
        existing_tenants = await tenant_store.list_tenants()
        tenant = next((t for t in existing_tenants if t.name == entry["name"]), None)
        if tenant is None:
            tenant = await tenant_store.create(name=entry["name"], plan=entry["plan"])
            print(f"[+] tenant created: {tenant.name} ({tenant.tenant_id})")
        else:
            print(f"[=] tenant exists:  {tenant.name} ({tenant.tenant_id})")

        existing_user = await user_store.get_by_email(entry["email"])
        if existing_user is None:
            pw_hash = hash_password(entry["password"])
            user = await user_store.create(
                tenant_id=tenant.tenant_id,
                email=entry["email"],
                password_hash=pw_hash,
                display_name=entry["display_name"],
            )
            print(f"[+] user created:   {user.email} (user_id={user.user_id})")
        else:
            print(f"[=] user exists:    {entry['email']}")

    # Set allow_self_signup_tenant_id hint (manual step)
    print()
    print("Demo seed complete. To enable self-signup, add to .env:")
    print(f"  ALLOW_SELF_SIGNUP_TENANT_ID=<tenant_id of any existing tenant>")
    print()
    print("Login with:")
    for e in DEMO_USERS:
        print(f"  {e['email']}  /  {e['password']}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
