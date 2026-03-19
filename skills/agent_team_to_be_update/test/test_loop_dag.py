#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
================================================================================
Agent Team Loop DAG 测试脚本 - 复杂迭代任务场景
================================================================================

【使用方式】

## 1. 独立运行测试

```bash
cd D:\git_codes\google_adk_helloworld_git\skills\agent_team_to_be_update\test
python test_loop_dag.py
```

## 2. 测试场景

### 场景 1: ML 训练循环
```
准备数据 --> [训练 --> 评估 --> 准确率达标?] --> 输出模型
                  ^         |
                  |_________| (如果未达标)
```

### 场景 2: Deep Research 搜索循环
```
规划 --> [搜索 --> 读取 --> 评估信息充分?] --> 撰写报告
          ^          |
          |__________| (如果不足)
```

### 场景 3: 复杂混合图
```
                    [Task A]
                        |
        +---------------+---------------+
        |               |               |
        v               v               v
   [Loop 1]       [Loop 2]       [Task B]
   train-A        train-B
        |               |               |
        +-------> [Compare] <---------+
                     |
                     v
               [Loop 3: Tune]
                     |
                     v
               [Final Output]
```

================================================================================
【核心概念】

1. Loop Group: 一组需要迭代执行的任务
2. Gate Task: 判断是否继续迭代的任务
3. Exit Condition: 退出条件 (e.g., "accuracy >= 0.95")
4. Max Iterations: 最大迭代次数

================================================================================
"""

import sys
import os
import tempfile
import shutil
import time
import random

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task_queue import TaskQueue
from loop_executor import LoopExecutor, demo_task_executor


def print_dag_diagram(dag_type: str):
    """打印 DAG 图"""
    diagrams = {
        "ml_training": r"""
ML 训练循环 DAG:

    [准备数据]
         |
         v
    [Loop: 训练模型]
    +-------------------+
    | train_model       |
    | evaluate_model    |
    | check_accuracy [G]|
    +-------------------+
         |
    accuracy >= 0.95?
         |
         v
    [保存模型]
        """,
        "deepresearch": r"""
Deep Research 搜索循环 DAG:

    [规划研究主题]
         |
         v
    [Loop: 信息搜索]
    +--------------------+
    | search_web         |
    | read_content       |
    | check_sufficiency [G]|
    +--------------------+
         |
    信息充分?
         |
         v
    [撰写报告]
        """,
        "mixed": r"""
复杂混合 DAG:

                    [Task A: 准备数据]
                           |
        +------------------+------------------+
        |                  |                  |
        v                  v                  v
   [Loop: Model A]  [Loop: Model B]  [Task B: 验证]
        |                  |
        +---------> [Compare] <---------+
                     |
                     v
              [Loop: Tune Best]
                     |
                     v
              [Final Output]
        """
    }
    print(diagrams.get(dag_type, ""))


def test_ml_training_loop():
    """测试场景 1: ML 训练循环"""
    print("\n" + "=" * 70)
    print("场景 1: ML 训练循环")
    print("=" * 70)
    
    print_dag_diagram("ml_training")
    
    temp_dir = tempfile.mkdtemp(prefix="ml_loop_test_")
    
    try:
        queue = TaskQueue(team_id="ml_test", base_dir=temp_dir)
        executor = LoopExecutor(queue)
        executor.set_task_executor(demo_task_executor)
        
        # 创建准备数据任务
        prepare_task = queue.create_task(
            name="准备训练数据",
            description="下载并预处理数据集"
        )
        
        # 创建循环组
        loop = executor.create_loop_group(
            name="ML Training",
            max_iterations=10,
            exit_condition="accuracy >= 0.95"
        )
        
        # 创建循环内的任务
        train_task = queue.create_task(
            name="训练模型",
            description="执行一轮训练",
            blocked_by=[prepare_task.id]
        )
        
        eval_task = queue.create_task(
            name="评估模型",
            description="计算验证集准确率",
            blocked_by=[train_task.id]
        )
        
        gate_task = queue.create_task(
            name="检查准确率",
            description="判断是否达到目标",
            blocked_by=[eval_task.id]
        )
        
        # 添加到循环组
        executor.add_task_to_loop(loop.id, train_task.id)
        executor.add_task_to_loop(loop.id, eval_task.id)
        executor.add_task_to_loop(loop.id, gate_task.id, is_gate=True)
        
        # 创建后续任务
        save_task = queue.create_task(
            name="保存模型",
            description="保存训练好的模型",
            blocked_by=[gate_task.id]  # 依赖 gate 任务
        )
        
        print(f"\n创建了 {len(queue.list_tasks())} 个任务")
        print(f"循环组: {loop.name} (max_iterations={loop.max_iterations})")
        
        # 执行
        print("\n开始执行...")
        stats = executor.execute_mixed_dag()
        
        print("\n最终状态:")
        print(f"  任务完成: {stats['tasks']['completed']}/{stats['tasks']['total']}")
        print(f"  循环组完成: {stats['loops']['completed']}/{stats['loops']['total']}")
        print(f"  总迭代次数: {stats['executor']['total_iterations']}")
        
        # 检查 gate 任务的退出结果
        gate = queue.get_task(gate_task.id)
        if gate and gate.loop_exit_result:
            print(f"  最终准确率: {gate.loop_exit_result.get('accuracy', 'N/A'):.4f}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_deepresearch_loop():
    """测试场景 2: Deep Research 搜索循环"""
    print("\n" + "=" * 70)
    print("场景 2: Deep Research 搜索循环")
    print("=" * 70)
    
    print_dag_diagram("deepresearch")
    
    temp_dir = tempfile.mkdtemp(prefix="dr_loop_test_")
    
    try:
        queue = TaskQueue(team_id="deepresearch_test", base_dir=temp_dir)
        executor = LoopExecutor(queue)
        executor.set_task_executor(demo_task_executor)
        
        # 创建规划任务
        plan_task = queue.create_task(
            name="规划研究主题",
            description="确定研究目标和搜索策略"
        )
        
        # 创建搜索循环
        loop = executor.create_loop_group(
            name="Deep Research",
            max_iterations=5,
            exit_condition="sources_found >= 10"
        )
        
        search_task = queue.create_task(
            name="搜索网页",
            description="使用搜索引擎查找相关内容",
            blocked_by=[plan_task.id]
        )
        
        read_task = queue.create_task(
            name="读取内容",
            description="提取关键信息",
            blocked_by=[search_task.id]
        )
        
        gate_task = queue.create_task(
            name="检查信息充分性",
            description="判断是否收集了足够的信息",
            blocked_by=[read_task.id]
        )
        
        executor.add_task_to_loop(loop.id, search_task.id)
        executor.add_task_to_loop(loop.id, read_task.id)
        executor.add_task_to_loop(loop.id, gate_task.id, is_gate=True)
        
        report_task = queue.create_task(
            name="撰写研究报告",
            description="基于收集的信息撰写报告",
            blocked_by=[gate_task.id]
        )
        
        print(f"\n创建了 {len(queue.list_tasks())} 个任务")
        print(f"循环组: {loop.name} (exit_condition: {loop.exit_condition})")
        
        # 执行
        print("\n开始执行...")
        stats = executor.execute_mixed_dag()
        
        print("\n最终状态:")
        print(f"  任务完成: {stats['tasks']['completed']}/{stats['tasks']['total']}")
        print(f"  循环组完成: {stats['loops']['completed']}/{stats['loops']['total']}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_mixed_complex_dag():
    """测试场景 3: 复杂混合 DAG"""
    print("\n" + "=" * 70)
    print("场景 3: 复杂混合 DAG (多并行循环)")
    print("=" * 70)
    
    print_dag_diagram("mixed")
    
    temp_dir = tempfile.mkdtemp(prefix="mixed_loop_test_")
    
    try:
        queue = TaskQueue(team_id="mixed_test", base_dir=temp_dir)
        executor = LoopExecutor(queue)
        executor.set_task_executor(demo_task_executor)
        
        # Task A: 准备数据 (无依赖)
        task_a = queue.create_task(
            name="Task A: 准备数据",
            description="准备训练和验证数据"
        )
        
        # Loop 1: 训练 Model A (依赖 Task A)
        loop1 = executor.create_loop_group(
            name="Train Model A",
            max_iterations=8,
            exit_condition="accuracy >= 0.90"
        )
        
        task_a1_train = queue.create_task(
            name="Train A: 训练模型",
            blocked_by=[task_a.id]
        )
        task_a1_eval = queue.create_task(
            name="Train A: 评估模型",
            blocked_by=[task_a1_train.id]
        )
        task_a1_gate = queue.create_task(
            name="Train A: 检查准确率",
            blocked_by=[task_a1_eval.id]
        )
        
        executor.add_task_to_loop(loop1.id, task_a1_train.id)
        executor.add_task_to_loop(loop1.id, task_a1_eval.id)
        executor.add_task_to_loop(loop1.id, task_a1_gate.id, is_gate=True)
        
        # Loop 2: 训练 Model B (依赖 Task A，与 Loop 1 并行)
        loop2 = executor.create_loop_group(
            name="Train Model B",
            max_iterations=8,
            exit_condition="accuracy >= 0.90"
        )
        
        task_b1_train = queue.create_task(
            name="Train B: 训练模型",
            blocked_by=[task_a.id]
        )
        task_b1_eval = queue.create_task(
            name="Train B: 评估模型",
            blocked_by=[task_b1_train.id]
        )
        task_b1_gate = queue.create_task(
            name="Train B: 检查准确率",
            blocked_by=[task_b1_eval.id]
        )
        
        executor.add_task_to_loop(loop2.id, task_b1_train.id)
        executor.add_task_to_loop(loop2.id, task_b1_eval.id)
        executor.add_task_to_loop(loop2.id, task_b1_gate.id, is_gate=True)
        
        # Task B: 验证 (依赖 Task A)
        task_b = queue.create_task(
            name="Task B: 验证数据质量",
            blocked_by=[task_a.id]
        )
        
        # Compare: 比较两个模型 (依赖两个循环组和 Task B)
        compare_task = queue.create_task(
            name="Compare: 对比模型",
            blocked_by=[task_a1_gate.id, task_b1_gate.id, task_b.id]
        )
        
        # Loop 3: 调优最佳模型 (依赖 Compare)
        loop3 = executor.create_loop_group(
            name="Tune Best Model",
            max_iterations=5,
            exit_condition="improvement >= 0.01"
        )
        
        task_tune1 = queue.create_task(
            name="Tune: 调优模型",
            blocked_by=[compare_task.id]
        )
        task_tune2 = queue.create_task(
            name="Tune: 评估调优效果",
            blocked_by=[task_tune1.id]
        )
        task_tune_gate = queue.create_task(
            name="Tune: 检查改进",
            blocked_by=[task_tune2.id]
        )
        
        executor.add_task_to_loop(loop3.id, task_tune1.id)
        executor.add_task_to_loop(loop3.id, task_tune2.id)
        executor.add_task_to_loop(loop3.id, task_tune_gate.id, is_gate=True)
        
        # Final: 输出结果 (依赖 Loop 3)
        final_task = queue.create_task(
            name="Final: 输出最终模型",
            blocked_by=[task_tune_gate.id]
        )
        
        print(f"\n创建了 {len(queue.list_tasks())} 个任务")
        print(f"创建了 {len(queue.list_loop_groups())} 个循环组")
        
        print("\n循环组:")
        for lg in queue.list_loop_groups():
            print(f"  - {lg.name} (max_iter={lg.max_iterations}, condition={lg.exit_condition})")
        
        print("\nDAG 结构:")
        print("""
                    [Task A]
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
   [Loop 1]       [Loop 2]       [Task B]
   Model A         Model B         验证
        |                |                |
        +-------> [Compare] <------------+
                     |
                     v
              [Loop 3: Tune]
                     |
                     v
              [Final Output]
        """)
        
        # 执行
        print("\n开始执行...")
        start_time = time.time()
        stats = executor.execute_mixed_dag()
        elapsed = time.time() - start_time
        
        print("\n" + "=" * 70)
        print("执行完成!")
        print("=" * 70)
        print(f"  总耗时: {elapsed:.2f} 秒")
        print(f"  总波次: {stats['waves']}")
        print(f"  任务: {stats['tasks']['completed']}/{stats['tasks']['total']}")
        print(f"  循环组: {stats['loops']['completed']}/{stats['loops']['total']}")
        print(f"  总迭代次数: {stats['executor']['total_iterations']}")
        
        # 详细循环统计
        print("\n循环组详情:")
        for lg in queue.list_loop_groups():
            gate = queue.get_task(lg.gate_task_id) if lg.gate_task_id else None
            result = gate.loop_exit_result if gate else {}
            accuracy = result.get('accuracy', 'N/A') if result else 'N/A'
            if accuracy != 'N/A':
                accuracy = f"{accuracy:.4f}"
            print(f"  {lg.name}:")
            print(f"    - 迭代次数: {lg.current_iteration}/{lg.max_iterations}")
            print(f"    - 最终准确率: {accuracy}")
            print(f"    - 状态: {lg.status}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_parallel_loops():
    """测试场景 4: 两个完全并行的循环"""
    print("\n" + "=" * 70)
    print("场景 4: 两个完全并行的循环")
    print("=" * 70)
    
    temp_dir = tempfile.mkdtemp(prefix="parallel_loop_test_")
    
    try:
        queue = TaskQueue(team_id="parallel_test", base_dir=temp_dir)
        executor = LoopExecutor(queue)
        executor.set_task_executor(demo_task_executor)
        
        # Loop A
        loop_a = executor.create_loop_group(
            name="Loop A",
            max_iterations=5,
            exit_condition="count >= 3"
        )
        
        task_a1 = queue.create_task(name="A: 步骤1")
        task_a2 = queue.create_task(name="A: 步骤2", blocked_by=[task_a1.id])
        task_a_gate = queue.create_task(name="A: 检查", blocked_by=[task_a2.id])
        
        executor.add_task_to_loop(loop_a.id, task_a1.id)
        executor.add_task_to_loop(loop_a.id, task_a2.id)
        executor.add_task_to_loop(loop_a.id, task_a_gate.id, is_gate=True)
        
        # Loop B (并行，与 Loop A 无依赖)
        loop_b = executor.create_loop_group(
            name="Loop B",
            max_iterations=5,
            exit_condition="count >= 3"
        )
        
        task_b1 = queue.create_task(name="B: 步骤1")
        task_b2 = queue.create_task(name="B: 步骤2", blocked_by=[task_b1.id])
        task_b_gate = queue.create_task(name="B: 检查", blocked_by=[task_b2.id])
        
        executor.add_task_to_loop(loop_b.id, task_b1.id)
        executor.add_task_to_loop(loop_b.id, task_b2.id)
        executor.add_task_to_loop(loop_b.id, task_b_gate.id, is_gate=True)
        
        print("""
两个完全并行的循环 DAG:

    [Loop A]              [Loop B]
    +-----+                +-----+
    | A1  |                | B1  |
    | A2  |                | B2  |
    | Agate|                | Bgate|
    +-----+                +-----+
         |                      |
         +--------> [Done] <---+
        """)
        
        print(f"\n2 个并行循环组")
        
        # 执行
        print("\n开始执行 (两个循环应该并行迭代)...")
        stats = executor.execute_mixed_dag()
        
        print(f"\n结果: {stats['loops']['completed']}/{stats['loops']['total']} 循环完成")
        print(f"总迭代次数: {stats['executor']['total_iterations']}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Agent Team Loop DAG 测试")
    print("=" * 70)
    
    # 场景 1: ML 训练循环
    test_ml_training_loop()
    
    # 场景 2: Deep Research 搜索循环
    test_deepresearch_loop()
    
    # 场景 3: 复杂混合 DAG
    test_mixed_complex_dag()
    
    # 场景 4: 并行循环
    test_parallel_loops()
    
    print("\n" + "=" * 70)
    print("所有测试完成!")
    print("=" * 70)
