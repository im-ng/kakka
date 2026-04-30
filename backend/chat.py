import json
import re
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import Entity, Triple, Task
from kg_sync import sync_task_to_graph

CREATE_PATTERNS = [
    (
        re.compile(
            r"""(?:add|create|new|make)\s+(?:a\s+)?(?:task|todo)(?:\s+called)?\s+["'](.+?)["'](?:\s+(?:with\s+)?(?:desc(?:ription)?|about|note|saying)\s+(.+))?$""",
            re.I,
        ),
        "title_quoted",
    ),
    (
        re.compile(
            r"""(?:add|create|new|make)\s+(?:a\s+)?(?:task|todo)(?:\s+called)?\s+(.+?)(?:\s+(?:with\s+)?(?:desc(?:ription)?|about|note|saying)\s+(.+))$""",
            re.I,
        ),
        "title_rest",
    ),
    (
        re.compile(
            r"""(?:add|create|new|make)\s+(?:a\s+)?(?:task|todo)(?:\s+called)?\s+(.+)$""",
            re.I,
        ),
        "title_bare",
    ),
]

ACTION_PATTERNS = [
    (
        re.compile(
            r"(?:mark|set|move|change|put)\s+(?:task\s*)?#(\d+)\s+(?:as\s+)?(?:to\s+)?(?:in\s+)?progress",
            re.I,
        ),
        "progress",
    ),
    (
        re.compile(
            r"(?:mark|set|move|change|put)\s+(?:task\s*)?#(\d+)\s+(?:as\s+)?(?:to\s+)?(?:done|complete|completed|finished)",
            re.I,
        ),
        "done",
    ),
    (
        re.compile(
            r"(?:mark|set|move|change|put)\s+(?:task\s*)?#(\d+)\s+(?:as\s+)?(?:to\s+)?(?:to\s*do|todo|pending|back)",
            re.I,
        ),
        "todo",
    ),
    (re.compile(r"#(\d+)\s+(?:as\s+)?(?:to\s+)?(?:in\s+)?progress", re.I), "progress"),
    (
        re.compile(
            r"#(\d+)\s+(?:as\s+)?(?:to\s+)?(?:done|complete|completed|finished)", re.I
        ),
        "done",
    ),
    (
        re.compile(r"#(\d+)\s+(?:as\s+)?(?:to\s+)?(?:to\s*do|todo|pending)", re.I),
        "todo",
    ),
    (re.compile(r"(?:start|begin|doing)\s+(?:task\s*)?#(\d+)", re.I), "progress"),
    (re.compile(r"(?:finish|complete|close)\s+(?:task\s*)?#(\d+)", re.I), "done"),
    (re.compile(r"(?:reopen|undo|reset)\s+(?:task\s*)?#(\d+)", re.I), "todo"),
]


def detect_action(message: str) -> list[tuple[int, str]]:
    actions = []
    seen = set()
    for pattern, status in ACTION_PATTERNS:
        for m in pattern.finditer(message):
            tid = int(m.group(1))
            if tid not in seen:
                seen.add(tid)
                actions.append((tid, status))
    return actions


async def query_kg(
    message: str, db: AsyncSession
) -> tuple[str, list[dict], list[dict]]:
    msg = message.lower().strip()
    original = message.strip()

    create_match = None
    create_desc = ""
    for pattern, kind in CREATE_PATTERNS:
        m = pattern.search(original)
        if m:
            create_match = m.group(1)
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                create_desc = m.group(2)
            break

    if not create_match:
        low = original.lower()
        for starter in [
            "add task ",
            "create task ",
            "new task ",
            "make task ",
            "add todo ",
            "create todo ",
            "new todo ",
        ]:
            if low.startswith(starter):
                rest = original[len(starter) :].strip()
                rest = re.sub(r"^called\s+", "", rest, flags=re.I)
                if rest:
                    for sep in [
                        " with ",
                        " desc ",
                        " description ",
                        " about ",
                        " note ",
                        " saying ",
                    ]:
                        idx = rest.lower().find(sep)
                        if idx > 0:
                            create_match = rest[:idx].strip().strip("\"'")
                            create_desc = rest[idx + len(sep) :].strip().strip("\"'")
                            break
                    if not create_match:
                        create_match = rest.strip().strip("\"'")
                break

    if create_match:
        title = create_match.strip().strip("\"'")
        if not title:
            return "Please provide a task title.", [], []
        description = create_desc.strip().strip("\"'")
        now = datetime.now(timezone.utc).isoformat()
        task = Task(
            title=title,
            description=description,
            status="todo",
            done=False,
            tags="[]",
            grp="",
            due_date="",
            archived=False,
            sort_order=0,
            created_at=now,
            updated_at=now,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        await sync_task_to_graph(task, db)
        await db.commit()
        resp = f"**Created [Task #{task.id}](task:{task.id})** — {task.title}"
        if description:
            resp += f"\n> {description}"
        resp += f"\nStatus: To Do"
        return (
            resp,
            [
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "changed": True,
                }
            ],
            [],
        )

    tasks_result = await db.execute(select(Task).where(Task.archived == False))
    all_tasks: list[Task] = list(tasks_result.scalars().all())

    entities_result = await db.execute(select(Entity))
    all_entities: list[Entity] = list(entities_result.scalars().all())

    triples_result = await db.execute(select(Triple).where(Triple.valid_to.is_(None)))
    all_triples: list[Triple] = list(triples_result.scalars().all())

    task_map = {t.id: t for t in all_tasks}
    entity_map = {e.id: e for e in all_entities}

    actions = detect_action(message)
    action_results: list[dict] = []
    if actions:
        status_labels = {"todo": "To Do", "progress": "In Progress", "done": "Done"}
        action_lines = []
        for tid, new_status in actions:
            if tid in task_map:
                task = task_map[tid]
                old_status = task.status
                if old_status != new_status:
                    task.status = new_status
                    task.done = new_status == "done"
                    task.updated_at = (
                        __import__("datetime")
                        .datetime.now(__import__("datetime").timezone.utc)
                        .isoformat()
                    )
                    db.add(task)
                    action_results.append(
                        {
                            "id": tid,
                            "title": task.title,
                            "status": new_status,
                            "changed": True,
                        }
                    )
                    action_lines.append(
                        f"**[Task #{tid}](task:{tid})** {task.title}: {status_labels[old_status]} → {status_labels[new_status]}"
                    )
                else:
                    action_results.append(
                        {
                            "id": tid,
                            "title": task.title,
                            "status": new_status,
                            "changed": False,
                        }
                    )
                    action_lines.append(
                        f"**[Task #{tid}](task:{tid})** {task.title} already {status_labels[new_status].lower()}"
                    )
            else:
                action_lines.append(f"Task #{tid} not found")
        await db.commit()
        if action_lines:
            header = "**Actions completed:**\n\n" if action_results else ""
            return header + "\n".join(action_lines), action_results, []

    task_id_matches = set(
        int(m.group(1))
        for m in re.finditer(r"#(\d+)", msg)
        if m.group(1).isdigit() and int(m.group(1)) in task_map
    )

    tag_matches = set()
    known_tags = set()
    for t in all_tasks:
        for tag in json.loads(t.tags) if t.tags else []:
            known_tags.add(tag.lower())
    for word in msg.split():
        w = word.rstrip("s").lower()
        if w in known_tags or word.lower() in known_tags:
            tag_matches.add(word.lower() if word.lower() in known_tags else w)

    status_keywords = {
        "todo": "todo",
        "to do": "todo",
        "to-do": "todo",
        "pending": "todo",
        "in progress": "progress",
        "progress": "progress",
        "ongoing": "progress",
        "working on": "progress",
        "done": "done",
        "complete": "done",
        "completed": "done",
        "finished": "done",
    }
    status_match = None
    for kw, status in status_keywords.items():
        if kw in msg:
            status_match = status
            break

    entity_matches = set()
    names_lower = {e.name.lower(): e.id for e in all_entities}
    names_lower.update(
        {e.id.split(":", 1)[-1].lower(): e.id for e in all_entities if ":" in e.id}
    )
    for token in msg.split():
        t = token.lower().strip(".,!?")
        if t in names_lower:
            entity_matches.add(names_lower[t])

    relevant_tasks: list[Task] = []
    relevant_triples: list[Triple] = []
    used_tags = set()

    if task_id_matches:
        relevant_tasks = [task_map[tid] for tid in task_id_matches if tid in task_map]
        for tid in task_id_matches:
            task_eid = f"task:{tid}"
            for tr in all_triples:
                if tr.subject == task_eid or tr.object == task_eid:
                    relevant_triples.append(tr)

    if tag_matches:
        for t in all_tasks:
            task_tags = [tg.lower() for tg in (json.loads(t.tags) if t.tags else [])]
            if any(tg in tag_matches for tg in task_tags):
                if t not in relevant_tasks:
                    relevant_tasks.append(t)
                    used_tags.update(tg for tg in task_tags if tg in tag_matches)
        for t in all_triples:
            if t.predicate == "has_tag" and any(
                t.object == f"tag:{tg}" for tg in tag_matches
            ):
                if t not in relevant_triples:
                    relevant_triples.append(t)

    if status_match:
        for t in all_tasks:
            if t.status == status_match and t not in relevant_tasks:
                relevant_tasks.append(t)

    if entity_matches:
        for eid in entity_matches:
            for t in all_triples:
                if (t.subject == eid or t.object == eid) and t not in relevant_triples:
                    relevant_triples.append(t)
            for t in all_tasks:
                if f"task:{t.id}" in entity_matches and t not in relevant_tasks:
                    relevant_tasks.append(t)

    is_overview = any(
        kw in msg
        for kw in [
            "all tasks",
            "all task",
            "list tasks",
            "show tasks",
            "what tasks",
            "what do i",
            "what have i",
            "overview",
            "summary",
            "dashboard",
            "my tasks",
            "everything",
            "task list",
            "how many",
        ]
    )
    is_status_overview = any(
        kw in msg
        for kw in [
            "status",
            "statuses",
            "by status",
            "status breakdown",
            "what's the status",
        ]
    )

    if msg in ("", "hi", "hello", "hey", "help", "?", "what can you do"):
        return _format_greeting(all_tasks, all_entities, all_triples, task_map)

    if is_overview or is_status_overview:
        relevant_tasks = list(all_tasks)

    project_kw = re.search(r"(?:project|proj)\s+(\S+)", msg, re.IGNORECASE)
    if project_kw:
        pname = project_kw.group(1).lower()
        for t in all_tasks:
            if t.grp and pname in t.grp.lower() and t not in relevant_tasks:
                relevant_tasks.append(t)

    if not relevant_tasks and not relevant_triples:
        kw_hits = set()
        for t in all_tasks:
            score = 0
            title_l = t.title.lower()
            desc_l = (t.description or "").lower()
            for word in msg.split():
                w = word.lower().strip(".,!?")
                if len(w) < 3:
                    continue
                if w in title_l or w in desc_l:
                    score += 2
                for tg in json.loads(t.tags) if t.tags else []:
                    if w == tg.lower() or w == tg.lower().rstrip("s"):
                        score += 1
                if t.grp and w in t.grp.lower():
                    score += 1
            if score >= 2:
                kw_hits.add(t.id)
                relevant_tasks.append(t)

        if not relevant_tasks:
            return _format_no_match(all_tasks), [], []

    return _format_response(
        message, relevant_tasks, relevant_triples, entity_map, task_map, used_tags
    )


def _format_greeting(all_tasks, all_entities, all_triples, task_map):
    todo = sum(1 for t in all_tasks if t.status == "todo")
    progress = sum(1 for t in all_tasks if t.status == "progress")
    done = sum(1 for t in all_tasks if t.status == "done")
    tags = sorted(
        set(tg for t in all_tasks for tg in (json.loads(t.tags) if t.tags else []))
    )

    lines = [
        "**Hi! I'm Kakka.** I can answer questions and take actions on your tasks.\n",
        f"You have **{len(all_tasks)} tasks**: {todo} to do, {progress} in progress, {done} done.",
    ]
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")
    lines.append("\nTry asking:")
    lines.append('- "What\'s in progress?"')
    lines.append('- "Mark #3 as done"')
    lines.append('- "Start task #1"')
    lines.append('- "Show me urgent tasks"')

    return (
        "\n".join(lines),
        [
            {"id": t.id, "title": t.title, "status": t.status, "changed": False}
            for t in all_tasks
        ],
        [],
    )


def _format_no_match(all_tasks):
    lines = [
        "I couldn't find anything matching that query.",
        f"You have **{len(all_tasks)} tasks** total. Try:",
        "- A tag name (work, personal, urgent, idea)",
        "- A status (todo, in progress, done)",
        "- A task number like #3",
        '- An action like "mark #3 as done"',
    ]
    return "\n".join(lines), [], []


def _format_response(message, tasks, triples, entity_map, task_map, used_tags):
    lines = []

    if len(tasks) == 1:
        t = tasks[0]
        lines.append(f"**[Task #{t.id}](task:{t.id}) — {t.title}**\n")
        lines.append(f"**Status:** {t.status}")
        lines.append(f"**Tags:** {', '.join(json.loads(t.tags)) if t.tags else 'none'}")
        if t.grp:
            lines.append(f"**Project:** {t.grp}")
        if t.description:
            lines.append(f"**Description:** {t.description}")

        task_eid = f"task:{t.id}"
        connections = [
            tr for tr in triples if tr.subject == task_eid or tr.object == task_eid
        ]
        if connections:
            lines.append("\n**Connections:**")
            for tr in connections:
                s_name = getattr(entity_map.get(tr.subject), "name", tr.subject)
                o_name = getattr(entity_map.get(tr.object), "name", tr.object)
                arrow = f"{s_name} → {tr.predicate.replace('_', ' ')} → {o_name}"
                lines.append(f"- {arrow}")
                if tr.object.startswith("task:") and tr.object != task_eid:
                    oid = int(tr.object.split(":")[1])
                    if oid in task_map:
                        ot = task_map[oid]
                        lines.append(
                            f"  → Linked: **[Task #{ot.id}](task:{ot.id})** ({ot.status})"
                        )

    elif len(tasks) <= 8:
        grouped = {"todo": [], "progress": [], "done": []}
        for t in tasks:
            grouped.get(t.status, grouped["todo"]).append(t)

        labels = {"todo": "To Do", "progress": "In Progress", "done": "Done"}
        for status, group in grouped.items():
            if group:
                lines.append(f"**{labels[status]}** ({len(group)})")
                for t in group:
                    tag_str = ", ".join(json.loads(t.tags)) if t.tags else ""
                    extra = f" · {tag_str}" if tag_str else ""
                    proj = f" · {t.grp}" if t.grp else ""
                    lines.append(
                        f"- **[Task #{t.id}](task:{t.id})** {t.title}{extra}{proj}"
                    )
                lines.append("")

        if used_tags and len(tasks) > 1:
            lines.append(f"Filtered by: {', '.join(used_tags)}")

    else:
        todo = sum(1 for t in tasks if t.status == "todo")
        progress = sum(1 for t in tasks if t.status == "progress")
        done = sum(1 for t in tasks if t.status == "done")
        lines.append(
            f"Found **{len(tasks)} tasks**: {todo} to do, {progress} in progress, {done} done.\n"
        )

        for t in tasks[:10]:
            lines.append(f"- **[Task #{t.id}](task:{t.id})** {t.title} ({t.status})")
        if len(tasks) > 10:
            lines.append(f"\n...and {len(tasks) - 10} more")

    connected_non_task = set()
    for tr in triples:
        if not tr.subject.startswith("task:") or not tr.object.startswith("task:"):
            connected_non_task.add(tr.subject)
            connected_non_task.add(tr.object)
    if connected_non_task and len(tasks) > 1:
        lines.append("\n**Related entities:**")
        for eid in connected_non_task:
            e = entity_map.get(eid)
            if e:
                lines.append(f"- {e.name} [{e.type}]")

    return (
        "\n".join(lines),
        [
            {"id": t.id, "title": t.title, "status": t.status, "changed": False}
            for t in tasks
        ],
        [],
    )
