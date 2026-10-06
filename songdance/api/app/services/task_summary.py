from typing import TypedDict

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import UsageLedger, UsagePeriod


class TaskSummary(TypedDict):
    succeeded: int
    failed: int
    in_progress: int


def task_summary(session: Session, user_id: str, period_id: str | None) -> TaskSummary:
    """Count distinct jobs from durable billing events in the selected entitlement period.

    Released attempts include cancellation and deletion. Retrying a released job replaces
    its failed summary status; consumption takes precedence over any other attempts.
    Job rows and event timestamps are intentionally not used: cleanup and late settlement
    must not move a task out of the period that reserved its allowance.
    """
    empty: TaskSummary = {"succeeded": 0, "failed": 0, "in_progress": 0}
    if period_id is None:
        return empty

    attempts = (
        select(
            UsageLedger.job_id,
            func.max(case((UsageLedger.event_type == "consume", 1), else_=0)).label("consumed"),
            func.max(case((UsageLedger.event_type == "reservation", 1), else_=0)).label("reserved"),
            func.max(case((UsageLedger.event_type.in_(["consume", "release"]), 1), else_=0)).label(
                "settled"
            ),
        )
        .join(UsagePeriod, UsagePeriod.id == UsageLedger.period_id)
        .where(
            UsageLedger.user_id == user_id,
            UsagePeriod.user_id == user_id,
            UsageLedger.period_id == period_id,
            UsageLedger.job_id.is_not(None),
            UsageLedger.event_type.in_(["reservation", "consume", "release"]),
        )
        .group_by(UsageLedger.job_id, UsageLedger.reservation_id)
        .subquery()
    )
    jobs = (
        select(
            func.max(attempts.c.consumed).label("consumed"),
            func.max(case((attempts.c.reserved > attempts.c.settled, 1), else_=0)).label("pending"),
        )
        .group_by(attempts.c.job_id)
        .subquery()
    )
    counts = session.execute(
        select(
            func.coalesce(func.sum(jobs.c.consumed), 0),
            func.coalesce(
                func.sum(case(((jobs.c.consumed == 0) & (jobs.c.pending == 0), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case(((jobs.c.consumed == 0) & (jobs.c.pending == 1), 1), else_=0)),
                0,
            ),
        )
    ).one()
    return {"succeeded": int(counts[0]), "failed": int(counts[1]), "in_progress": int(counts[2])}
