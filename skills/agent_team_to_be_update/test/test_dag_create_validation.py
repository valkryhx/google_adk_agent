#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for dag_create input validation and atomic behavior."""

import asyncio
import os
import shutil
import sys
import tempfile
import uuid

import pytest

# Add skill root to import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decentralized_tools import dag_create
from task_queue import TaskQueue


@pytest.fixture
def isolated_coord_root():
    """Provide an isolated coordination root via ADK_COORDINATION_DIR."""
    local_tmp_root = tempfile.gettempdir()
    tmpdir = os.path.join(local_tmp_root, f"dag_create_validation_{uuid.uuid4().hex}")
    os.makedirs(tmpdir, exist_ok=False)
    old_coord_root = os.environ.get("ADK_COORDINATION_DIR")
    os.environ["ADK_COORDINATION_DIR"] = tmpdir
    try:
        yield tmpdir
    finally:
        if old_coord_root is None:
            os.environ.pop("ADK_COORDINATION_DIR", None)
        else:
            os.environ["ADK_COORDINATION_DIR"] = old_coord_root
        shutil.rmtree(tmpdir, ignore_errors=True)


def _build_queue(team_id: str, coord_root: str) -> TaskQueue:
    return TaskQueue(team_id=team_id, base_dir=os.path.join(coord_root, team_id))


def test_dag_create_missing_name_fails_without_partial_tasks(isolated_coord_root):
    team_id = "test-team"
    tasks = [
        {"name": "Task A", "description": "valid"},
        {"description": "missing name field"},
    ]

    with pytest.raises(ValueError, match=r"tasks\[2\]\.name is required"):
        asyncio.run(dag_create(team_id=team_id, tasks=tasks, broadcast=False))

    queue = _build_queue(team_id, isolated_coord_root)
    assert queue.list_tasks() == []


def test_dag_create_unknown_dependency_fails_without_partial_tasks(isolated_coord_root):
    team_id = "test-team"
    tasks = [
        {"name": "Task A"},
        {"name": "Task B", "blocked_by": ["Task C"]},
    ]

    with pytest.raises(ValueError, match="unknown or future task name: Task C"):
        asyncio.run(dag_create(team_id=team_id, tasks=tasks, broadcast=False))

    queue = _build_queue(team_id, isolated_coord_root)
    assert queue.list_tasks() == []


def test_dag_create_valid_tasks_creates_expected_dependency(isolated_coord_root):
    team_id = "test-team"
    tasks = [
        {"name": "Task A"},
        {"name": "Task B", "blocked_by": ["Task A"]},
    ]

    result = asyncio.run(dag_create(team_id=team_id, tasks=tasks, broadcast=False))
    queue = _build_queue(team_id, isolated_coord_root)
    created = queue.list_tasks()

    assert len(created) == 2
    by_name = {task.name: task for task in created}
    assert by_name["Task B"].blocked_by == [by_name["Task A"].id]
    assert "[DAG CREATED]" in result
