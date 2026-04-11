"""Dataclasses for OmniFocus objects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Tag:
    id: str
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> Tag:
        return cls(id=d["id"], name=d["name"])

    def to_line(self) -> str:
        return self.name

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
        }


@dataclass
class Task:
    id: str
    name: str
    flagged: bool = False
    completed: bool = False
    due_date: str | None = None
    note: str | None = None
    project: str | None = None
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Task:
        return cls(
            id=d["id"],
            name=d["name"],
            flagged=d.get("flagged", False),
            completed=d.get("completed", False),
            due_date=d.get("dueDate"),
            note=d.get("note"),
            project=d.get("project"),
            tags=d.get("tags", []),
        )

    def to_line(self) -> str:
        parts = []
        if self.flagged:
            parts.append("*")
        parts.append(self.name)
        if self.due_date:
            parts.append(f"(due {self.due_date[:10]})")
        if self.project:
            parts.append(f"[{self.project}]")
        if self.tags:
            parts.append(f"#{' #'.join(self.tags)}")
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "flagged": self.flagged,
            "completed": self.completed,
            "dueDate": self.due_date,
            "note": self.note,
            "project": self.project,
            "tags": self.tags,
        }


@dataclass
class Project:
    id: str
    name: str
    status: str = "active"
    task_count: int = 0
    folder: str | None = None
    note: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        return cls(
            id=d["id"],
            name=d["name"],
            status=d.get("status", "active"),
            task_count=d.get("taskCount", 0),
            folder=d.get("folder"),
            note=d.get("note"),
        )

    def to_line(self) -> str:
        parts = [self.name]
        if self.folder:
            parts.append(f"[{self.folder}]")
        parts.append(f"({self.task_count} tasks)")
        if self.status != "active":
            parts.append(f"— {self.status}")
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "taskCount": self.task_count,
            "folder": self.folder,
            "note": self.note,
        }


@dataclass
class Folder:
    id: str
    name: str
    project_count: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> Folder:
        return cls(
            id=d["id"],
            name=d["name"],
            project_count=d.get("projectCount", 0),
        )

    def to_line(self) -> str:
        return f"{self.name} ({self.project_count} projects)"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "projectCount": self.project_count,
        }
