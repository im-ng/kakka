import asyncio
import json
import sys

sys.path.insert(0, ".")

from database import init_db, async_session, Task, Entity, Triple
from kg_sync import sync_task_to_graph, upsert_entity, create_triple, _now
from sqlalchemy import select


async def backfill():
    await init_db()

    async with async_session() as db:
        result = await db.execute(select(Task))
        tasks = result.scalars().all()

        for task in tasks:
            await sync_task_to_graph(task, db)

        await db.commit()
        print(f"Backfilled {len(tasks)} tasks into knowledge graph")

        result = await db.execute(select(Entity))
        entities = result.scalars().all()
        print(f"Total entities: {len(entities)}")

        result = await db.execute(select(Triple).where(Triple.valid_to.is_(None)))
        triples = result.scalars().all()
        print(f"Total current triples: {len(triples)}")


if __name__ == "__main__":
    asyncio.run(backfill())
