from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.logging_config import setup_logging
from app.core.rate_limit import limiter
from app.routers import clients, kyc, payments, pilot_leads, signatures, uploads, usage

settings = get_settings()
setup_logging()

# En dev con SQLite creamos las tablas directo. En producción (Postgres) el
# esquema se gestiona SOLO vía Alembic — ver alembic/versions/.
if settings.database_url.startswith("sqlite"):
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description="API de firma electrónica, KYC/AML y compliance-as-a-service para fintechs peruanas.",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients.router)
app.include_router(uploads.router)
app.include_router(signatures.router)
app.include_router(kyc.router)
app.include_router(usage.router)
app.include_router(payments.router)
app.include_router(pilot_leads.router)

app.mount("/panel", StaticFiles(directory="app/static", html=True), name="panel")


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}
