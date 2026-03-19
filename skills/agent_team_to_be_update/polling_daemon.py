#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polling Daemon for Agent Team.

Each Agent (Leader or Worker) runs a lightweight background polling daemon.
Continuously checks the shared coordination directory without blocking the Agent main loop.
When changes are detected, triggers callbacks to notify the Agent main loop.

Mechanism:
1. Periodically check own inbox file for new messages
2. Periodically check task queue for available tasks
3. Trigger callbacks to inject synthetic conversation turns when changes detected
"""

import os
import time
import threading
from typing import Callable, List, Optional, Any
from dataclasses import dataclass

try:
    from .mailbox import Mailbox, Message
    from .task_queue import TaskQueue, Task
except ImportError:
    from mailbox import Mailbox, Message
    from task_queue import TaskQueue, Task


@dataclass
class DaemonEvent:
    """Daemon event data structure."""
    event_type: str
    data: Any


class PollingDaemon:
    """
    Background polling daemon for decentralized agent coordination.

    Non-blocking to the caller, notifies events asynchronously via callbacks.
    Supports:
    - Inbox polling (check for new messages)
    - Task queue polling (check for available tasks)
    - Message batching (avoid frequent callbacks)
    """

    def __init__(
        self,
        agent_id: str,
        team_id: str,
        coordination_dir: str,
        poll_interval: float = 2.0,
        on_message: Callable[[List[Message]], None] = None,
        on_task_available: Callable[[Task], None] = None,
        on_idle: Callable[[], None] = None
    ):
        """
        Initialize the polling daemon.

        Args:
            agent_id: Unique identifier for this agent
            team_id: Team identifier
            coordination_dir: Base directory for coordination files
            poll_interval: Seconds between polling cycles (default: 2.0)
            on_message: Callback when new messages arrive
            on_task_available: Callback when a task becomes available
            on_idle: Callback when no new messages or tasks
        """
        self.agent_id = agent_id
        self.team_id = team_id
        self.poll_interval = poll_interval
        self.on_message = on_message
        self.on_task_available = on_task_available
        self.on_idle = on_idle

        self.mailbox = Mailbox(base_dir=coordination_dir)
        self.task_queue = TaskQueue(team_id=team_id, base_dir=coordination_dir)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_message_count = 0
        self._last_task_states: dict = {}

    def start(self):
        """
        Start the daemon in a background thread.

        Non-blocking - returns immediately after launching the thread.
        The thread runs as a daemon thread (daemon=True).
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """
        Stop the daemon gracefully.

        Sets _running=False and waits for the thread to join (max 5 seconds).
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run_loop(self):
        """
        The main polling loop running in the background thread.

        Initializes state tracking variables on first run, then continuously:
        1. Checks inbox for new messages
        2. Checks task queue for available tasks
        3. Sleeps for poll_interval

        All exceptions are wrapped to prevent the daemon from crashing.
        """
        # Initialize state tracking on first run
        self._last_message_count = self._count_messages()
        self._last_task_states = self._snapshot_task_states()

        while self._running:
            try:
                self._check_inbox()
                self._check_tasks()
                if self.on_idle:
                    self.on_idle()
            except Exception as e:
                # Wrap exceptions to prevent daemon from crashing
                print(f"[PollingDaemon] Error in poll cycle: {e}")
            time.sleep(self.poll_interval)

    def _count_messages(self) -> int:
        """
        Count total lines in the inbox file (fast, no parsing).

        Returns:
            Number of non-empty lines in the inbox file
        """
        inbox_path = self.mailbox._get_inbox_path(self.agent_id)
        if not os.path.exists(inbox_path):
            return 0
        try:
            with open(inbox_path, 'r', encoding='utf-8') as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def _snapshot_task_states(self) -> dict:
        """
        Get a snapshot of all task states.

        Returns:
            Dictionary mapping task_id -> (status, owner)
        """
        tasks = self.task_queue.list_tasks()
        return {t.id: (t.status, t.owner) for t in tasks}

    def _check_inbox(self):
        """
        Check inbox for new messages and trigger callback if found.

        Compares current message count with last known count.
        If new messages exist, reads them and triggers on_message callback.
        """
        current_count = self._count_messages()
        if current_count > self._last_message_count:
            messages = self.mailbox.check_new_messages(
                self.agent_id, unread_only=True
            )
            if messages and self.on_message:
                self.on_message(messages)
            self._last_message_count = current_count

    def _check_tasks(self):
        """
        Check task queue for newly available tasks and trigger callback.

        Compares current task states with last snapshot.
        Detects tasks that are now pending with no owner but weren't before.
        """
        current_states = self._snapshot_task_states()
        for task_id, (status, owner) in current_states.items():
            old_status, old_owner = self._last_task_states.get(task_id, (None, None))
            if (status == "pending" and owner is None and
                    (old_status != "pending" or old_owner is not None)):
                task = self.task_queue.get_task(task_id)
                if task and self.on_task_available:
                    self.on_task_available(task)
        self._last_task_states = current_states

    def check_new_messages(self, mark_read: bool = True) -> List[Message]:
        """
        Manually check for new messages without triggering callbacks.

        Args:
            mark_read: Whether to mark returned messages as read

        Returns:
            List of unread messages
        """
        return self.mailbox.read_messages(
            self.agent_id, mark_read=mark_read
        )

    def get_available_tasks(self) -> List[Task]:
        """
        Get list of tasks that are currently available for claiming.

        Returns:
            List of available Task objects
        """
        return self.task_queue.get_available_tasks()

    def claim_task(self, task_id: str) -> bool:
        """
        Attempt to claim a task for this agent.

        Args:
            task_id: ID of the task to claim

        Returns:
            True if successfully claimed, False otherwise
        """
        return self.task_queue.claim_task(task_id, self.agent_id)

    @property
    def is_running(self) -> bool:
        """
        Check if the daemon is currently running.

        Returns:
            True if the polling loop is active
        """
        return self._running
