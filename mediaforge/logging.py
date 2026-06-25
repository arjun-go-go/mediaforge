import contextvars
import logging
import sys

from loguru import logger

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<yellow>{extra[trace_id]}</yellow> | "
    "<level>{message}</level>\n"
)


def _patch_trace_id(record):
    record["extra"]["trace_id"] = trace_id_var.get()
    return True


class InterceptHandler(logging.Handler):
    """Forward standard logging records to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = sys._getframe(6), 0
        while frame and frame.f_globals.get("__name__", "").startswith("loguru"):
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(
    level: str = "INFO",
    log_format: str = "console",
    log_file: str = "",
    log_rotation: str = "50 MB",
    log_retention: str = "30 days",
    log_compression: str = "zip",
) -> None:
    """Configure the application logging system.

    Call once at application startup. Replaces all standard logging
    handlers with Loguru's InterceptHandler so that third-party
    libraries (uvicorn, httpx, langchain, etc.) also flow through
    the same formatting and sinks.
    """
    # Inject trace_id into every record globally (including calls from
    # other modules that import `logger` directly from loguru).
    logger.remove()
    logger.configure(patcher=_patch_trace_id)

    is_json = log_format == "json"

    # Console sink
    logger.add(
        sys.stderr,
        level=level,
        format=None if is_json else _CONSOLE_FORMAT,
        serialize=is_json,
        enqueue=True,
        diagnose=False,
        backtrace=False,
    )

    # File sink (optional)
    if log_file:
        logger.add(
            log_file,
            level=level,
            format=None if is_json else _CONSOLE_FORMAT,
            serialize=is_json,
            rotation=log_rotation,
            retention=log_retention,
            compression=log_compression,
            enqueue=True,
            diagnose=False,
            backtrace=False,
        )

    # Intercept standard logging so all libraries route through Loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Suppress noisy third-party loggers
    for name in ("uvicorn.error", "uvicorn.access", "httpx", "httpcore", "chromadb", "sentence_transformers"):
        logging.getLogger(name).setLevel(logging.WARNING)
