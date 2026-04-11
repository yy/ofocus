"""Focused tests for project tree view preparation helpers."""

from copy import deepcopy

from ofocus.helpers import prepare_project_children


def _make_task(
    name: str,
    *,
    completed: bool = False,
    dropped: bool = False,
    defer_date: str | None = None,
    sequential: bool = False,
    children: list[dict] | None = None,
) -> dict:
    return {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "flagged": False,
        "completed": completed,
        "dropped": dropped,
        "dueDate": None,
        "deferDate": defer_date,
        "note": "",
        "tags": [],
        "sequential": sequential,
        "children": children or [],
    }


def test_prepare_project_children_filters_completed_without_mutating_input():
    source = [
        _make_task("Done", completed=True),
        _make_task("Active"),
    ]
    original = deepcopy(source)

    prepared = prepare_project_children(
        source,
        parent_sequential=False,
        show_all=False,
        available_only=False,
        first_available_only=False,
    )

    assert [task["name"] for task in prepared] == ["Active"]
    assert source == original


def test_prepare_project_children_filters_available_on_a_copy():
    source = [
        _make_task("First"),
        _make_task("Second"),
    ]
    original = deepcopy(source)

    prepared = prepare_project_children(
        source,
        parent_sequential=True,
        show_all=True,
        available_only=True,
        first_available_only=False,
        today="2026-03-20",
    )

    assert [task["name"] for task in prepared] == ["First"]
    assert source == original
    assert "_available" not in source[0]


def test_prepare_project_children_collects_first_available_leaf_tasks():
    source = [
        _make_task(
            "Group",
            sequential=True,
            children=[
                _make_task("Nested First"),
                _make_task("Nested Second"),
            ],
        ),
        _make_task("Standalone"),
    ]
    original = deepcopy(source)

    prepared = prepare_project_children(
        source,
        parent_sequential=False,
        show_all=True,
        available_only=False,
        first_available_only=True,
        today="2026-03-20",
    )

    assert [task["name"] for task in prepared] == ["Nested First", "Standalone"]
    assert source == original
