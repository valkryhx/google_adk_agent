#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
================================================================================
Agent Team DAG 测试脚本 - Deep Research 智能体开发示例
================================================================================

【使用方式】

## 1. 独立运行测试

直接在命令行运行：
```bash
cd D:\git_codes\google_adk_helloworld_git\skills\agent_team_to_be_update\test
python test_deepresearch.py
```

## 2. 在 Swarm 集群中使用

启动集群后 (start_demo_swarm.bat)，在 Web 界面输入：
```
开发一个 Deep Research 智能体，研究主题：AI Agent 在 2026 年的发展趋势

需要完成：
1. 规划研究路线
2. 并行搜索多个信息源（OpenAI、Google、Anthropic 等）
3. 提取关键信息
4. 交叉验证
5. 生成研究报告
```

## 3. 核心概念

Deep Research = DeepSearch + 交叉验证 + 结构化报告

DeepSearch 循环：
    搜索 -> 阅读 -> 推理 -> 再次搜索 -> ...
    (直到信息充分或达到迭代上限)

================================================================================
【测试内容】

本脚本测试 Claude Code 风格的 Agent Team DAG，用于开发 Deep Research 智能体：

DAG 任务结构：
```
[Task 1: 规划研究路线]  (无依赖)
        |
        V
[Task 2a: 搜索 OpenAI]  (依赖1，并行)
[Task 2b: 搜索 Google]   (依赖1，并行)
[Task 2c: 搜索 Anthropic] (依赖1，并行)
        |
        V
[Task 3: 信息提取与验证]  (依赖 2a,2b,2c)
        |
        V
[Task 4: 撰写研究报告]  (依赖3)
        |
        V
[Task 5: 引用整理]      (依赖4)
```

================================================================================
【API 配置】

使用的 API (来自 private_key.yaml):
- Tavily API: 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
- Exa API: 8a05237e-ae81-4331-b0f2-a50818514ade

================================================================================
"""

import sys
import os
import tempfile
import shutil
import time

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Task
from task_queue import TaskQueue
from mailbox import Mailbox, Message


def print_task(task: Task, indent: str = "  "):
    """打印任务信息"""
    print(f"{indent}[{task.status.upper()}] {task.name}")
    print(f"{indent}    ID: {task.id}")
    print(f"{indent}    Owner: {task.owner or '(unclaimed)'}")
    if task.blocked_by:
        print(f"{indent}    blockedBy: {task.blocked_by}")
    print()


def simulate_worker(worker_id: str, task: Task, delay: float = 0.5):
    """模拟 Worker 执行任务"""
    print(f"    [{worker_id}] 开始执行: {task.name}")
    time.sleep(delay)
    print(f"    [{worker_id}] 完成: {task.name}")
    return True


def test_deepresearch_dag():
    """测试 Deep Research DAG"""
    print("=" * 70)
    print("Deep Research 智能体开发 - DAG 任务依赖测试")
    print("=" * 70)
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="deepresearch_test_")
    print(f"测试目录: {temp_dir}\n")
    
    try:
        # 初始化任务队列
        queue = TaskQueue(team_id="deepresearch", base_dir=temp_dir)
        mb = Mailbox(base_dir=temp_dir)
        
        print("=" * 70)
        print("Step 1: 创建 Deep Research 任务 DAG")
        print("=" * 70)
        
        # Task 1: 规划研究路线 (无依赖)
        task1 = queue.create_task(
            name="规划研究路线",
            description="确定研究主题，制定搜索策略，规划信息源分布",
            expected_artifacts=["research_plan.md"],
            writable_files=["research_plan.md"]
        )
        print(f"  [1] Task 1: {task1.name} (无依赖)")
        
        # Task 2a-c: 并行搜索 (都依赖 Task 1)
        task2a = queue.create_task(
            name="搜索 OpenAI Agent 信息",
            description="使用 Tavily API 搜索 OpenAI 的 Agent/GPT 相关更新",
            blocked_by=[task1.id],
            expected_artifacts=["data/openai_agents.json"],
            writable_files=["data/"],
            verification_commands=["test -f data/openai_agents.json"]
        )
        print(f"  [2a] Task 2a: {task2a.name} (blockedBy: {task1.id})")
        
        task2b = queue.create_task(
            name="搜索 Google Agent 信息",
            description="使用 Exa API 搜索 Google Gemini/Agent 最新进展",
            blocked_by=[task1.id],
            expected_artifacts=["data/google_agents.json"],
            writable_files=["data/"],
            verification_commands=["test -f data/google_agents.json"]
        )
        print(f"  [2b] Task 2b: {task2b.name} (blockedBy: {task1.id})")
        
        task2c = queue.create_task(
            name="搜索 Anthropic Agent 信息",
            description="搜索 Claude/MCP/Agent 相关技术",
            blocked_by=[task1.id],
            expected_artifacts=["data/anthropic_agents.json"],
            writable_files=["data/"],
            verification_commands=["test -f data/anthropic_agents.json"]
        )
        print(f"  [2c] Task 2c: {task2c.name} (blockedBy: {task1.id})")
        
        # Task 3: 信息提取与验证 (依赖 2a, 2b, 2c)
        task3 = queue.create_task(
            name="信息提取与交叉验证",
            description="从三个信息源提取关键信息，进行交叉验证",
            blocked_by=[task2a.id, task2b.id, task2c.id],
            expected_artifacts=["extracted_findings.json"],
            writable_files=["extracted_findings.json"]
        )
        print(f"  [3] Task 3: {task3.name} (blockedBy: 2a, 2b, 2c)")
        
        # Task 4: 撰写报告 (依赖 Task 3)
        task4 = queue.create_task(
            name="撰写研究报告",
            description="基于验证后的信息，撰写结构化研究报告",
            blocked_by=[task3.id],
            expected_artifacts=["report.md"],
            writable_files=["report.md"]
        )
        print(f"  [4] Task 4: {task4.name} (blockedBy: {task3.id})")
        
        # Task 5: 引用整理 (依赖 Task 4)
        task5 = queue.create_task(
            name="引用整理与格式化",
            description="整理所有引用来源，格式化最终报告",
            blocked_by=[task4.id],
            expected_artifacts=["final_report.md"],
            writable_files=["final_report.md"],
            read_only_files=["report.md"]
        )
        print(f"  [5] Task 5: {task5.name} (blockedBy: {task4.id})")
        
        # 显示 DAG 图
        print("\n" + "=" * 70)
        print("Deep Research DAG 任务依赖图")
        print("=" * 70)
        print("""
                    [Task 1: 规划研究路线]
                              |
                              V
           +------------------+------------------+
           |                  |                  |
           V                  V                  V
    [Task 2a: OpenAI]  [Task 2b: Google]  [Task 2c: Anthropic]
           |                  |                  |
           +------------------+------------------+
                              |
                              V
                    [Task 3: 信息提取与验证]
                              |
                              V
                    [Task 4: 撰写研究报告]
                              |
                              V
                    [Task 5: 引用整理]
        """)
        
        # 显示所有任务
        print("\n" + "=" * 70)
        print("Step 2: 查看任务状态")
        print("=" * 70)
        for task in queue.list_tasks():
            print_task(task)
        
        # ===== 模拟执行 =====
        
        print("=" * 70)
        print("Step 3: 模拟 Deep Research 执行流程")
        print("=" * 70)
        
        # Wave 1: Task 1 (无依赖)
        print("\n--- Wave 1: 规划阶段 ---")
        available = queue.get_available_tasks()
        print(f"可用任务: {[t.name for t in available]}")
        
        if available:
            task = available[0]
            queue.claim_task(task.id, "research-lead")
            print(f"\n  [research-lead] 认领并执行: {task.name}")
            simulate_worker("research-lead", task, 1.0)
            queue.complete_task(task.id)
            
            # Worker 通知 Lead
            mb.send_message(
                from_agent="research-lead",
                to_agent="lead",
                content=f"研究路线规划完成: {task.name}",
                msg_type="task_completed"
            )
        
        # Wave 2: Task 2a, 2b, 2c (都依赖 Task 1)
        print("\n--- Wave 2: 并行搜索阶段 ---")
        available = queue.get_available_tasks()
        print(f"可用任务: {[t.name for t in available]}")
        
        # 三个任务可以并行
        workers = ["worker-search-1", "worker-search-2", "worker-search-3"]
        for i, task in enumerate(available):
            queue.claim_task(task.id, workers[i])
            print(f"\n  [{workers[i]}] 认领并执行: {task.name}")
            simulate_worker(workers[i], task, 1.5)
            queue.complete_task(task.id)
            
            mb.send_message(
                from_agent=workers[i],
                to_agent="lead",
                content=f"搜索完成: {task.name}",
                msg_type="task_completed"
            )
        
        # Wave 3: Task 3 (依赖 2a, 2b, 2c)
        print("\n--- Wave 3: 信息提取与验证阶段 ---")
        available = queue.get_available_tasks()
        print(f"可用任务: {[t.name for t in available]}")
        
        if available:
            task = available[0]
            queue.claim_task(task.id, "research-analyst")
            print(f"\n  [research-analyst] 认领并执行: {task.name}")
            simulate_worker("research-analyst", task, 2.0)
            queue.complete_task(task.id)
        
        # Wave 4: Task 4 (依赖 Task 3)
        print("\n--- Wave 4: 报告撰写阶段 ---")
        available = queue.get_available_tasks()
        print(f"可用任务: {[t.name for t in available]}")
        
        if available:
            task = available[0]
            queue.claim_task(task.id, "report-writer")
            print(f"\n  [report-writer] 认领并执行: {task.name}")
            simulate_worker("report-writer", task, 1.5)
            queue.complete_task(task.id)
        
        # Wave 5: Task 5 (依赖 Task 4)
        print("\n--- Wave 5: 引用整理阶段 ---")
        available = queue.get_available_tasks()
        print(f"可用任务: {[t.name for t in available]}")
        
        if available:
            task = available[0]
            queue.claim_task(task.id, "editor")
            print(f"\n  [editor] 认领并执行: {task.name}")
            simulate_worker("editor", task, 1.0)
            queue.complete_task(task.id)
        
        # 最终状态
        print("\n" + "=" * 70)
        print("Step 4: 最终任务状态")
        print("=" * 70)
        for task in queue.list_tasks():
            status_icon = "OK" if task.status == "completed" else "!!" if task.status == "in_progress" else ".."
            print(f"  [{status_icon}] {task.name}: {task.status}")
        
        # 统计
        stats = queue.get_task_stats()
        print("\n" + "=" * 70)
        print("执行统计")
        print("=" * 70)
        print(f"  总任务数: {stats['total']}")
        print(f"  已完成: {stats['completed']}")
        print(f"  进行中: {stats['in_progress']}")
        print(f"  等待中: {stats['pending']}")
        
        # 显示 Mailbox 消息
        print("\n" + "=" * 70)
        print("Agent 间通信记录")
        print("=" * 70)
        messages = mb.read_messages("lead", mark_read=False)
        print(f"  Lead 收件箱: {len(messages)} 条消息")
        for msg in messages:
            print(f"    [{msg.from_agent}] -> {msg.to_agent}: {msg.content[:50]}...")
        
        print("\n" + "=" * 70)
        print("Deep Research DAG 测试完成!")
        print("=" * 70)
        
    finally:
        # 清理
        print(f"\n清理测试目录: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_wave_execution():
    """测试 Wave 执行顺序"""
    print("\n" + "=" * 70)
    print("Wave 执行顺序测试")
    print("=" * 70)
    
    temp_dir = tempfile.mkdtemp(prefix="wave_test_")
    
    try:
        queue = TaskQueue(team_id="wave_test", base_dir=temp_dir)
        
        # 创建复杂 DAG
        tasks = {}
        
        # Wave 1: 2 个独立任务
        tasks['a1'] = queue.create_task(name="Task A1 (无依赖)")
        tasks['a2'] = queue.create_task(name="Task A2 (无依赖)")
        
        # Wave 2: 3 个任务 (都依赖 a1)
        tasks['b1'] = queue.create_task(name="Task B1 (blockedBy: a1)", blocked_by=[tasks['a1'].id])
        tasks['b2'] = queue.create_task(name="Task B2 (blockedBy: a1)", blocked_by=[tasks['a1'].id])
        tasks['b3'] = queue.create_task(name="Task B3 (blockedBy: a1)", blocked_by=[tasks['a1'].id])
        
        # Wave 3: 1 个任务 (依赖 b1, b2)
        tasks['c1'] = queue.create_task(name="Task C1 (blockedBy: b1, b2)", blocked_by=[tasks['b1'].id, tasks['b2'].id])
        
        # Wave 4: 1 个任务 (依赖 c1)
        tasks['d1'] = queue.create_task(name="Task D1 (blockedBy: c1)", blocked_by=[tasks['c1'].id])
        
        print("\nDAG 结构:")
        print(r"""
    [A1] [A2]                    <- Wave 1: 可并行
       \ | /
        [B1] [B2] [B3]           <- Wave 2: 都依赖 A1
          \   |   /
           [C1]                   <- Wave 3: 依赖 B1, B2
             |
           [D1]                   <- Wave 4: 依赖 C1
        """)
        
        # 模拟顺序执行
        wave_num = 1
        while True:
            available = queue.get_available_tasks()
            if not available:
                break
            
            print(f"\n  Wave {wave_num}: {[t.name for t in available]}")
            
            for task in available:
                queue.claim_task(task.id, f"worker-{wave_num}")
                queue.complete_task(task.id)
            
            wave_num += 1
        
        print(f"\n  总共 {wave_num - 1} 个 Wave 完成")
        
        stats = queue.get_task_stats()
        print(f"  最终: {stats['completed']}/{stats['total']} 任务完成")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Agent Team Deep Research DAG 测试")
    print("=" * 70 + "\n")
    
    # 测试 Deep Research DAG
    test_deepresearch_dag()
    
    # 测试 Wave 执行顺序
    test_wave_execution()
    
    print("\n" + "=" * 70)
    print("所有测试完成!")
    print("=" * 70)
