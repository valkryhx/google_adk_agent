#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Self-Claim Loop for Worker Agent.

Worker's core execution loop:
1. Start PollingDaemon to listen for inbox and task queue
2. Wait for task available notification
3. flock competition to claim task
4. Execute task
5. Mark complete and notify Lead
6. Loop

This is the decentralized replacement for dispatch_task.
"""

import asyncio
import json
import time
from typing import Optional, Callable, Any

try:
    from .mailbox import Mailbox, Message
    from .task_queue import TaskQueue, Task
    from .team_config import TeamConfig
    from .polling_daemon import PollingDaemon
except ImportError:
    from mailbox import Mailbox, Message
    from task_queue import TaskQueue, Task
    from team_config import TeamConfig
    from polling_daemon import PollingDaemon


class SelfClaimLoop:
    """
    Worker self-claim task loop.

    Execution flow:
    1. Start background PollingDaemon
    2. Agent main loop waits for daemon events
    3. Receive task available notification -> flock claim
    4. Execute task
    5. Mark complete -> mailbox notify Lead
    6. Continue waiting
    """

    def __init__(
        self,
        agent_id: str,
        agent_port: int,
        team_id: str,
        coordination_dir: str,
        task_executor: Callable[[Task], Any] = None,
        poll_interval: float = 2.0
    ):
        """
        Initialize the self-claim loop.

        Args:
            agent_id: Unique identifier for this worker agent
            agent_port: Port number this agent is running on
            team_id: Team identifier
            coordination_dir: Base directory for coordination files
            task_executor: Optional callback function to execute tasks
            poll_interval: Seconds between polling cycles (default: 2.0)
        """
        self.agent_id = agent_id
        self.agent_port = agent_port
        self.team_id = team_id
        self.coordination_dir = coordination_dir
        self.task_executor = task_executor
        self.poll_interval = poll_interval

        self.mailbox = Mailbox(base_dir=coordination_dir)
        self.task_queue = TaskQueue(team_id=team_id, base_dir=coordination_dir)
        self.team_config = TeamConfig(team_id=team_id, base_dir=coordination_dir)

        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._current_task: Optional[Task] = None
        self._daemon: Optional[PollingDaemon] = None

    def _on_messages(self, messages: list):
        """
        Callback when new messages arrive from PollingDaemon.

        Creates async tasks to handle each message.

        Args:
            messages: List of Message objects
        """
        for msg in messages:
            asyncio.create_task(self._handle_message(msg))

    def _on_task_available(self, task: Task):
        """
        Callback when a task becomes available.

        Puts a task_available event into the event queue.

        Args:
            task: Available Task object
        """
        self._event_queue.put_nowait(("task_available", task))

    def _on_idle(self):
        """
        Callback when daemon detects idle state.

        Puts an idle event into the event queue.
        """
        self._event_queue.put_nowait(("idle", None))

    async def _handle_message(self, msg: Message):
        """
        Handle incoming messages from other agents.

        Parses message content as JSON and handles different message types:
        - shutdown_request: Send shutdown_response and stop the loop
        - task_assignment: Extract taskId and queue for execution
        - broadcast/text: Log the message

        Args:
            msg: Message object to handle
        """
        try:
            content_data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            content_data = {"type": "text", "content": msg.content}

        msg_type = content_data.get("type", msg.msg_type)

        if msg_type == "shutdown_request":
            await self._handle_shutdown_request(msg, content_data)
        elif msg_type == "task_assignment":
            task_id = content_data.get("taskId")
            if task_id:
                self._event_queue.put_nowait(("task_available", task_id))
        elif msg_type in ("broadcast", "text"):
            print(f"[{self.agent_id}] Received from {msg.from_agent}: {content_data.get('content', msg.content)}")

    async def _handle_shutdown_request(self, msg: Message, content_data: dict):
        """
        Handle shutdown request from leader.

        Sends shutdown_response to leader and sets _running to False
        to gracefully stop the main loop.

        Args:
            msg: Original shutdown request message
            content_data: Parsed message content
        """
        request_id = content_data.get("requestId", "")
        self.mailbox.send_message(
            from_agent=self.agent_id,
            to_agent="leader",
            content=json.dumps({
                "type": "shutdown_response",
                "requestId": request_id,
                "approved": True
            }),
            msg_type="shutdown_response"
        )
        self._running = False

    async def run(self):
        """
        Start the self-claim task loop.

        This is the MAIN ASYNC METHOD that runs continuously until shutdown.

        Flow:
        1. Start PollingDaemon in background thread
        2. Set _running=True
        3. Main loop: wait on _event_queue with timeout=5s
           - On task_available: call _try_claim_and_execute()
           - On idle: increment idle_count, send idle_notification if >=3
           - On timeout: check available tasks, try to claim one
        4. Loop until _running=False
        5. Stop daemon
        """
        self._daemon = PollingDaemon(
            agent_id=self.agent_id,
            team_id=self.team_id,
            coordination_dir=self.coordination_dir,
            poll_interval=self.poll_interval,
            on_message=self._on_messages,
            on_task_available=self._on_task_available,
            on_idle=self._on_idle
        )
        self._daemon.start()

        self._running = True
        idle_count = 0

        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=5.0
                )
                event_type, data = event
                if event_type == "task_available":
                    await self._try_claim_and_execute(data)
                    idle_count = 0
                elif event_type == "idle":
                    idle_count += 1
                    if idle_count >= 3:
                        self.mailbox.send_message(
                            from_agent=self.agent_id,
                            to_agent="leader",
                            content=json.dumps({
                                "type": "idle_notification",
                                "from": self.agent_id,
                                "idleReason": "available"
                            }),
                            msg_type="idle_notification"
                        )
                        idle_count = 0
            except asyncio.TimeoutError:
                available = self.task_queue.get_available_tasks()
                if available:
                    await self._try_claim_and_execute(available[0])
                else:
                    idle_count += 1

        if self._daemon:
            self._daemon.stop()

    async def _try_claim_and_execute(self, task_or_id):
        """
        Try to claim and execute a task.

        Flow:
        1. Get Task object from task_id or use direct Task object
        2. Call task_queue.claim_task(task_id, agent_id)
           - If False (flock failed), return immediately
        3. Set _current_task=task
        4. Execute task via task_executor callback (if provided, run in run_in_executor)
        5. On complete/error: call task_queue.complete_task(task_id)
        6. Send task_completed message to leader via mailbox
        7. Set _current_task=None

        Args:
            task_or_id: Either a Task object or task_id string
        """
        if isinstance(task_or_id, str):
            task_id = task_or_id
            task = self.task_queue.get_task(task_id)
        else:
            task = task_or_id
            task_id = task.id

        if task is None:
            return

        if not self.task_queue.claim_task(task_id, self.agent_id):
            return

        self._current_task = task
        result = None
        error = None
        try:
            if self.task_executor:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self.task_executor, task
                )
        except Exception as e:
            error = str(e)

        self.task_queue.complete_task(task_id)
        self.mailbox.send_message(
            from_agent=self.agent_id,
            to_agent="leader",
            content=json.dumps({
                "type": "task_completed",
                "taskId": task_id,
                "taskName": task.name,
                "result": result,
                "error": error
            }),
            msg_type="task_completed"
        )
        self._current_task = None

    def get_current_task(self) -> Optional[Task]:
        """
        Get the currently executing task.

        Returns:
            Current Task object or None if idle
        """
        return self._current_task

    def stop(self):
        """
        Stop the self-claim loop gracefully.

        Sets _running to False, which will cause the main loop to exit
        on the next iteration.
        """
        self._running = False
