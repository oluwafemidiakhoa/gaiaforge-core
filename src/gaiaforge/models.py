"""Validated plans and explicit execution boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PHASES = {"inspect", "design", "implement", "test", "review", "release"}
EFFECTS = {"read", "workspace_write", "external_write", "production_write"}


class PlanError(ValueError):
    """A plan failed structural or authorization-independent safety checks."""


@dataclass(frozen=True)
class Task:
    id: str
    phase: str
    side_effect: str
    environment: str
    depends_on: tuple[str, ...]
    acceptance: str
    budget_seconds: int
    approval_required: bool

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Task":
        required = {"id", "phase", "side_effect", "environment", "depends_on", "acceptance", "budget_seconds", "approval_required"}
        missing = required - value.keys()
        if missing:
            raise PlanError(f"missing task fields: {sorted(missing)}")
        if not isinstance(value["depends_on"], list) or not all(isinstance(x, str) for x in value["depends_on"]):
            raise PlanError("depends_on must be a list of IDs")
        if type(value["budget_seconds"]) is not int or not 1 <= value["budget_seconds"] <= 3600:
            raise PlanError("budget_seconds must be an integer between 1 and 3600")
        if type(value["approval_required"]) is not bool:
            raise PlanError("approval_required must be a boolean")
        for key in ("id", "phase", "side_effect", "environment", "acceptance"):
            if not isinstance(value[key], str) or not value[key].strip():
                raise PlanError(f"{key} must be a nonempty string")
        return cls(**{k: (tuple(value[k]) if k == "depends_on" else value[k]) for k in required})


def validate_plan(raw: dict[str, Any]) -> list[Task]:
    if not isinstance(raw, dict) or not isinstance(raw.get("tasks"), list) or not raw["tasks"]:
        raise PlanError("plan requires a nonempty tasks array")
    tasks = [Task.from_dict(t) for t in raw["tasks"]]
    by_id = {t.id: t for t in tasks}
    if len(by_id) != len(tasks):
        raise PlanError("duplicate task ID")
    for task in tasks:
        if task.phase not in PHASES or task.side_effect not in EFFECTS:
            raise PlanError(f"invalid phase or side effect for {task.id}")
        if task.environment not in {"local", "sandbox", "staging", "production"}:
            raise PlanError(f"invalid environment for {task.id}")
        if task.environment == "production" or task.side_effect in {"external_write", "production_write"}:
            if not task.approval_required:
                raise PlanError(f"high-impact task {task.id} requires human approval")
        if task.side_effect == "production_write" and task.environment != "production":
            raise PlanError(f"production_write requires production environment: {task.id}")
        if task.phase == "release" and not task.approval_required:
            raise PlanError("release cannot self-approve")
        for dependency in task.depends_on:
            if dependency not in by_id:
                raise PlanError(f"unknown dependency {dependency} for {task.id}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str) -> None:
        if node in visiting:
            raise PlanError("cyclic task dependency")
        if node in visited:
            return
        visiting.add(node)
        for dependency in by_id[node].depends_on:
            walk(dependency)
        visiting.remove(node)
        visited.add(node)

    for task in tasks:
        walk(task.id)
    for task in tasks:
        if task.phase == "release":
            ancestors: set[str] = set()
            pending = list(task.depends_on)
            while pending:
                parent = pending.pop()
                if parent in ancestors:
                    continue
                ancestors.add(parent)
                pending.extend(by_id[parent].depends_on)
            if not any(by_id[a].phase == "test" for a in ancestors):
                raise PlanError("release requires a preceding test task")
            if not any(by_id[a].phase == "review" for a in ancestors):
                raise PlanError("release requires a preceding review task")
    return tasks


def eligible_tasks(tasks: list[Task], finished: set[str]) -> list[str]:
    return [task.id for task in tasks if task.id not in finished and set(task.depends_on) <= finished and not task.approval_required]
