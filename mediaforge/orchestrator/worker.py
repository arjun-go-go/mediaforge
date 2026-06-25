"""Legacy Redis-queue worker — SUPERSEDED by Celery.

This module is retained for reference only. Starting it alongside the
Celery worker would cause every job to be consumed twice.

Start the Celery worker instead:
    celery -A mediaforge.celery_app worker --loglevel=info -Q high,normal,low

Beat scheduler (token purge, etc.):
    celery -A mediaforge.celery_app beat --loglevel=info
"""

import sys


def consume() -> None:
    print(
        "ERROR: mediaforge.orchestrator.worker is deprecated.\n"
        "Use Celery instead:\n"
        "  celery -A mediaforge.celery_app worker --loglevel=info -Q high,normal,low",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    consume()
