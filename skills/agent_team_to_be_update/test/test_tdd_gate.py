#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TDD Gate Tests for SelfClaimLoop verification hook integration.

Verifies that:
1. A task with a FAILING verification_command is NOT marked completed
   (status stays pending after handle_task_error resets it).
2. A task with a PASSING verification_command IS marked completed.
3. A task with no verification_commands completes unconditionally.
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Task
from task_queue import TaskQueue
from self_claim_loop import SelfClaimLoop


def _make_queue(tmpdir: str, team_id: str = "tdd_test") -> TaskQueue:
    return TaskQueue(team_id=team_id, base_dir=tmpdir)


def _make_loop(queue: TaskQueue, tmpdir: str) -> SelfClaimLoop:
    loop = SelfClaimLoop(
        agent_id="test_worker",
        agent_port=0,
        team_id=queue.team_id,
        coordination_dir=tmpdir,
        task_executor=lambda task: {"success": True},  # always "succeeds"
    )
    # Bypass mailbox send (no real mailbox in unit test)
    loop.mailbox = _NoOpMailbox()
    loop._leader_agent_id = "test_leader"
    return loop


class _NoOpMailbox:
    """Stub mailbox that silently drops messages."""
    def send_message(self, **kwargs):
        pass


async def _run_task(loop: SelfClaimLoop, task: Task):
    """Helper: claim and execute a single task through SelfClaimLoop."""
    await loop._try_claim_and_execute(task)


# ---------------------------------------------------------------------------
# Test 1: Failing verification_command keeps task out of completed
# ---------------------------------------------------------------------------
def test_failing_verification_blocks_completion():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = _make_queue(tmpdir)
        task = queue.create_task(
            name="failing_task",
            description="Should fail verification",
            verification_commands=["python -c \"assert 1 == 2, 'intentional failure'\""],
        )

        scl = _make_loop(queue, tmpdir)
        asyncio.run(_run_task(scl, task))

        refreshed = queue.get_task(task.id)
        assert refreshed.status != "completed", (
            f"Expected task NOT completed after failing verification, got status={refreshed.status}"
        )
        print(f"[PASS] test_failing_verification_blocks_completion: status={refreshed.status}")


# ---------------------------------------------------------------------------
# Test 2: Passing verification_command allows completion
# ---------------------------------------------------------------------------
def test_passing_verification_allows_completion():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = _make_queue(tmpdir)
        task = queue.create_task(
            name="passing_task",
            description="Should pass verification",
            verification_commands=["python -c \"assert 1 == 1\""],
        )

        scl = _make_loop(queue, tmpdir)
        asyncio.run(_run_task(scl, task))

        refreshed = queue.get_task(task.id)
        assert refreshed.status == "completed", (
            f"Expected task completed after passing verification, got status={refreshed.status}"
        )
        print(f"[PASS] test_passing_verification_allows_completion: status={refreshed.status}")


# ---------------------------------------------------------------------------
# Test 3: No verification_commands — task completes unconditionally
# ---------------------------------------------------------------------------
def test_no_verification_commands_completes():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = _make_queue(tmpdir)
        task = queue.create_task(
            name="no_verification_task",
            description="No verification commands set",
        )

        scl = _make_loop(queue, tmpdir)
        asyncio.run(_run_task(scl, task))

        refreshed = queue.get_task(task.id)
        assert refreshed.status == "completed", (
            f"Expected task completed (no verification), got status={refreshed.status}"
        )
        print(f"[PASS] test_no_verification_commands_completes: status={refreshed.status}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TDD Gate Tests")
    print("=" * 60 + "\n")

    test_failing_verification_blocks_completion()
    test_passing_verification_allows_completion()
    test_no_verification_commands_completes()

    print("\n" + "=" * 60)
    print("All TDD gate tests passed!")
    print("=" * 60)
