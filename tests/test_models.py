"""Unit tests for models — no OmniFocus needed."""

from ofocus.models import Folder, Project, Tag, Task


def test_task_from_dict_minimal():
    t = Task.from_dict({"id": "abc123", "name": "Buy milk"})
    assert t.id == "abc123"
    assert t.name == "Buy milk"
    assert t.flagged is False
    assert t.tags == []


def test_task_from_dict_full():
    t = Task.from_dict(
        {
            "id": "abc123",
            "name": "Review PR",
            "flagged": True,
            "completed": False,
            "dueDate": "2026-03-15T00:00:00.000Z",
            "note": "Check tests",
            "project": "Work",
            "tags": ["code", "urgent"],
        }
    )
    assert t.flagged is True
    assert t.due_date == "2026-03-15T00:00:00.000Z"
    assert t.project == "Work"
    assert t.tags == ["code", "urgent"]


def test_task_to_line():
    t = Task(id="abc", name="Buy milk", flagged=True, due_date="2026-03-15T00:00:00Z")
    line = t.to_line()
    assert "* Buy milk" in line
    assert "(due 2026-03-15)" in line


def test_task_to_dict():
    t = Task(id="abc", name="Test", tags=["foo"])
    d = t.to_dict()
    assert d["id"] == "abc"
    assert d["tags"] == ["foo"]


def test_project_from_dict():
    p = Project.from_dict(
        {
            "id": "p1",
            "name": "Work",
            "status": "active",
            "taskCount": 5,
            "folder": "Main",
        }
    )
    assert p.task_count == 5
    assert p.folder == "Main"


def test_project_to_line():
    p = Project(id="p1", name="Work", task_count=5, folder="Main")
    assert "Work [Main] (5 tasks)" == p.to_line()


def test_tag_from_dict():
    t = Tag.from_dict({"id": "t1", "name": "urgent"})
    assert t.name == "urgent"


def test_folder_from_dict():
    f = Folder.from_dict({"id": "f1", "name": "Personal", "projectCount": 3})
    assert f.project_count == 3
    assert "3 projects" in f.to_line()
