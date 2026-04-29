import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import Entity, Triple, Task

TAG_COLORS = {
    "work": "sage",
    "personal": "emerald",
    "urgent": "amber",
    "idea": "violet",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def upsert_entity(
    db: AsyncSession, eid: str, name: str, etype: str, now: str, properties: str = "{}"
):
    result = await db.execute(select(Entity).where(Entity.id == eid))
    existing = result.scalar_one_or_none()
    if existing:
        existing.name = name
        return existing
    entity = Entity(
        id=eid, name=name, type=etype, properties=properties, created_at=now
    )
    db.add(entity)
    return entity


async def create_triple(
    db: AsyncSession,
    subject: str,
    predicate: str,
    obj: str,
    now: str,
    source_task_id: int | None = None,
):
    result = await db.execute(
        select(Triple).where(
            Triple.subject == subject,
            Triple.predicate == predicate,
            Triple.object == obj,
            Triple.valid_to.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    triple = Triple(
        subject=subject,
        predicate=predicate,
        object=obj,
        valid_from=now,
        valid_to=None,
        confidence=1.0,
        source_task_id=source_task_id,
        created_at=now,
    )
    db.add(triple)
    return triple


async def invalidate_triples(
    db: AsyncSession, subject: str, predicate: str | None, now: str
):
    stmt = update(Triple).where(
        Triple.subject == subject,
        Triple.valid_to.is_(None),
    )
    if predicate:
        stmt = stmt.where(Triple.predicate == predicate)
    stmt = stmt.values(valid_to=now)
    await db.execute(stmt)


async def sync_task_to_graph(task: Task, db: AsyncSession):
    now = _now()
    tid = f"task:{task.id}"

    await upsert_entity(db, tid, task.title, "task", now)

    tags = json.loads(task.tags) if task.tags else []
    for tag in tags:
        color = TAG_COLORS.get(tag, "")
        props = json.dumps({"color": color}) if color else "{}"
        await upsert_entity(db, f"tag:{tag}", tag.capitalize(), "tag", now, props)
        await create_triple(db, tid, "has_tag", f"tag:{tag}", now, task.id)

    if task.grp:
        await upsert_entity(db, f"project:{task.grp}", task.grp, "project", now)
        await create_triple(db, tid, "belongs_to", f"project:{task.grp}", now, task.id)

    await upsert_entity(
        db, f"status:{task.status}", task.status.capitalize(), "concept", now
    )
    await create_triple(db, tid, "has_status", f"status:{task.status}", now, task.id)


async def sync_task_update_graph(
    old_tags: list[str],
    old_grp: str,
    old_status: str,
    task: Task,
    db: AsyncSession,
):
    now = _now()
    tid = f"task:{task.id}"

    result = await db.execute(select(Entity).where(Entity.id == tid))
    entity = result.scalar_one_or_none()
    if entity:
        entity.name = task.title

    new_tags = json.loads(task.tags) if task.tags else []
    if set(old_tags) != set(new_tags):
        await invalidate_triples(db, tid, "has_tag", now)
        for tag in new_tags:
            color = TAG_COLORS.get(tag, "")
            props = json.dumps({"color": color}) if color else "{}"
            await upsert_entity(db, f"tag:{tag}", tag.capitalize(), "tag", now, props)
            await create_triple(db, tid, "has_tag", f"tag:{tag}", now, task.id)

    if old_grp != task.grp:
        await invalidate_triples(db, tid, "belongs_to", now)
        if task.grp:
            await upsert_entity(db, f"project:{task.grp}", task.grp, "project", now)
            await create_triple(
                db, tid, "belongs_to", f"project:{task.grp}", now, task.id
            )

    if old_status != task.status:
        await invalidate_triples(db, tid, "has_status", now)
        await upsert_entity(
            db, f"status:{task.status}", task.status.capitalize(), "concept", now
        )
        await create_triple(
            db, tid, "has_status", f"status:{task.status}", now, task.id
        )


async def sync_task_delete_graph(task_id: int, db: AsyncSession):
    now = _now()
    await invalidate_triples(db, f"task:{task_id}", None, now)
