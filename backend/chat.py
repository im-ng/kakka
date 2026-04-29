import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Entity, Triple, Task

OLLAMA_URL = "http://localhost:11434"


def build_kg_context(
    entities: list[Entity], triples: list[Triple], tasks: list[Task]
) -> str:
    lines = ["## Knowledge Graph"]
    if entities:
        lines.append("Entities:")
        for e in entities:
            lines.append(f"  - [{e.type}] {e.name} (id: {e.id})")
    if triples:
        lines.append("Relationships:")
        for t in triples:
            lines.append(f"  - {t.subject} --[{t.predicate}]--> {t.object}")
    if tasks:
        lines.append("Tasks:")
        for t in tasks:
            lines.append(
                f'  - #{t.id} "{t.title}" status={t.status} tags={t.tags} project={t.grp or "(none)"}'
            )
    return "\n".join(lines)


SYSTEM_PROMPT = """You are Kakka, a helpful task management assistant. You have access to the user's knowledge graph and task list.

When you mention or reference a task, use the format [Task #ID](task:ID) so the user can click to open it. For example: [Task #3](task:3).

Be concise, helpful, and reference relevant tasks and knowledge graph relationships when answering questions. If the user asks about their tasks, projects, tags, or how things connect, use the knowledge graph data to provide informed answers."""


async def call_ollama(messages: list[dict], model: str = "llama3") -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")


async def get_kg_context(
    db: AsyncSession,
) -> tuple[list[Entity], list[Triple], list[Task]]:
    entities = (await db.execute(select(Entity))).scalars().all()
    triples = (
        (await db.execute(select(Triple).where(Triple.valid_to.is_(None))))
        .scalars()
        .all()
    )
    tasks = (
        (await db.execute(select(Task).where(Task.archived == False))).scalars().all()
    )
    return entities, triples, tasks


def extract_task_refs(text: str, tasks: list[Task]) -> list[dict]:
    import re

    seen = set()
    refs = []
    for m in re.finditer(r"\[Task #(\d+)\]\(task:\d+\)", text):
        tid = int(m.group(1))
        if tid not in seen:
            seen.add(tid)
            task = next((t for t in tasks if t.id == tid), None)
            if task:
                refs.append({"id": task.id, "title": task.title, "status": task.status})
    return refs
