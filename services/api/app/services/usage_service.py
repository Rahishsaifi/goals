from __future__ import annotations

import calendar
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.model_provider import UsageTelemetry
from app.models.domain import EvaluationRun, UsageEvent

# Azure OpenAI Global Standard list price for gpt-4.1-mini, USD per 1M tokens.
_LIST_RATES_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
}
_BUDGET_USD = Decimal("10")
_MILLION = Decimal("1000000")


def estimate_cost(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    embedding_tokens: int | None,
    input_rate: Decimal = Decimal("0"),
    output_rate: Decimal = Decimal("0"),
    embedding_rate: Decimal = Decimal("0"),
) -> Decimal | None:
    if input_tokens is None and output_tokens is None and embedding_tokens is None:
        return None
    million = Decimal("1000000")
    total = Decimal("0")
    if input_tokens is not None:
        total += Decimal(input_tokens) * input_rate / million
    if output_tokens is not None:
        total += Decimal(output_tokens) * output_rate / million
    if embedding_tokens is not None:
        total += Decimal(embedding_tokens) * embedding_rate / million
    return total


def record_usage(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    operation_type: str,
    provider: str,
    usage: UsageTelemetry,
    idempotency_key: str,
    evaluation_run_id: uuid.UUID | None = None,
    ingestion_batch_id: uuid.UUID | None = None,
    resume_id: uuid.UUID | None = None,
    status: str = "succeeded",
) -> None:
    cost = estimate_cost(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        embedding_tokens=usage.embedding_tokens,
    )
    stmt = (
        insert(UsageEvent)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evaluation_run_id=evaluation_run_id,
            ingestion_batch_id=ingestion_batch_id,
            resume_id=resume_id,
            operation_type=operation_type,
            provider=provider,
            model_deployment=usage.model_deployment,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            embedding_tokens=usage.embedding_tokens,
            estimated_total_cost=cost,
            currency="USD",
            status=status,
            usage_available=usage.usage_available,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    db.execute(stmt)


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


def _list_price(
    *,
    provider: str,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> Decimal:
    if provider != "foundry" or model is None:
        return Decimal("0")
    rates = _LIST_RATES_PER_MILLION.get(model)
    if rates is None:
        return Decimal("0")
    return (Decimal(input_tokens) * rates[0] + Decimal(output_tokens) * rates[1]) / _MILLION


def usage_summary(db: Session, *, tenant_id: uuid.UUID) -> dict[str, object]:
    rows = db.execute(
        select(
            func.coalesce(func.sum(UsageEvent.input_tokens), 0),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0),
            func.coalesce(func.sum(UsageEvent.embedding_tokens), 0),
            func.count(UsageEvent.id),
            func.coalesce(func.sum(UsageEvent.estimated_total_cost), 0),
            func.count().filter(UsageEvent.usage_available.is_(False)),
            func.min(UsageEvent.created_at),
            func.max(UsageEvent.created_at),
        ).where(UsageEvent.tenant_id == tenant_id)
    ).one()
    grouped = db.execute(
        select(
            UsageEvent.operation_type,
            UsageEvent.provider,
            UsageEvent.model_deployment,
            func.count(),
            func.coalesce(func.sum(UsageEvent.input_tokens), 0),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0),
        )
        .where(UsageEvent.tenant_id == tenant_id)
        .group_by(
            UsageEvent.operation_type,
            UsageEvent.provider,
            UsageEvent.model_deployment,
        )
        .order_by(func.count().desc())
    ).all()
    day_count = int(
        db.scalar(
            select(func.count(func.distinct(cast(UsageEvent.created_at, Date)))).where(
                UsageEvent.tenant_id == tenant_id
            )
        )
        or 0
    )
    matching_runs = int(
        db.scalar(
            select(func.count())
            .select_from(EvaluationRun)
            .where(EvaluationRun.tenant_id == tenant_id)
        )
        or 0
    )
    scored_runs = int(
        db.scalar(
            select(func.count())
            .select_from(EvaluationRun)
            .where(
                EvaluationRun.tenant_id == tenant_id,
                EvaluationRun.result_count > 0,
            )
        )
        or 0
    )

    by_operation: list[dict[str, object]] = []
    list_price = Decimal("0")
    evidence_price = Decimal("0")
    evidence_calls = 0
    resume_price = Decimal("0")
    resume_calls = 0
    for operation, provider, model, calls, input_tokens, output_tokens in grouped:
        price = _list_price(
            provider=str(provider),
            model=str(model) if model is not None else None,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
        )
        list_price += price
        if operation == "evidence_assessment":
            evidence_price += price
            evidence_calls += int(calls or 0)
        if operation == "resume_extraction":
            resume_price += price
            resume_calls += int(calls or 0)
        by_operation.append(
            {
                "operation_type": operation,
                "provider": provider,
                "model_deployment": model,
                "calls": int(calls or 0),
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
                "list_price_usd": _money(price),
            }
        )

    now = datetime.now(UTC)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_left = days_in_month - now.day
    active_days = day_count if day_count > 0 else 0
    daily = (list_price / Decimal(active_days)) if active_days else Decimal("0")
    per_resume = (resume_price / Decimal(resume_calls)) if resume_calls else Decimal("0")
    per_score = (evidence_price / Decimal(scored_runs)) if scored_runs else Decimal("0")

    return {
        "input_tokens": int(rows[0] or 0),
        "output_tokens": int(rows[1] or 0),
        "embedding_tokens": int(rows[2] or 0),
        "model_calls": int(rows[3] or 0),
        "estimated_total_cost": str(rows[4] or 0),
        "unavailable_usage_count": int(rows[5] or 0),
        "currency": "USD",
        "first_event_at": rows[6].isoformat() if rows[6] is not None else None,
        "last_event_at": rows[7].isoformat() if rows[7] is not None else None,
        "by_operation": by_operation,
        "ai_matching_runs": matching_runs,
        "ai_matching_scored": scored_runs,
        "evidence_calls": evidence_calls,
        "list_price_usd": _money(list_price),
        "budget_usd": _money(_BUDGET_USD),
        "input_rate_per_million": "0.40",
        "output_rate_per_million": "1.60",
        "forecast": {
            "days_with_usage": active_days,
            "days_in_month": days_in_month,
            "days_left_after_today": days_left,
            "rest_of_month_usd": _money(daily * Decimal(days_left)),
            "full_month_if_repeated_usd": _money(list_price + daily * Decimal(days_left)),
            "per_resume_parse_usd": _money(per_resume),
            "per_candidate_score_usd": _money(per_score),
        },
        "note": (
            "List price uses Azure OpenAI Global Standard rates for gpt-4.1-mini "
            "($0.40 input / $1.60 output per million tokens). "
            "The stored ledger cost is $0. This is not an Azure invoice."
        ),
    }


def list_usage_events(db: Session, *, tenant_id: uuid.UUID, limit: int = 100) -> list[UsageEvent]:
    return list(
        db.scalars(
            select(UsageEvent)
            .where(UsageEvent.tenant_id == tenant_id)
            .order_by(UsageEvent.created_at.desc())
            .limit(limit)
        )
    )
