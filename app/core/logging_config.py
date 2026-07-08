"""
Logging estructurado en JSON (fácil de indexar en CloudWatch/Datadog/etc.) +
Sentry opcional. Sin SENTRY_DSN, Sentry simplemente no se inicializa — no es
obligatorio para correr el proyecto, pero es lo primero que quieres prender
antes de un piloto real: hoy, sin esto, un error en producción no te avisa,
solo se pierde en el log del proceso.
"""
import json
import logging
import sys

from app.core.config import get_settings

settings = get_settings()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # Menos ruido de librerías de terceros a nivel INFO/DEBUG.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    if settings.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                integrations=[FastApiIntegration()],
                traces_sample_rate=0.1,
            )
            logging.getLogger("verifiq").info("Sentry inicializado")
        except ImportError:
            logging.getLogger("verifiq").warning(
                "SENTRY_DSN configurado pero sentry-sdk no está instalado"
            )
