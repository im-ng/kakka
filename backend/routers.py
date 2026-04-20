import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import Task, async_session
from models import TaskCreate, TaskUpdate


router = APIRouter(prefix="/api")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description or "",
        "status": t.status,
        "done": bool(t.done),
        "tags": json.loads(t.tags) if t.tags else [],
        "project": t.grp or "",
        "archived": bool(t.archived),
        "sort_order": t.sort_order if t.sort_order is not None else 0,
        "due_date": t.due_date or "",
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


@router.get("/tasks")
async def list_tasks(
    tag: str | None = None,
    status: str | None = None,
    date: str | None = None,
    archived: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Task)
    if tag:
        stmt = stmt.where(Task.tags.contains(f'"{tag}"'))
    if status:
        stmt = stmt.where(Task.status == status)
    if date:
        stmt = stmt.where(func.date(Task.created_at) == date)
    if archived is None:
        stmt = stmt.where(Task.archived == False)
    elif archived:
        stmt = stmt.where(Task.archived == True)
    else:
        stmt = stmt.where(Task.archived == False)

    stmt = stmt.order_by(Task.sort_order.asc(), Task.id.asc())
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [task_to_dict(t) for t in tasks]


@router.post("/tasks", status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc).isoformat()
    task = Task(
        title=body.title,
        description=body.description,
        status=body.status,
        done=body.status == "done",
        tags=json.dumps(body.tags),
        grp=body.project,
        due_date=body.due_date,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task_to_dict(task)


@router.put("/tasks/reorder")
async def reorder_tasks(body: list[int], db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc).isoformat()
    for i, task_id in enumerate(body):
        await db.execute(
            update(Task).where(Task.id == task_id).values(sort_order=i, updated_at=now)
        )
    await db.commit()
    return {"ok": True}


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return JSONResponse(status_code=404, content={"detail": "Task not found"})

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.status is not None:
        task.status = body.status
        task.done = body.status == "done"
    if body.tags is not None:
        task.tags = json.dumps(body.tags)
    if body.project is not None:
        task.grp = body.project
    if body.archived is not None:
        task.archived = body.archived
    if body.sort_order is not None:
        task.sort_order = body.sort_order
    if body.due_date is not None:
        task.due_date = body.due_date

    task.updated_at = datetime.now(timezone.utc).isoformat()
    await db.commit()
    await db.refresh(task)
    return task_to_dict(task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return JSONResponse(status_code=404, content={"detail": "Task not found"})
    await db.delete(task)
    await db.commit()
    return {"ok": True}


@router.get("/tags")
async def list_tags(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task.tags))
    rows = result.scalars().all()
    tags_set: set[str] = set()
    for t in rows:
        for tag in json.loads(t):
            tags_set.add(tag)
    return sorted(tags_set)
