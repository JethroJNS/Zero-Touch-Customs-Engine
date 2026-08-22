import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.activity import Activity, ActivityAction

router = APIRouter(prefix="/api", tags=["activities"])


@router.get("/activities")
async def list_activities(
    action: Optional[str] = Query(None, description="Filter by action type"),
    search: Optional[str] = Query(None, description="Search in description or reference_code"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    # List activities with pagination, filtering, and search.
    query = select(Activity).order_by(Activity.created_at.desc())

    if action:
        query = query.where(Activity.action == action)
    if status:
        query = query.where(Activity.status == status)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Activity.description.ilike(search_term),
                Activity.reference_code.ilike(search_term),
            )
        )

    count_query = select(func.count(Activity.id))
    if action:
        count_query = count_query.where(Activity.action == action)
    if status:
        count_query = count_query.where(Activity.status == status)
    if search:
        search_term = f"%{search}%"
        count_query = count_query.where(
            or_(
                Activity.description.ilike(search_term),
                Activity.reference_code.ilike(search_term),
            )
        )
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    def parse_meta(act: Activity):
        if act.event_data:
            try:
                return json.loads(act.event_data)
            except Exception:
                return {}
        return {}

    activities = [
        {
            "id": act.id,
            "action": act.action,
            "description": act.description,
            "entity_type": act.entity_type,
            "entity_id": act.entity_id,
            "reference_code": act.reference_code,
            "metadata": parse_meta(act),
            "status": act.status,
            "created_at": act.created_at.isoformat() if act.created_at else None,
        }
        for act in items
    ]

    return {
        "items": activities,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/activities/stats")
async def get_activity_stats(db: AsyncSession = Depends(get_db)):
    total_result = await db.execute(select(func.count(Activity.id)))
    total_events = total_result.scalar() or 0

    ocr_result = await db.execute(
        select(func.count(Activity.id)).where(Activity.action == ActivityAction.OCR_PROCESS.value)
    )
    ocr_runs = ocr_result.scalar() or 0

    submission_actions = [
        ActivityAction.DECLARATION_SEND.value,
        ActivityAction.DECLARATION_APPROVE.value,
    ]
    submission_result = await db.execute(
        select(func.count(Activity.id)).where(Activity.action.in_(submission_actions))
    )
    ceisa_submissions = submission_result.scalar() or 0

    last_result = await db.execute(
        select(Activity.created_at).order_by(Activity.created_at.desc()).limit(1)
    )
    last_activity_row = last_result.scalar_one_or_none()
    last_activity = last_activity_row.isoformat() if last_activity_row else None

    return {
        "total_events": total_events,
        "ocr_runs": ocr_runs,
        "ceisa_submissions": ceisa_submissions,
        "last_activity": last_activity,
    }
