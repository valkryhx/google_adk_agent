#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
================================================================================
Agent Team DAG 测试脚本 - 博客系统开发示例
================================================================================

【使用方式】

## 1. 独立运行测试

直接在命令行运行：
```bash
cd D:\git_codes\google_adk_helloworld_git\skills\agent_team_to_be_update\test
python test_blog_system_develop.py
```

## 2. 在 Swarm 集群中使用

启动集群后 (start_demo_swarm.bat)，在 Web 界面输入：
```
测试任务依赖系统：
- 让 Worker 8001 创建用户模块（Schema + API + 前端）
- 让 Worker 8002 创建文章模块（依赖用户模块）
- 让 Worker 8003 创建评论模块（依赖用户和文章模块）
- 最后做集成测试
```

## 3. 导入模块到你的代码

```python
import sys
sys.path.insert(0, 'skills/agent_team_to_be_update')

from models import Task
from task_queue import TaskQueue
from mailbox import Mailbox
from path_guard import PathGuard
from verification_hooks import TeammateIdleHook, TaskCompletedHook
from planner import TaskPlanner
```

================================================================================
【测试内容】

本脚本测试 Claude Code 风格的 Agent Team DAG 任务依赖系统：

1. Task 数据模型 - 支持 blockedBy 依赖声明
2. TaskQueue 任务队列 - 文件锁抢任务机制
3. Wave 执行顺序 - 自动计算可并行执行的任务
4. Mailbox 通信 - Agent 间点对点消息
5. PathGuard 路径守卫 - 防止访问禁止目录

================================================================================
"""

import sys
import os
import tempfile
import shutil

if sys.platform == "win32":
    import codecs
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Task
from task_queue import TaskQueue


def print_task(task: Task, indent: str = "  "):
    """打印任务信息"""
    print(f"{indent}Task: {task.name}")
    print(f"{indent}   ID: {task.id}")
    print(f"{indent}   Status: {task.status}")
    print(f"{indent}   Owner: {task.owner or '(unclaimed)'}")
    if task.blocked_by:
        print(f"{indent}   blockedBy: {task.blocked_by}")
    print()


def test_basic_dag():
    """测试基础 DAG 功能"""
    print("=" * 60)
    print("测试 1: 基础 DAG - 博客系统开发")
    print("=" * 60)
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="agent_team_test_")
    print(f"测试目录: {temp_dir}\n")
    
    try:
        # 初始化任务队列
        queue = TaskQueue(team_id="test_blog", base_dir=temp_dir)
        
        # 创建 DAG 任务结构：
        # 
        # Task 1: 设计 Schema (无依赖)
        #     |
        # Task 2: 实现后端 API (blockedBy: 1)
        #     |
        # Task 3: 实现前端页面 (blockedBy: 2)
        # Task 4: 编写测试 (blockedBy: 2)
        #     |
        # Task 5: 集成测试 (blockedBy: 3, 4)
        
        print("创建任务...")
        
        # Task 1: 无依赖
        task1 = queue.create_task(
            name="设计数据库 Schema",
            description="设计用户表、文章表、评论表的字段结构",
            expected_artifacts=["docs/schema.md"],
            writable_files=["docs/schema.md"]
        )
        print(f"  [OK] Task 1: {task1.name}")
        
        # Task 2: blockedBy Task 1
        task2 = queue.create_task(
            name="实现后端 API",
            description="实现 CRUD 接口",
            blocked_by=[task1.id],
            expected_artifacts=["src/api/users.py", "src/api/posts.py"],
            writable_files=["src/api/"],
            read_only_files=["docs/schema.md"]
        )
        print(f"  [OK] Task 2: {task2.name} (blockedBy: {task1.id})")
        
        # Task 3: blockedBy Task 2
        task3 = queue.create_task(
            name="实现前端页面",
            description="实现用户列表和文章页面",
            blocked_by=[task2.id],
            expected_artifacts=["src/frontend/index.html"],
            writable_files=["src/frontend/"],
            read_only_files=["src/api/"]
        )
        print(f"  [OK] Task 3: {task3.name} (blockedBy: {task2.id})")
        
        # Task 4: blockedBy Task 2 (与 Task 3 并行)
        task4 = queue.create_task(
            name="编写测试",
            description="为 API 编写单元测试",
            blocked_by=[task2.id],
            expected_artifacts=["tests/test_api.py"],
            writable_files=["tests/"],
            read_only_files=["src/api/"]
        )
        print(f"  [OK] Task 4: {task4.name} (blockedBy: {task2.id})")
        
        # Task 5: blockedBy Task 3 和 Task 4
        task5 = queue.create_task(
            name="集成测试",
            description="端到端测试",
            blocked_by=[task3.id, task4.id],
            expected_artifacts=["tests/e2e_test.py"],
            writable_files=["tests/"]
        )
        print(f"  [OK] Task 5: {task5.name} (blockedBy: {task3.id}, {task4.id})")
        
        print("\n" + "=" * 60)
        print("任务依赖图 (DAG)")
        print("=" * 60)
        print("""
    [Task 1: 设计 Schema]
           |
           V
    [Task 2: 实现后端 API]
           |
     +-----+-----+
     V           V
[Task 3: 前端] [Task 4: 测试]
     |           |
     +-----+-----+
           V
    [Task 5: 集成测试]
        """)
        
        # 显示所有任务
        print("\n" + "=" * 60)
        print("所有任务")
        print("=" * 60)
        for task in queue.list_tasks():
            print_task(task)
        
        # 测试可用任务计算
        print("\n" + "=" * 60)
        print("可用任务 (无依赖或依赖已满足)")
        print("=" * 60)
        available = queue.get_available_tasks()
        for task in available:
            print(f"  -> {task.name}")
        
        # 测试任务认领
        print("\n" + "=" * 60)
        print("测试文件锁抢任务")
        print("=" * 60)
        
        # Worker 1 尝试认领 Task 1
        success1 = queue.claim_task(task1.id, "worker-8001")
        print(f"  Worker 8001 认领 Task 1: {('[OK]' if success1 else '[FAIL]')}")
        
        # Worker 2 尝试认领 Task 1 (应该失败)
        success2 = queue.claim_task(task1.id, "worker-8002")
        print(f"  Worker 8002 认领 Task 1: {('[OK]' if success2 else '[FAIL] 被抢走了')}")
        
        # Worker 2 尝试认领 Task 2 (应该失败 - 依赖未完成)
        success3 = queue.claim_task(task2.id, "worker-8002")
        print(f"  Worker 8002 认领 Task 2: {('[OK]' if success3 else '[FAIL] Task 1 未完成')}")
        
        # 完成 Task 1
        print("\n  Worker 8001 完成 Task 1...")
        queue.complete_task(task1.id)
        print("  Task 1 已标记完成")
        
        # 再次检查可用任务
        print("\n" + "=" * 60)
        print("Task 1 完成后，可用的任务")
        print("=" * 60)
        available = queue.get_available_tasks()
        for task in available:
            print(f"  -> {task.name}")
        
        # Worker 2 现在可以认领 Task 2
        success4 = queue.claim_task(task2.id, "worker-8002")
        print(f"\n  Worker 8002 认领 Task 2: {('[OK]' if success4 else '[FAIL]')}")
        
        # 测试 Wave 计算
        print("\n" + "=" * 60)
        print("执行 Wave 分析")
        print("=" * 60)
        
        # 模拟完成所有任务
        queue.complete_task(task2.id)
        queue.claim_task(task3.id, "worker-8001")
        queue.claim_task(task4.id, "worker-8003")
        
        available = queue.get_available_tasks()
        print(f"  Wave 1 (Task 1, 2 完成):")
        print(f"    可用: {[t.name for t in available]}")
        
        queue.complete_task(task3.id)
        queue.complete_task(task4.id)
        
        available = queue.get_available_tasks()
        print(f"  Wave 2 (Task 3, 4 完成):")
        print(f"    可用: {[t.name for t in available]}")
        
        # 统计
        print("\n" + "=" * 60)
        print("最终统计")
        print("=" * 60)
        stats = queue.get_task_stats()
        print(f"  总任务数: {stats['total']}")
        print(f"  已完成: {stats['completed']}")
        print(f"  进行中: {stats['in_progress']}")
        print(f"  等待中: {stats['pending']}")
        
        print("\n" + "=" * 60)
        print("DAG 测试完成!")
        print("=" * 60)
        
    finally:
        # 清理
        print(f"\n清理测试目录: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_mailbox():
    """测试 Mailbox 通信"""
    print("\n" + "=" * 60)
    print("测试 Mailbox Agent 间通信")
    print("=" * 60)
    
    from mailbox import Mailbox, Message
    
    temp_dir = tempfile.mkdtemp(prefix="mailbox_test_")
    
    try:
        mb = Mailbox(base_dir=temp_dir)
        
        # Worker 8001 发送消息给 Lead
        msg_id = mb.send_message(
            from_agent="worker-8001",
            to_agent="lead",
            content="Task 1 已完成!",
            msg_type="task_completed",
            metadata={"task_id": "task-1", "artifacts": ["docs/schema.md"]}
        )
        print(f"  [OK] Worker 8001 -> Lead: 消息 ID = {msg_id}")
        
        # Lead 发送消息给 Worker 8002
        msg_id2 = mb.send_message(
            from_agent="lead",
            to_agent="worker-8002",
            content="开始 Task 2",
            msg_type="task_assignment"
        )
        print(f"  [OK] Lead -> Worker 8002: 消息 ID = {msg_id2}")
        
        # Worker 8002 检查收件箱
        messages = mb.read_messages("worker-8002")
        print(f"  Worker 8002 收件箱: {len(messages)} 条消息")
        for msg in messages:
            print(f"     - [{msg.msg_type}] {msg.content}")
        
        # Lead 检查收件箱
        messages = mb.read_messages("lead")
        print(f"  Lead 收件箱: {len(messages)} 条消息")
        
        # 广播测试
        print("\n  测试广播...")
        mb.broadcast(
            from_agent="lead",
            content="所有 Worker 停止工作!",
            agent_ids=["worker-8001", "worker-8002", "worker-8003"]
        )
        print("  [OK] 广播已发送")
        
        print("\nMailbox 测试完成!")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_path_guard():
    """测试路径守卫"""
    print("\n" + "=" * 60)
    print("测试 PathGuard 路径守卫")
    print("=" * 60)
    
    from path_guard import PathGuard
    
    # 模拟项目目录
    project_dir = "D:\\projects\\my_blog"
    
    # Agent 目录 (禁止 Worker 访问)
    agent_dir = "D:\\git_codes\\google_adk_agent\\skills"
    
    guard = PathGuard(
        allowed_root=project_dir,
        forbidden_paths=[agent_dir]
    )
    
    # 测试允许的路径
    test_cases = [
        ("D:\\projects\\my_blog\\src\\api\\users.py", True, "项目内文件"),
        ("D:\\projects\\my_blog\\docs\\schema.md", True, "项目内文档"),
        ("D:\\git_codes\\google_adk_agent\\skills\\agent_team\\tools.py", False, "Agent 目录 (禁止)"),
        ("D:\\windows\\system32\\config.sys", False, "系统目录 (禁止)"),
    ]
    
    for path, expected, description in test_cases:
        result = guard.is_allowed(path)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"  {status} {description}: {result}")
    
    print("\nPathGuard 测试完成!")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Agent Team DAG 系统测试")
    print("=" * 60 + "\n")
    
    # 测试 DAG 功能
    test_basic_dag()
    
    # 测试 Mailbox
    test_mailbox()
    
    # 测试 PathGuard
    test_path_guard()
    
    print("\n" + "=" * 60)
    print("所有测试完成!")
    print("=" * 60)
