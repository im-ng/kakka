import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import Task, Entity, Triple, async_session
from models import TaskCreate, TaskUpdate, ChatRequest, ChatResponse, TaskRef
from kg_sync import sync_task_to_graph, sync_task_update_graph, sync_task_delete_graph
from chat import query_kg


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
    await sync_task_to_graph(task, db)
    await db.commit()
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
    task_id: int,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return JSONResponse(status_code=404, content={"detail": "Task not found"})

    old_tags = json.loads(task.tags) if task.tags else []
    old_grp = task.grp or ""
    old_status = task.status

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

    await sync_task_update_graph(old_tags, old_grp, old_status, task, db)
    await db.commit()
    return task_to_dict(task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return JSONResponse(status_code=404, content={"detail": "Task not found"})
    await sync_task_delete_graph(task_id, db)
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


# --- Knowledge Graph endpoints ---


@router.get("/graph")
async def get_graph(db: AsyncSession = Depends(get_db)):
    nodes = (await db.execute(select(Entity))).scalars().all()
    edges = (
        (await db.execute(select(Triple).where(Triple.valid_to.is_(None))))
        .scalars()
        .all()
    )
    return {
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "type": n.type,
                "properties": n.properties,
                "created_at": n.created_at,
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": e.id,
                "subject": e.subject,
                "predicate": e.predicate,
                "object": e.object,
                "valid_from": e.valid_from,
                "valid_to": e.valid_to,
                "confidence": e.confidence,
                "source_task_id": e.source_task_id,
                "created_at": e.created_at,
            }
            for e in edges
        ],
    }


@router.get("/graph/stats")
async def get_graph_stats(db: AsyncSession = Depends(get_db)):
    entity_count = (await db.execute(select(func.count()).select_from(Entity))).scalar()
    triple_count = (await db.execute(select(func.count()).select_from(Triple))).scalar()
    current_count = (
        await db.execute(
            select(func.count()).select_from(Triple).where(Triple.valid_to.is_(None))
        )
    ).scalar()
    expired_count = triple_count - current_count

    pred_counts = {}
    result = await db.execute(
        select(Triple.predicate, func.count())
        .where(Triple.valid_to.is_(None))
        .group_by(Triple.predicate)
    )
    for row in result:
        pred_counts[row[0]] = row[1]

    return {
        "entities": entity_count,
        "triples": triple_count,
        "current_facts": current_count,
        "expired_facts": expired_count,
        "relationship_types": pred_counts,
    }


@router.get("/graph/entity/{entity_id}")
async def get_entity(entity_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        return JSONResponse(status_code=404, content={"detail": "Entity not found"})

    outgoing = (
        (
            await db.execute(
                select(Triple).where(
                    Triple.subject == entity_id, Triple.valid_to.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    incoming = (
        (
            await db.execute(
                select(Triple).where(
                    Triple.object == entity_id, Triple.valid_to.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )

    def triple_dict(t: Triple) -> dict:
        return {
            "id": t.id,
            "subject": t.subject,
            "predicate": t.predicate,
            "object": t.object,
            "valid_from": t.valid_from,
            "valid_to": t.valid_to,
            "confidence": t.confidence,
            "source_task_id": t.source_task_id,
            "created_at": t.created_at,
        }

    return {
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "type": entity.type,
            "properties": entity.properties,
            "created_at": entity.created_at,
        },
        "outgoing": [triple_dict(t) for t in outgoing],
        "incoming": [triple_dict(t) for t in incoming],
    }


@router.get("/graph/timeline/{entity_id}")
async def get_timeline(entity_id: str, db: AsyncSession = Depends(get_db)):
    triples = (
        (
            await db.execute(
                select(Triple)
                .where((Triple.subject == entity_id) | (Triple.object == entity_id))
                .order_by(Triple.valid_from)
            )
        )
        .scalars()
        .all()
    )
    return {
        "entity_id": entity_id,
        "timeline": [
            {
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
                "valid_from": t.valid_from,
                "valid_to": t.valid_to,
                "current": t.valid_to is None,
            }
            for t in triples
        ],
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    last_msg = body.messages[-1].content if body.messages else ""
    content, task_refs, _ = await query_kg(last_msg, db)
    return ChatResponse(content=content, tasks=task_refs)
