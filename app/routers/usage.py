from calendar import monthrange
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.adapters import exchange_rate_adapter
from app.core.database import get_db
from app.core.deps import get_current_client
from app.models.models import Client, UsageEvent
from app.schemas.schemas import UsageSummaryOut

router = APIRouter(prefix="/usage", tags=["usage"])

SIGN_PRICE_USD = 0.55
KYC_PRICE_USD = 1.25
GROWTH_BASE_PEN = 399
GROWTH_INCLUDED_OPS = 1000


@router.get("/summary", response_model=UsageSummaryOut)
async def summary(client: Client = Depends(get_current_client), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    period = now.strftime("%Y-%m")
    exchange_rate_pen = await exchange_rate_adapter.get_usd_to_pen_rate()

    # Rango de fechas explícito en vez de strftime() de SQLite, que no existe
    # en Postgres. func.date_trunc tampoco se usa porque Postgres/SQLite lo
    # implementan distinto — un BETWEEN es portable a ambos motores.
    period_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    last_day = monthrange(now.year, now.month)[1]
    period_end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    rows = (
        db.query(UsageEvent.event_type, func.count(UsageEvent.id), func.sum(UsageEvent.unit_cost_usd))
        .filter(
            UsageEvent.client_id == client.id,
            UsageEvent.created_at >= period_start,
            UsageEvent.created_at <= period_end,
        )
        .group_by(UsageEvent.event_type)
        .all()
    )

    counts = {row[0]: row[1] for row in rows}
    signatures_count = counts.get("signature", 0)
    kyc_count = counts.get("kyc", 0)
    cost_usd_starter = sum(row[2] or 0 for row in rows)

    if client.plan == "growth":
        # Misma fórmula que updateCalc() del landing: base fija + excedente por
        # encima de las 1,000 operaciones incluidas, a precio promedio con 30%
        # de descuento sobre el precio individual Starter.
        total_ops = signatures_count + kyc_count
        overage_ops = max(0, total_ops - GROWTH_INCLUDED_OPS)
        overage_avg_price_pen = ((SIGN_PRICE_USD + KYC_PRICE_USD) / 2) * exchange_rate_pen * 0.7
        cost_pen = GROWTH_BASE_PEN + overage_ops * overage_avg_price_pen
        cost_usd = round(cost_pen / exchange_rate_pen, 2)
    else:
        cost_usd = round(cost_usd_starter, 2)
        cost_pen = round(cost_usd * exchange_rate_pen, 2)

    return UsageSummaryOut(
        client_id=client.id,
        period=period,
        signatures_count=signatures_count,
        kyc_count=kyc_count,
        estimated_cost_usd=cost_usd,
        estimated_cost_pen=round(cost_pen, 2),
    )
