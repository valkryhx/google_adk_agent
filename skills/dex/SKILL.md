---
name: "Dex Async Task Manager"
description: "用于管理长耗时、异步任务的工具集。当任务预计执行时间超过 10 秒（如模型训练、大型构建、批量数据处理）时，必须使用此工具，而不是 bash。"
---

# Dex Skill 使用指南

Dex 是一个专门用于处理**长耗时异步任务**的任务管理系统。它将“思考”（Agent）与“执行”（后台进程）解耦。

## 核心原则：何时使用 Dex？

*   **⚡ 由于网络延迟或计算量大，预计耗时 > 10 秒的操作** -> **使用 Dex**
*   **📡 需要在 Agent 思考循环之外持续运行的服务** -> **使用 Dex**
*   **💻 简单的文件操作、系统信息查询、快速的 CLI 命令** -> **使用 bash**

## 核心定位

Dex 不再只是“长命令后台执行器”，而是 **Kairos 的异步任务引擎**。

当任务需要被后台持续观察、需要跨轮次检查结果、需要被 Kairos handoff/attach/汇报时，必须使用 Dex。

### 任务完成标准
- 任务必须有明确的结构化状态：`pending/running/completed/failed/canceled`
- 任务必须暴露结构化结果摘要与错误摘要
- 任务必须提供日志 artifact 路径
- 任务必须能被 Kairos 通过 bridge 稳定读取

## 工具详解

Dex 提供了一组原生 Python 工具，Agent 可以直接调用：

### 1. `dex_create_task`
创建一个新的任务记录。
*   `description`: 任务简述 (e.g. "Fine-tune model v2")
*   `context`: 详细参数或目标

### 2. `dex_start_task`
**关键步骤**。启动一个后台进程来执行具体命令。
*   `task_id`: `dex_create_task` 返回的 ID
*   `command`: 完整的命令行字符串 (e.g. "python scripts/train.py --epochs 100")
*   **注意**：命令会在后台**异步执行**，Agent 会立即获得 "Task started" 的响应，而不会被阻塞。

### 3. `dex_list_tasks` & `dex_get_task_details`
查询任务状态。
*   定期调用 `dex_list_tasks` 查看任务是否从 `running` 变为 `completed`。
*   任务完成后，调用 `dex_get_task_details` 查看 `result` 字段中的日志摘要。

## 典型工作流 (Workflow)

**场景：用户要求开始一个耗时的训练任务。**

1.  **创建任务**
    ```python
    task_info = dex_create_task(description="Training Llama3", context="Epochs: 50, Data: data.csv")
    # Returns: {"id": "a1b2c3d4", ...}
    ```

2.  **启动进程**
    ```python
    dex_start_task(task_id="a1b2c3d4", command="python train_model.py --data data.csv")
    # Returns: [OK] Task started in background...
    ```

3.  **Agent 继续其他工作... (或者每隔几轮对话检查一次)**

4.  **检查状态**
    ```python
    tasks = dex_list_tasks()
    # Returns: [{"id": "a1b2c3d4", "status": "completed", "result": "..."}]
    ```

5.  **查看结果**
    ```python
    details = dex_get_task_details("a1b2c3d4")
    # 分析 details['result'] 中的日志，回报给用户。
    ```

## 注意事项

*   所有输出都会被重定向到 `.dex/logs/{id}.log`。
*   如果是 Windows 环境，后台进程是一个独立的进程；Linux 下是 nohup 进程。
*   如果任务失败，`status` 会变成 `completed`，但在 `result` 中会包含 "FAILED" 字样和错误码。
