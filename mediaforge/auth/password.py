"""Password hashing with bcrypt (direct).

passlib 1.7.4 is unmaintained and its bcrypt backend breaks on bcrypt >=4.2
(it probes `bcrypt.__about__.__version__` which no longer exists, then
generates an overlong probe password to detect a legacy wrap bug — the
probe itself now raises ValueError). We use bcrypt directly instead.

The stored hash is the standard bcrypt `$2b$…` string, same shape passlib
would have produced. `verify_password` accepts either form for any hashes
that might still be in the DB from before the switch.
"""

import asyncio

import bcrypt

from mediaforge.config import get_settings

_PREFIX = b"$2b$"
_PASSLIB_PREFIX = "$bcrypt$"
_BCRYPT_MAX_BYTES = 72


def _rounds() -> int:
    return get_settings().password_bcrypt_rounds


def _clip(plain: str) -> bytes:
    """Encode and clip to bcrypt's 72-byte limit."""
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=_rounds())
    return bcrypt.hashpw(_clip(plain), salt).decode("ascii")


async def hash_password_async(plain: str) -> str:
    return await asyncio.to_thread(hash_password, plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        stored = hashed
        if stored.startswith(_PASSLIB_PREFIX):
            stored = stored[len(_PASSLIB_PREFIX):]
        if not stored.startswith("$2"):
            return False
        return bcrypt.checkpw(_clip(plain), stored.encode("ascii"))
    except (ValueError, TypeError):
        return False


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(verify_password, plain, hashed)


def needs_rehash(hashed: str) -> bool:
    """Return True when the stored hash doesn't match current bcrypt rounds.

    Best-effort: parses the cost factor from the bcrypt digest prefix.
    """
    try:
        stored = hashed
        if stored.startswith(_PASSLIB_PREFIX):
            stored = stored[len(_PASSLIB_PREFIX):]
        if not stored.startswith(_PREFIX.decode()):
            return True  # unrecognized scheme -> rehash
        # bcrypt format: $2b$<cost>$<22 salt><31 hash>
        cost_str = stored.split("$")[2]
        return int(cost_str) != _rounds()
    except (IndexError, ValueError):
        return True
