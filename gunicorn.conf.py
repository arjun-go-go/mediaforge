"""Gunicorn configuration for production deployment.

Start with:
    gunicorn -c gunicorn.conf.py mediaforge.gateway.main:app
"""

import multiprocessing
import os

# Bind
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Workers — default to CPU count, capped at 4 for typical deployments.
# Each worker is an independent asyncio event loop (UvicornWorker).
workers = int(os.getenv("GUNICORN_WORKERS", min(multiprocessing.cpu_count(), 4)))
worker_class = "uvicorn.workers.UvicornWorker"

# Connections per worker — async, so can be high
worker_connections = 1000

# Timeouts
timeout = 120           # Kill worker if it doesn't respond in 120s (covers long LLM calls)
graceful_timeout = 30   # Time to finish in-flight requests on shutdown
keepalive = 5           # Keep TCP alive for HTTP/1.1 pipelining

# Pre-load app to share memory across workers (copy-on-write after fork)
preload_app = True

# Restart workers periodically to prevent memory leaks
max_requests = 10000
max_requests_jitter = 1000

# Logging — let loguru handle it, just pass through access logs
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Security
forwarded_allow_ips = os.getenv("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")


def post_fork(server, worker):
    """Reset per-process singletons after fork.

    Gunicorn with preload_app=True forks from a pre-loaded master. Connection
    objects (Redis, DB pools, httpx clients) from the master are invalid in
    children — they share file descriptors that get corrupted. We force them
    to None so they're lazily re-created in each worker.
    """
    import mediaforge.db.redis_client as _rc
    import mediaforge.db.engine as _eng

    _rc._redis = None
    _eng._engine = None
    _eng._session_maker = None
