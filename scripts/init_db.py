"""Database initialisation — runs Alembic migrations.

Usage:
    python scripts/init_db.py

This script replaces the old `Base.metadata.create_all` approach.
All schema changes must go through Alembic revision files under alembic/versions/.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
