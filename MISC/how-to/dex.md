# DEX: Asynchronous Task Execution

Dex (Daemon Executor) is a specialized skill designed to handle **long-running tasks** asynchronously. It prevents the main agent loop from blocking while waiting for time-consuming operations like file scanning, model training, or large data processing.

## 1. The Problem
In a standard agent ReAct loop, if an agent executes a command that takes 5 minutes, the entire system hangs for 5 minutes. The user cannot interact, and the context window might time out.

## 2. The Dex Solution
Dex introduces a **"Fire and Forget"** mechanism. the Agent submits a task, Dex spawns a background process, and immediately returns a "Task Started" message. The agent is then free to continue conversing with the user or perform other tasks.

## 3. Implementation Details

*   **Skill**: `skills/dex`
*   **Storage**: Uses local filesystem (`.dex/tasks/`) to persist task state and logs.
*   **Process Management**:
    *   **Windows**: Uses `subprocess.Popen` with `creationflags=subprocess.CREATE_NEW_CONSOLE` (or detached flags) to ensure the process survives even if the main agent restarts.
    *   **Linux/Mac**: Uses `nohup` to detach processes.

## 4. Workflow

1.  **Create Task**:
    *   Tool: `dex_create_task(description, context)`
    *   Output: A unique `task_id`.
2.  **Start Task**:
    *   Tool: `dex_start_task(task_id, command)`
    *   Action: Spawns the background process.
    *   Output: "Task started".
3.  **Monitor**:
    *   Tool: `dex_list_tasks()` / `dex_get_task_details(task_id)`
    *   Action: Checks the `.dex` directory for status updates and log files.

## 5. Example Scenario
User: "Scan my entire D: drive for PDF files."

*   **Without Dex**: Agent runs `find /d -name *.pdf`, hangs for 10 minutes. User is frustrated.
*   **With Dex**:
    1.  Agent: "I will start a background task to scan for PDFs."
    2.  Agent calls `dex_create_task(...)` -> gets ID `1234`.
    3.  Agent calls `dex_start_task(1234, "find ... > results.txt")`.
    4.  Agent: "Scanning started! You can ask me other questions while we wait."
    5.  (Later) Agent checks `dex_list_tasks()` and notifies user when done.

## 6. Fundamentals
Dex is an excellent example of **Agentic Fundamentals**:
*   **Non-blocking I/O**: Essential for real-world usability.
*   **State Persistence**: Tasks survive agent restarts.
*   **Tool Abstraction**: Complex OS-level process management is abstracted into simple API calls for the LLM.
