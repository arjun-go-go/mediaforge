"""Seed the database with one operator-provided tenant and user.

Usage:
    Set SEED_USER_EMAIL and SEED_USER_PASSWORD in the process environment, then:
    python scripts/seed_users.py

The password is read at runtime, bcrypt-hashed, and never stored in source.
Re-running with the same email is idempotent.
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


async def main() -> None:
    email = os.environ.get("SEED_USER_EMAIL", "").strip().lower()
    password = os.environ.get("SEED_USER_PASSWORD", "")
    if not email or not password:
        raise SystemExit("SEED_USER_EMAIL and SEED_USER_PASSWORD are required")

    try:
        plan = TenantPlan(os.environ.get("SEED_TENANT_PLAN", "starter").strip().lower())
    except ValueError as exc:
        raise SystemExit("SEED_TENANT_PLAN must be starter, pro, or enterprise") from exc
    tenant_name = os.environ.get("SEED_TENANT_NAME", "Seeded workspace").strip()
    display_name = os.environ.get("SEED_USER_DISPLAY_NAME", "Seeded user").strip()

    clear_settings_cache()
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    # Ensure all tables exist (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    tenant_store = TenantStore(engine)
    user_store = UserStore(engine)

    existing_tenants = await tenant_store.list_tenants()
    tenant = next((item for item in existing_tenants if item.name == tenant_name), None)
    if tenant is None:
        tenant = await tenant_store.create(name=tenant_name, plan=plan)
        print(f"[+] tenant created: {tenant.name} ({tenant.tenant_id})")
    else:
        print(f"[=] tenant exists:  {tenant.name} ({tenant.tenant_id})")

    existing_user = await user_store.get_by_email(email)
    if existing_user is None:
        user = await user_store.create(
            tenant_id=tenant.tenant_id,
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
        )
        print(f"[+] user created:   {user.email} (user_id={user.user_id})")
    else:
        print(f"[=] user exists:    {email}")

    print("Seed complete. Login with the email and password supplied through the environment.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
