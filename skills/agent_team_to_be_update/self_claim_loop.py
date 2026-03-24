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
    from .path_guard import PathGuard
except ImportError:
    from mailbox import Mailbox, Message
    from task_queue import TaskQueue, Task
    from team_config import TeamConfig
    from polling_daemon import PollingDaemon
    from path_guard import PathGuard


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

        # [缺陷修复] 动态解析 Leader 的完整 agent_id，避免硬编码 "leader"
        # 格式如 leader_8000@adk_swarm，与 Mailbox 收件箱文件名匹配
        _leader = self.team_config.get_leader()
        self._leader_agent_id: str = _leader.agent_id if _leader else "leader"

        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._claim_lock = asyncio.Lock() # 👈 内存锁：解决进入抢占时的时序竞争 (Race Condition)
        self._running = False
        self._current_task: Optional[Task] = None
        self._daemon: Optional[PollingDaemon] = None
        # 👈 保存调用 run() 时所在的 event loop，供后台线程安全地 put 事件
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_messages(self, messages: list):
        """
        Callback when new messages arrive from PollingDaemon.
        PollingDaemon 运行在后台线程，必须用 call_soon_threadsafe 跨线程安全提交。

        Args:
            messages: List of Message objects
        """
        if self._loop and not self._loop.is_closed():
            for msg in messages:
                self._loop.call_soon_threadsafe(
                    lambda m=msg: self._loop.create_task(self._handle_message(m))
                )

    def _on_task_available(self, task: Task):
        """
        Callback when a task becomes available.
        PollingDaemon 运行在后台线程，必须用 call_soon_threadsafe 跨线程安全 put 事件。

        Args:
            task: Available Task object
        """
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait, ("task_available", task)
            )

    def _on_idle(self):
        """
        Callback when daemon detects idle state.
        PollingDaemon 运行在后台线程，必须用 call_soon_threadsafe 跨线程安全 put 事件。
        """
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait, ("idle", None)
            )

    def _drain_task_events(self):
        """清空 event_queue 中所有积压的 task_available stale 事件。

        Worker 完成一个任务后，其 event_queue 中可能残留着来自首次轮询时
        积压的其他任务通知。如果不清空，该 Worker 会率先连续认领多个任务，
        导致其他空闲 Worker 无任务可抢（负载不均）。
        清空后，所有 Worker 靠 PollingDaemon 下次轮询公平竞争。
        """
        drained = 0
        while not self._event_queue.empty():
            try:
                event = self._event_queue.get_nowait()
                if event[0] != "task_available":
                    # 非任务事件（idle / shutdown 等）放回队列
                    self._event_queue.put_nowait(event)
                else:
                    drained += 1
            except asyncio.QueueEmpty:
                break
        if drained:
            print(f"[{self.agent_id}] Drained {drained} stale task_available events after task completion.")

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
            to_agent=self._leader_agent_id,
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
        # 👈 保存当前 asyncio event loop，必须在 daemon.start() 之前赋值！
        # 否则后台线程第一次扫描时 _loop 为 None，事件被静默丢弃（竞态 bug）
        self._loop = asyncio.get_event_loop()
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
                    # 👈 极致加固: 防止 PollingDaemon 的 idle 喂饱 wait_for 撑破 5s 超时兜底锁。
                    # idle 触发时，顺便自主扫描并认领任务。
                    try:
                        available = self.task_queue.get_available_tasks()
                        if available:
                            print(f"[{self.agent_id}] 💤 Idle 巡检拾荒发现 {len(available)} 条任务，积极领命 ⚔️")
                            await self._try_claim_and_execute(available[0])
                            idle_count = 0
                    except Exception as e:
                        print(f"[{self.agent_id}] 💤 Idle 巡检异常: {e}")

                    if idle_count >= 3:
                        self.mailbox.send_message(
                            from_agent=self.agent_id,
                            to_agent=self._leader_agent_id,
                            content=json.dumps({
                                "type": "idle_notification",
                                "from": self.agent_id,
                                "idleReason": "available"
                            }),
                            msg_type="idle_notification"
                        )
                        idle_count = 0
            except asyncio.TimeoutError:
                # 👈 漏洞修复三：超时轮询时，如果没有执行器，也跳过认领
                if self.task_executor is None:
                    continue
                    
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

        # 👈 互斥锁守卫：如果本 Worker 已经有任务在执行，不应去竞争新任务
        if self._current_task is not None:
            return

        # 👈 漏洞修复一：如果没有本地执行器，说明是中心化派发模式节点，绝不能主动抢任务，防止空跑误报 completed
        if self.task_executor is None:
            return

        # 👈 漏洞修复二：如果外部（如 HTTP 线程）正在执行任务，不参与抢占
        if hasattr(self, 'has_running_task') and self.has_running_task():
            return

        async with self._claim_lock:
            # 再次检查：确保从事件队列出来后依然是空闲状态
            if self._current_task is not None:
                return

            if not self.task_queue.claim_task(task_id, self.agent_id):
                print(f"[SelfClaimLoop] ❌ claim_task({task_id}) 返回 False！抢单失败")
                return

            # PathGuard 集成：只校验 writable_files，读取不限制
            if task.writable_files:
                import os as _os
                guard = PathGuard(allowed_root=_os.getcwd())
                violations = [
                    f for f in task.writable_files
                    if not guard.is_allowed(f)
                ]
                if violations:
                    self.task_queue.fail_task(task_id)
                    self.mailbox.send_message(
                        from_agent=self.agent_id,
                        to_agent=self._leader_agent_id,
                        content=json.dumps({
                            "type": "task_failed",
                            "taskId": task_id,
                            "taskName": task.name,
                            "error": "PathGuard: 非法写路径 " + "; ".join(violations)
                        }),
                        msg_type="task_failed"
                    )
                    self._current_task = None
                    print(f"[SelfClaimLoop] 🚫 PathGuard 拦截任务 {task_id}，非法写路径: {violations}")
                    return

            print(f"[SelfClaimLoop] ✅ claim_task({task_id}) 成功！即将进入执行器")
            self._current_task = task
        result = None
        error = None
        try:
            if asyncio.iscoroutinefunction(self.task_executor):
                result = await self.task_executor(task)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self.task_executor, task
                )
            self.task_queue.complete_task(task_id)
        except Exception as e:
            error = str(e)
            print(f"[SelfClaimLoop] 任务 {task_id} 执行异常: {error}")
            self.task_queue.fail_task(task_id)

        self.mailbox.send_message(
            from_agent=self.agent_id,
            to_agent=self._leader_agent_id,
            content=json.dumps({
                "type": "task_completed" if error is None else "task_failed",
                "taskId": task_id,
                "taskName": task.name,
                "result": result,
                "error": error
            }),
            msg_type="task_completed" if error is None else "task_failed"
        )
        self._current_task = None
        # 任务完成后清空积压的 stale 事件，让其他 Worker 公平竞争剩余任务
        self._drain_task_events()


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
