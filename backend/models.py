from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "todo"
    tags: list[str] = Field(default_factory=list)
    project: str = ""
    due_date: str = ""


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    project: Optional[str] = None
    archived: Optional[bool] = None
    sort_order: Optional[int] = None
    due_date: Optional[str] = None


class TaskOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    description: str
    status: str
    done: bool
    tags: list[str]
    project: str
    archived: bool
    sort_order: int
    due_date: str
    created_at: str
    updated_at: str
