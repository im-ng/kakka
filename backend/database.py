import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Integer, String, Text, Boolean, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DB_PATH = Path(__file__).parent / "kakka.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="todo")
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    grp: Mapped[str] = mapped_column(String, default="")
    due_date: Mapped[str] = mapped_column(String, default="")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


@event.listens_for(Task, "before_insert")
def set_timestamps(mapper, connection, target):
    now = datetime.now(timezone.utc).isoformat()
    if not target.created_at:
        target.created_at = now
    target.updated_at = now


SEED_DATA = [
    {
        "title": "Design landing page wireframes",
        "description": "Create low-fidelity wireframes for the new product landing page",
        "status": "todo",
        "done": False,
        "tags": json.dumps(["work", "urgent"]),
        "grp": "",
    },
    {
        "title": "Review pull request #42",
        "description": "Check code quality and provide feedback on the auth module",
        "status": "progress",
        "done": False,
        "tags": json.dumps(["work"]),
        "grp": "",
    },
    {
        "title": "Buy groceries for the week",
        "description": "Vegetables, fruits, milk, bread, eggs",
        "status": "todo",
        "done": False,
        "tags": json.dumps(["personal"]),
        "grp": "",
    },
    {
        "title": "Read chapter 5 of Design Patterns",
        "description": "Focus on observer and strategy patterns",
        "status": "progress",
        "done": False,
        "tags": json.dumps(["personal", "idea"]),
        "grp": "",
    },
    {
        "title": "Fix navigation responsive bug",
        "description": "Mobile menu does not close on item click",
        "status": "done",
        "done": True,
        "tags": json.dumps(["work", "urgent"]),
        "grp": "",
    },
    {
        "title": "Set up CI/CD pipeline",
        "description": "Configure GitHub Actions for automated testing",
        "status": "todo",
        "done": False,
        "tags": json.dumps(["work"]),
        "grp": "",
    },
    {
        "title": "Morning meditation routine",
        "description": "15 minutes mindfulness before starting work",
        "status": "done",
        "done": True,
        "tags": json.dumps(["personal"]),
        "grp": "",
    },
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        from sqlalchemy import func, select

        count = (await session.execute(select(func.count()).select_from(Task))).scalar()
        if count == 0:
            for seed in SEED_DATA:
                session.add(Task(**seed))
            await session.commit()
