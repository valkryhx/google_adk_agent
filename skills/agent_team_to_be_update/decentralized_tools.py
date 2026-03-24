#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Decentralized Agent Team Tools (A-ish Architecture)

基于文件 + flock 的去中心化自协调工具集。
Leader 创建 DAG 并广播任务，Worker 通过 flock 竞争认领。

工具列表:
- team_create, team_join, team_leave, team_status, team_list_workers
- task_create, task_claim, task_complete, task_status, task_list
- mailbox_send, mailbox_read, mailbox_broadcast
- worker_status, worker_idle_report

所有工具使用文件协调，通过 Mailbox/TaskQueue/TeamConfig 模块实现。
"""

import asyncio
import json
import os
import time
import uuid
from typing import List, Optional, Dict, Any

try:
    from .mailbox import Mailbox, Message
    from .task_queue import TaskQueue, Task
    from .team_config import TeamConfig, TeamMember
    from .verification_hooks import TaskCompletedHook, TeammateIdleHook
except ImportError:
    from mailbox import Mailbox, Message
    from task_queue import TaskQueue, Task
    from team_config import TeamConfig, TeamMember
    from verification_hooks import TaskCompletedHook, TeammateIdleHook

# ==========================================
# 协调目录解析
# ==========================================

def _get_coordination_dir(team_id: str) -> str:
    """获取团队的协调目录路径。

    优先级:
    1. 环境变量 ADK_COORDINATION_DIR
    2. ADK_PROJECT_ROOT/coordination/{team_id}
    3. 当前目录/coordination/{team_id}
    """
    if os.environ.get("ADK_COORDINATION_DIR"):
        return os.path.join(os.environ["ADK_COORDINATION_DIR"], team_id)
    project_root = os.environ.get(
        "ADK_PROJECT_ROOT",
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    return os.path.join(project_root, "coordination", team_id)


def _get_current_agent_id() -> str:
    """获取当前 Agent 的完整 ID。

    格式: {node_type}_{port}@{project}
    例如: leader_8000@adk_swarm
    """
    port = os.environ.get("ADK_CURRENT_PORT", "0")
    project = os.environ.get("ADK_PROJECT_NAME", "adk_swarm")
    node_type = os.environ.get("ADK_NODE_TYPE", "agent")
    return f"{node_type}_{port}@{project}"


def _get_current_port() -> int:
    """获取当前 Agent 运行的端口号。"""
    return int(os.environ.get("ADK_CURRENT_PORT", 0))


# ==========================================
# Team Management Tools (Leader 使用)
# ==========================================

async def team_create(
    team_id: str,
    team_name: str = None,
    description: str = ""
) -> str:
    """
    【Leader 专用】创建一个新的 Agent Team。

    在协调目录中初始化 config.json，注册 Leader 自身为第一个成员。
    只需在集群启动时调用一次。

    Args:
        team_id: 团队唯一标识 (建议用项目名)
        team_name: 团队显示名称
        description: 团队描述

    Returns:
        创建结果报告
    """
    coord_dir = _get_coordination_dir(team_id)
    current_port = _get_current_port()
    agent_id = _get_current_agent_id()

    os.makedirs(coord_dir, exist_ok=True)

    config = TeamConfig(team_id=team_id, base_dir=os.path.dirname(coord_dir), team_name=team_name)

    # 注册 Leader 自身
    leader = TeamMember(
        name="leader",
        agent_id=agent_id,
        agent_type="leader",
        port=current_port,
        role="orchestrator",
        status="active",
        metadata={"description": description}
    )

    if config.register_member(leader):
        result = (
            f"[TEAM CREATED]\n"
            f"Team ID: {team_id}\n"
            f"Team Name: {team_name or team_id}\n"
            f"Description: {description}\n"
            f"Leader: {agent_id} (port {current_port})\n"
            f"Coordination Dir: {coord_dir}\n"
            f"\n"
            f"下一步: 使用 team_join() 让 Worker 节点加入团队。"
        )
    else:
        result = (
            f"[TEAM EXISTS] 团队 {team_id} 已存在，Leader 已注册。\n"
            f"Coordination Dir: {coord_dir}"
        )

    return result


async def team_join(
    team_id: str,
    worker_name: str = None,
    worker_type: str = "general-purpose",
    role: str = ""
) -> str:
    """
    【Worker 专用】加入一个已存在的 Agent Team。

    将当前 Worker 注册到团队的 config.json 中。
    Worker 启动时调用。

    Args:
        team_id: 团队唯一标识
        worker_name: Worker 名称 (默认为 worker_{port})
        worker_type: Agent 类型 (general-purpose / specialized)
        role: 角色描述

    Returns:
        加入结果报告
    """
    coord_dir = _get_coordination_dir(team_id)
    base_dir = os.path.dirname(coord_dir)
    current_port = _get_current_port()
    agent_id = _get_current_agent_id()

    if worker_name is None:
        worker_name = f"worker_{current_port}"

    config = TeamConfig(team_id=team_id, base_dir=base_dir)

    member = TeamMember(
        name=worker_name,
        agent_id=agent_id,
        agent_type=worker_type,
        port=current_port,
        role=role,
        status="active",
        metadata={}
    )

    if config.register_member(member):
        result = (
            f"[TEAM JOINED]\n"
            f"Team ID: {team_id}\n"
            f"Worker Name: {worker_name}\n"
            f"Agent ID: {agent_id}\n"
            f"Port: {current_port}\n"
            f"Type: {worker_type}\n"
            f"Role: {role or 'unspecified'}\n"
            f"\n"
            f"你已成功加入团队。现在可以等待任务通知或主动认领任务。"
        )
    else:
        existing = config.get_member(worker_name)
        if existing and existing.agent_id == agent_id:
            result = f"[ALREADY JOINED] Worker {worker_name} 已注册在此团队中。"
        else:
            result = f"[JOIN FAILED] Worker 名称 {worker_name} 已被占用。"

    return result


async def team_leave(team_id: str, reason: str = "") -> str:
    """
    【通用】离开 Agent Team。

    从 config.json 中注销当前 Agent。
    Agent 关闭前调用。

    Args:
        team_id: 团队唯一标识
        reason: 离开原因

    Returns:
        离开结果报告
    """
    base_dir = os.path.dirname(_get_coordination_dir(team_id))
    agent_id = _get_current_agent_id()
    current_port = _get_current_port()

    config = TeamConfig(team_id=team_id, base_dir=base_dir)

    # 查找当前 agent 对应的 name
    member_name = None
    for m in config.get_all_members():
        if m.port == current_port:
            member_name = m.name
            break

    if member_name is None:
        return f"[NOT FOUND] 当前 Agent 未注册在团队 {team_id} 中。"

    # 更新状态为 shutdown
    config.update_member_status(member_name, "shutdown")

    return (
        f"[TEAM LEFT]\n"
        f"Team ID: {team_id}\n"
        f"Worker: {member_name}\n"
        f"Reason: {reason or 'normal shutdown'}"
    )


async def team_status(
    team_id: str,
    include_workers: bool = True
) -> str:
    """
    【通用】查询团队状态。

    获取团队成员列表和状态摘要。

    Args:
        team_id: 团队唯一标识
        include_workers: 是否列出所有 Worker 详情

    Returns:
        团队状态报告
    """
    base_dir = os.path.dirname(_get_coordination_dir(team_id))
    config = TeamConfig(team_id=team_id, base_dir=base_dir)

    all_members = config.get_all_members()
    leader = config.get_leader()
    workers = config.get_worker_members()
    active = config.get_active_members()

    lines = [
        "[TEAM STATUS]",
        f"Team ID: {team_id}",
        f"Total Members: {len(all_members)}",
        f"Active: {len(active)}",
        "",
    ]

    if leader:
        lines.append(f"Leader: {leader.name} (port {leader.port}, {leader.status})")

    if include_workers and workers:
        lines.append(f"Workers ({len(workers)}):")
        for w in workers:
            status_icon = {"active": "O", "idle": "-", "busy": "@", "shutdown": "X"}.get(w.status, "?")
            lines.append(f"  [{status_icon}] {w.name} (port {w.port}, {w.status})")

    return "\n".join(lines)


async def team_list_workers(team_id: str, status_filter: str = None) -> str:
    """
    【Leader 专用】列出团队中的 Worker 节点。

    用于任务分发前的 Worker 枚举。

    Args:
        team_id: 团队唯一标识
        status_filter: 可选，按状态过滤 (active/idle/busy/shutdown)

    Returns:
        Worker 列表报告
    """
    base_dir = os.path.dirname(_get_coordination_dir(team_id))
    config = TeamConfig(team_id=team_id, base_dir=base_dir)

    workers = config.get_worker_members()
    if status_filter:
        workers = [w for w in workers if w.status == status_filter]

    if not workers:
        return f"[NO WORKERS] 团队 {team_id} 中没有可用 Worker。"

    lines = [f"[WORKERS] team={team_id} count={len(workers)}", ""]
    for w in workers:
        lines.append(f"  - {w.name} | port={w.port} | status={w.status} | role={w.role or 'unspecified'}")

    lines.append("")
    lines.append(f"总计: {len(workers)} 个 Worker")
    return "\n".join(lines)


# ==========================================
# Task Management Tools
# ==========================================

async def task_create(
    team_id: str,
    name: str,
    description: str = "",
    blocked_by: List[str] = None,
    expected_artifacts: List[str] = None,
    writable_files: List[str] = None,
    read_only_files: List[str] = None,
    task_type: str = "regular",
    priority: str = "NORMAL"
) -> str:
    """
    【Leader 专用】创建一个任务并广播通知。

    创建任务后，向所有活跃 Worker 广播 mailbox 通知。

    Args:
        team_id: 团队唯一标识
        name: 任务名称
        description: 任务描述
        blocked_by: 依赖的任务 ID 列表
        expected_artifacts: 期望产出的文件路径
        writable_files: 可写文件列表
        read_only_files: 只读文件列表
        task_type: 任务类型 (regular/gate/loop)
        priority: 优先级 (LOW/NORMAL/HIGH/URGENT)

    Returns:
        创建结果，包含 task_id
    """
    coord_dir = _get_coordination_dir(team_id)
    base_dir = os.path.dirname(coord_dir)

    queue = TaskQueue(team_id=team_id, base_dir=coord_dir)

    task = queue.create_task(
        name=name,
        description=description,
        blocked_by=blocked_by or [],
        expected_artifacts=expected_artifacts or [],
        writable_files=writable_files or [],
        read_only_files=read_only_files or [],
        task_type=task_type
    )

    # 广播任务通知给所有 Worker
    mailbox = Mailbox(base_dir=coord_dir)
    config = TeamConfig(team_id=team_id, base_dir=base_dir)

    workers = config.get_worker_members()
    broadcast_content = json.dumps({
        "type": "task_broadcast",
        "taskId": task.id,
        "taskName": name,
        "priority": priority,
        "blockedBy": blocked_by or [],
        "description": description[:200] if description else ""
    })

    notified = 0
    for w in workers:
        if w.status == "active":
            mailbox.send_message(
                from_agent=_get_current_agent_id(),
                to_agent=w.agent_id,
                content=broadcast_content,
                msg_type="task_broadcast"
            )
            notified += 1

    return (
        f"[TASK CREATED]\n"
        f"Task ID: {task.id}\n"
        f"Name: {name}\n"
        f"Type: {task_type}\n"
        f"Priority: {priority}\n"
        f"Blocked By: {blocked_by or 'none'}\n"
        f"Notified Workers: {notified}/{len(workers)}\n"
        f"\n"
        f"Workers 将通过 flock 竞争认领此任务。"
    )


async def task_claim(
    team_id: str,
    task_id: str = None,
    prefer_first: bool = False
) -> str:
    """
    【Worker 专用】尝试认领一个任务。

    如果 task_id 为空，主动从 get_available_tasks() 获取第一个。
    使用 flock 文件锁实现竞争。

    Args:
        team_id: 团队唯一标识
        task_id: 指定的任务 ID (可选)
        prefer_first: True=优先认领第一个可用任务，False=认领指定 ID

    Returns:
        认领结果报告
    """
    coord_dir = _get_coordination_dir(team_id)
    agent_id = _get_current_agent_id()

    queue = TaskQueue(team_id=team_id, base_dir=coord_dir)

    target_id = task_id

    if target_id is None or prefer_first:
        available = queue.get_available_tasks()
        if not available:
            return (
                f"[NO TASKS] 当前没有可认领的任务。\n"
                f"请等待 Leader 创建新任务。"
            )
        target_id = available[0].id

    if queue.claim_task(target_id, agent_id):
        task = queue.get_task(target_id)
        return (
            f"[TASK CLAIMED]\n"
            f"Task ID: {target_id}\n"
            f"Name: {task.name if task else 'unknown'}\n"
            f"Owner: {agent_id}\n"
            f"\n"
            f"请开始执行任务，完成后调用 task_complete()。"
        )
    else:
        return (
            f"[CLAIM FAILED] 任务 {target_id} 被其他 Worker 抢走了。\n"
            f"flock 竞争失败，尝试认领其他任务。"
        )


async def task_complete(
    team_id: str,
    task_id: str,
    result: str = "",
    error: str = None,
    artifacts: List[str] = None
) -> str:
    """
    【Worker 专用】标记任务完成并通知 Leader。

    完成任务后，通过 Mailbox 向 Leader 发送完成通知。

    Args:
        team_id: 团队唯一标识
        task_id: 任务 ID
        result: 执行结果摘要
        error: 错误信息 (如有)
        artifacts: 产出文件列表

    Returns:
        完成结果报告
    """
    coord_dir = _get_coordination_dir(team_id)
    base_dir = os.path.dirname(coord_dir)
    agent_id = _get_current_agent_id()

    queue = TaskQueue(team_id=team_id, base_dir=coord_dir)

    task = queue.get_task(task_id)
    if task is None:
        return f"[ERROR] 任务 {task_id} 不存在。"

    # VerificationHooks 集成：完成前校验产出物与质量门禁
    workdir = os.getcwd()
    hook = TaskCompletedHook(workdir)
    # 从任务字段中读取期望产出文件和验证命令（若无则跳过对应项）
    if task.expected_artifacts:
        hook.set_required_files(task.expected_artifacts)
    if task.verification_commands:
        hook.set_verification_commands(task.verification_commands)
    # git 检查默认关闭（Agent 环境不保证 git 干净）
    hook.require_git_clean = False

    vr = hook.verify()
    if not vr.allowed:
        return (
            f"[BLOCKED] 任务 {task_id} 未通过完成验证，操作被拦截。\n"
            f"原因: {vr.reason}\n"
            f"建议: {vr.action}"
        )

    queue.complete_task(task_id)

    # 通知 Leader
    mailbox = Mailbox(base_dir=coord_dir)
    config = TeamConfig(team_id=team_id, base_dir=base_dir)
    leader = config.get_leader()

    if leader:
        completion_msg = json.dumps({
            "type": "task_completed",
            "taskId": task_id,
            "taskName": task.name,
            "worker": agent_id,
            "result": result[:2000] if result else "",
            "error": error,
            "artifacts": artifacts or []
        })
        mailbox.send_message(
            from_agent=agent_id,
            to_agent=leader.agent_id,
            content=completion_msg,
            msg_type="task_completed"
        )

    return (
        f"[TASK COMPLETED]\n"
        f"Task ID: {task_id}\n"
        f"Task Name: {task.name}\n"
        f"Worker: {agent_id}\n"
        f"Result: {result[:500] if result else 'no output'}\n"
        f"{f'Error: {error}' if error else ''}\n"
        f"\n"
        f"Leader 已收到完成通知。"
    )


async def task_status(
    team_id: str,
    task_id: str = None,
    show_all: bool = False
) -> str:
    """
    【通用】查询任务状态。

    Args:
        team_id: 团队唯一标识
        task_id: 任务 ID (可选，为空则列出所有)
        show_all: 是否显示所有任务

    Returns:
        任务状态报告
    """
    coord_dir = _get_coordination_dir(team_id)
    queue = TaskQueue(team_id=team_id, base_dir=coord_dir)

    if task_id:
        task = queue.get_task(task_id)
        if task is None:
            return f"[NOT FOUND] 任务 {task_id} 不存在。"
        return (
            f"[TASK STATUS]\n"
            f"ID: {task.id}\n"
            f"Name: {task.name}\n"
            f"Status: {task.status}\n"
            f"Owner: {task.owner or 'unclaimed'}\n"
            f"Type: {task.task_type}\n"
            f"Blocked By: {task.blocked_by or 'none'}\n"
            f"Created: {task.created_at}\n"
            f"Description: {task.description or 'none'}"
        )

    all_tasks = queue.list_tasks()
    if not all_tasks:
        return f"[NO TASKS] 团队 {team_id} 没有任何任务。"

    stats = queue.get_task_stats()
    lines = [
        f"[TASK STATUS] team={team_id}",
        f"Total: {stats['total']} | Pending: {stats['pending']} | "
        f"In Progress: {stats['in_progress']} | Completed: {stats['completed']}",
        ""
    ]

    if show_all:
        for t in all_tasks:
            owner_str = t.owner or "unclaimed"
            lines.append(f"  [{t.status:12}] {t.id[:16]}... | {t.name} | owner={owner_str}")
    else:
        pending = [t for t in all_tasks if t.status == "pending"]
        for t in pending:
            lines.append(f"  [PENDING] {t.id[:16]}... | {t.name}")

    return "\n".join(lines)


async def task_list(
    team_id: str,
    status: str = None,
    limit: int = 50
) -> str:
    """
    【通用】列出任务列表。

    Args:
        team_id: 团队唯一标识
        status: 按状态过滤 (pending/in_progress/completed)
        limit: 返回数量上限

    Returns:
        任务列表报告
    """
    coord_dir = _get_coordination_dir(team_id)
    queue = TaskQueue(team_id=team_id, base_dir=coord_dir)

    tasks = queue.list_tasks(status=status)
    tasks = tasks[:limit]

    if not tasks:
        filter_str = f" (status={status})" if status else ""
        return f"[NO TASKS] 团队 {team_id} 没有符合条件的任务{filter_str}。"

    lines = [
        f"[TASK LIST] team={team_id}{f' status={status}' if status else ''} count={len(tasks)}",
        ""
    ]
    for t in tasks:
        lines.append(
            f"  [{t.status:12}] {t.id[:20]} | {t.name[:40]} | "
            f"owner={t.owner or 'none'[:20] if t.owner else 'none'}"
        )

    return "\n".join(lines)


# ==========================================
# Mailbox / Messaging Tools
# ==========================================

async def mailbox_send(
    team_id: str,
    to_agent: str,
    content: str,
    msg_type: str = "text",
    metadata: Dict[str, Any] = None
) -> str:
    """
    【通用】向指定 Agent 发送消息。

    Args:
        team_id: 团队唯一标识
        to_agent: 目标 Agent ID (或名称如 "leader")
        content: 消息内容
        msg_type: 消息类型 (text/task_broadcast/task_completed/shutdown_request)
        metadata: 附加元数据

    Returns:
        发送结果
    """
    coord_dir = _get_coordination_dir(team_id)
    base_dir = os.path.dirname(coord_dir)
    agent_id = _get_current_agent_id()

    mailbox = Mailbox(base_dir=coord_dir)

    # 支持用名称查找 agent_id
    config = TeamConfig(team_id=team_id, base_dir=base_dir)
    target_id = to_agent
    if to_agent != "leader":
        member = config.get_member(to_agent)
        if member:
            target_id = member.agent_id

    msg_id = mailbox.send_message(
        from_agent=agent_id,
        to_agent=target_id,
        content=content,
        msg_type=msg_type,
        metadata=metadata or {}
    )

    return (
        f"[MESSAGE SENT]\n"
        f"Message ID: {msg_id}\n"
        f"To: {target_id}\n"
        f"Type: {msg_type}\n"
        f"Content: {content[:200]}{'...' if len(content) > 200 else ''}"
    )


async def mailbox_read(
    team_id: str,
    mark_read: bool = False,
    unread_only: bool = True
) -> str:
    """
    【通用】读取当前 Agent 的收件箱消息。

    Args:
        team_id: 团队唯一标识
        mark_read: 是否标记消息为已读
        unread_only: 是否只返回未读消息

    Returns:
        消息列表报告
    """
    coord_dir = _get_coordination_dir(team_id)
    agent_id = _get_current_agent_id()

    mailbox = Mailbox(base_dir=coord_dir)
    messages = mailbox.read_messages(
        agent_id=agent_id,
        mark_read=mark_read,
        unread_only=unread_only
    )

    if not messages:
        return "[NO MESSAGES] 收件箱为空。"

    lines = [f"[MAILBOX] {len(messages)} 条消息", ""]
    for i, msg in enumerate(messages):
        time_str = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
        content_preview = msg.content[:150].replace("\n", " ")
        lines.append(
            f"  [{i+1}] {time_str} | from={msg.from_agent[:30]} | "
            f"type={msg.msg_type} | read={msg.read}"
        )
        lines.append(f"       {content_preview}...")
        lines.append("")

    return "\n".join(lines)


async def mailbox_broadcast(
    team_id: str,
    content: str,
    msg_type: str = "broadcast",
    target_type: str = "all"  # all / workers / leader
) -> str:
    """
    【Leader 专用】广播消息给团队成员。

    Args:
        team_id: 团队唯一标识
        content: 广播内容
        msg_type: 消息类型
        target_type: 目标类型 (all/workers/leader)

    Returns:
        广播结果
    """
    coord_dir = _get_coordination_dir(team_id)
    base_dir = os.path.dirname(coord_dir)
    agent_id = _get_current_agent_id()

    mailbox = Mailbox(base_dir=coord_dir)
    config = TeamConfig(team_id=team_id, base_dir=base_dir)

    targets = []
    if target_type in ("all", "workers"):
        targets.extend(config.get_worker_members())
    if target_type in ("all", "leader"):
        leader = config.get_leader()
        if leader:
            targets.append(leader)

    sent = 0
    for member in targets:
        if member.agent_id != agent_id:
            mailbox.send_message(
                from_agent=agent_id,
                to_agent=member.agent_id,
                content=content,
                msg_type=msg_type
            )
            sent += 1

    return (
        f"[BROADCAST SENT]\n"
        f"Team: {team_id}\n"
        f"Target: {target_type}\n"
        f"Recipients: {sent}\n"
        f"Content: {content[:200]}{'...' if len(content) > 200 else ''}"
    )


# ==========================================
# Worker Self-Management Tools
# ==========================================

async def worker_status(
    team_id: str,
    status: str = None,
    detail: str = ""
) -> str:
    """
    【Worker 专用】更新自身状态。

    Args:
        team_id: 团队唯一标识
        status: 新状态 (active/idle/busy/shutdown_requested)
        detail: 状态详情

    Returns:
        更新结果
    """
    base_dir = os.path.dirname(_get_coordination_dir(team_id))
    current_port = _get_current_port()

    config = TeamConfig(team_id=team_id, base_dir=base_dir)

    # 查找当前 worker 的 name
    member_name = None
    for m in config.get_all_members():
        if m.port == current_port:
            member_name = m.name
            break

    if member_name is None:
        return f"[NOT FOUND] 当前 Worker 未注册在团队 {team_id} 中。"

    config.update_member_status(member_name, status)

    return (
        f"[WORKER STATUS UPDATED]\n"
        f"Worker: {member_name}\n"
        f"Status: {status}\n"
        f"Detail: {detail or 'none'}"
    )


async def worker_idle_report(team_id: str, reason: str = "available") -> str:
    """
    【Worker 专用】向 Leader 报告自身空闲。

    当 Worker 空闲多轮后，主动通知 Leader。

    Args:
        team_id: 团队唯一标识
        reason: 空闲原因

    Returns:
        报告结果
    """
    coord_dir = _get_coordination_dir(team_id)
    base_dir = os.path.dirname(coord_dir)
    agent_id = _get_current_agent_id()

    mailbox = Mailbox(base_dir=coord_dir)
    config = TeamConfig(team_id=team_id, base_dir=base_dir)
    leader = config.get_leader()

    # VerificationHooks 集成：空闲前校验产出物与验证命令
    workdir = os.getcwd()
    idle_hook = TeammateIdleHook(workdir)
    vr = idle_hook.verify()
    if not vr.allowed:
        return (
            f"[BLOCKED] Worker 空闲上报被拦截，请先完成待处理工作。\n"
            f"原因: {vr.reason}\n"
            f"建议: {vr.action}"
        )

    if leader:
        idle_msg = json.dumps({
            "type": "idle_notification",
            "from": agent_id,
            "reason": reason,
            "timestamp": time.time()
        })
        mailbox.send_message(
            from_agent=agent_id,
            to_agent=leader.agent_id,
            content=idle_msg,
            msg_type="idle_notification"
        )

    return (
        f"[IDLE REPORT SENT]\n"
        f"Team: {team_id}\n"
        f"Worker: {agent_id}\n"
        f"Reason: {reason}"
    )


# ==========================================
# Batch / DAG Creation Tool
# ==========================================

async def dag_create(
    team_id: str,
    tasks: List[Dict[str, Any]],
    broadcast: bool = True
) -> str:
    """
    【Leader 专用】批量创建 DAG 任务并可选广播。

    一次创建多个任务，自动处理依赖关系，并广播通知所有 Worker。

    Args:
        team_id: 团队唯一标识
        tasks: 任务定义列表，每个 dict 包含:
            - name: 任务名称
            - description: 任务描述 (可选)
            - blocked_by: 依赖的任务名称列表 (可选)
            - task_type: regular/gate (可选)
        broadcast: 是否广播通知 Worker

    Returns:
        创建结果报告，包含所有 task_id

    Example:
        dag_create(team_id="my_proj", tasks=[
            {"name": "task1", "description": "调研市场"},
            {"name": "task2", "description": "写代码", "blocked_by": ["task1"]},
        ])
    """
    coord_dir = _get_coordination_dir(team_id)
    base_dir = os.path.dirname(coord_dir)
    agent_id = _get_current_agent_id()

    queue = TaskQueue(team_id=team_id, base_dir=coord_dir)
    mailbox = Mailbox(base_dir=coord_dir)
    config = TeamConfig(team_id=team_id, base_dir=base_dir)

    # 第一遍：创建所有任务，建立 name -> id 映射
    name_to_id = {}
    created_tasks = []

    for task_def in tasks:
        blocked_by_ids = []
        for dep_name in task_def.get("blocked_by", []):
            if dep_name in name_to_id:
                blocked_by_ids.append(name_to_id[dep_name])

        task = queue.create_task(
            name=task_def["name"],
            description=task_def.get("description", ""),
            blocked_by=blocked_by_ids,
            expected_artifacts=task_def.get("expected_artifacts", []),
            writable_files=task_def.get("writable_files", []),
            read_only_files=task_def.get("read_only_files", []),
            task_type=task_def.get("task_type", "regular")
        )
        name_to_id[task_def["name"]] = task.id
        created_tasks.append(task)

    # 第二遍：广播通知
    if broadcast:
        workers = config.get_worker_members()
        notified = 0
        for task in created_tasks:
            broadcast_content = json.dumps({
                "type": "task_broadcast",
                "taskId": task.id,
                "taskName": task.name,
                "blockedBy": task.blocked_by,
                "description": task.description[:200] if task.description else ""
            })
            for w in workers:
                if w.status == "active":
                    mailbox.send_message(
                        from_agent=agent_id,
                        to_agent=w.agent_id,
                        content=broadcast_content,
                        msg_type="task_broadcast"
                    )
                    notified += 1

        workers_count = len(workers)
    else:
        notified = 0
        workers_count = len(config.get_worker_members())

    lines = [
        f"[DAG CREATED] team={team_id}",
        f"Tasks Created: {len(created_tasks)}",
        f"Workers Notified: {notified}",
        "",
        "Task ID Map:"
    ]
    for task in created_tasks:
        deps = ", ".join(task.blocked_by) if task.blocked_by else "none"
        lines.append(f"  {task.name}: {task.id} (blocked_by: {deps})")

    return "\n".join(lines)


# ==========================================
# get_tools - 返回去中心化工具集
# ==========================================

def get_decentralized_tools():
    """
    返回去中心化自协调工具集。
    
    供 Agent (Leader 或 Worker) 注册使用。
    """
    return [
        # Team Management
        team_create,
        team_join,
        team_leave,
        team_status,
        team_list_workers,
        # Task Management
        task_create,
        task_claim,
        task_complete,
        task_status,
        task_list,
        # Mailbox / Messaging
        mailbox_send,
        mailbox_read,
        mailbox_broadcast,
        # Worker Self-Management
        worker_status,
        worker_idle_report,
        # DAG
        dag_create,
    ]
