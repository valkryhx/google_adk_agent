# DEX: 异步任务执行 (Asynchronous Task Execution)

Dex (Daemon Executor) 是一个专门的技能，用于异步处理**长时间运行的任务**。它可以防止主 Agent 循环在等待耗时操作（如文件扫描、模型训练或大数据处理）时被阻塞。

## 1. 为了解决什么问题？

在标准的 Agent ReAct 循环中，如果 Agent 执行一个需要 5 分钟的命令，整个系统就会挂起 5 分钟。用户无法交互，上下文窗口可能会超时。

## 2. Dex 的解决方案

Dex 引入了 **"即发即弃 (Fire and Forget)"** 机制。Agent 提交任务，Dex 启动后台进程，并立即返回 "Task Started"。Agent 然后可以自由地继续与用户交谈或执行其他任务。

## 3. 实现细节

*   **Skill**: `skills/dex`
*   **存储**: 使用本地文件系统 (`.dex/tasks/`) 持久化任务状态和日志。
*   **进程管理**:
    *   **Windows**: 使用 `subprocess.Popen` 和 `creationflags=subprocess.CREATE_NEW_CONSOLE` (或 detached flags) 确保进程在主 Agent 重启后仍然存活。
    *   **Linux/Mac**: 使用 `nohup` 分离进程。

## 4. 工作流 (Workflow)

1.  **创建任务**:
    *   工具: `dex_create_task(description, context)`
    *   输出: 一个唯一的 `task_id`。
2.  **启动任务**:
    *   工具: `dex_start_task(task_id, command)`
    *   动作: 启动后台进程。
    *   输出: "Task started"。
3.  **监控**:
    *   工具: `dex_list_tasks()` / `dex_get_task_details(task_id)`
    *   动作: 检查 `.dex` 目录以获取状态更新和日志文件。

## 5. 示例场景

用户: "扫描整个 D 盘的 PDF 文件。"

*   **没有 Dex**: Agent 运行 `find /d -name *.pdf`，挂起 10 分钟。用户感到沮丧。
*   **使用 Dex**:
    1.  Agent: "我将启动一个后台任务来扫描 PDF。"
    2.  Agent 调用 `dex_create_task(...)` -> 获得 ID `1234`。
    3.  Agent 调用 `dex_start_task(1234, "find ... > results.txt")`。
    4.  Agent: "扫描已启动！在等待的同时，你可以问我其他问题。"
    5.  (稍后) Agent 检查 `dex_list_tasks()` 并在完成后通知用户。

## 6. 基本原理 (Fundamentals)

Dex 是 **Agentic Fundamentals** 的绝佳示例：
*   **非阻塞 I/O**: 真实世界可用性的关键。
*   **状态持久化**: 任务在 Agent 重启后因存在。
*   **工具抽象**: 复杂的操作系统级进程管理被抽象为简单的 API 调用，供 LLM 使用。
