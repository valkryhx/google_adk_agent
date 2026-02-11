# Playwright-CLI 中断 Bug 修复与 get_tools(*args, **kwargs) 设计模式分析

## 1. 问题现象 (Phenomenon)

在 ADK 中使用 `playwright-cli` 执行浏览器操作时（例如 `playwright-cli open google.com`），如果用户尝试：
1.  向 Agent 发送新指令（如“停止”或“换个网站”）。
2.  点击前端的“中断/停止”按钮。

**观察到的异常**：
- 后台 `/chat` 或 `/api/chat` 端点返回 **503 Service Unavailable** 错误。
- 任务没有立即停止，Agent 依然处于 Busy（锁定）状态，直到原本的命令（如长时间加载）自然结束或超时。
- 前端界面的中断按钮消失或无法生效，用户感到 Agent “卡死”了。

## 2. 问题分析过程 (Root Cause Analysis)

### 初步排查
- 503 错误通常表示 Agent 正忙（Work Locked）。在 `main_web_start_steering.py` 中，当 `WORKER_LOCK` 被占用时，新请求直接返回 503。
- 只有带 `[URGENT_INTERRUPT]` 标记的请求或者专门的 `/api/cancel` 请求可以尝试打断。
- 但是，即使用了 `/api/cancel`，如果正在运行的工具（Tool）是 **同步阻塞** 的且没有检查中断信号，那么 `await session.queue.put("CANCEL")` 仅仅是把信号放进了队列，消费者（Tool）不取走处理，任务就停不下来。

### 深入代码
1.  **调用链**：`playwright-cli` 的实现实际上是调用了 `bash` 工具来执行命令行。
2.  **Bash 工具** (`skills/bash/tools.py`)：查看 `bash` 函数源码，它使用 `asyncio.create_subprocess_shell` 执行命令。
3.  **关键缺失**：
    - 旧的 `bash` 函数虽然是异步的，但它在等待子进程结束的循环中，**没有检查 `interruption_queue`**（或者根本没接收这个参数）。
    - 旧的 `get_tools` 仅仅返回函数列表，**没有注入当前 Session 的上下文对象**（如 `queue`）。

这意味着：当 Playwright 命令在跑的时候，Python 协程在 `await process.wait()`，完全忽略了外界的 Cancel 信号。

## 3. 代码修改方案 (Solution)

### 修改 1：`skills/bash/tools.py`
我们需要让 `bash` 工具能够“感知”中断。

1.  **函数签名变更**：给 `bash` 函数增加 `interruption_queue` 参数。
2.  **中断检测逻辑**：在 `while` 循环中，使用 `interruption_queue.get_nowait()` 轮询信号。如果收到 "CANCEL"，立即 `process.terminate()`。
3.  **动态绑定 (Dependency Injection)**：
    修改 `get_tools`，使其接收 `**kwargs`。如果 `kwargs` 中包含 `interruption_queue`，则使用 `functools.partial` 将其绑定到 `bash` 函数上。

```python
# skills/bash/tools.py

def bash(..., interruption_queue=None):
    # ... setup process ...
    while True:
        # 🟢 新增：检查中断信号
        if interruption_queue and not interruption_queue.empty():
            if interruption_queue.get_nowait() == "CANCEL":
                process.terminate()
                return "[INTERRUPTED] By User"
        # ... wait for output ...

def get_tools(*args, **kwargs):
    tools = list(bash_TOOLS.values())
    
    # 🟢 新增：动态注入依赖
    if 'interruption_queue' in kwargs:
        queue = kwargs['interruption_queue']
        # 使用 partial 绑定参数，但保留函数名和文档 (对 LLM 至关重要)
        # ... logic to wrap bash with partial ...
    
    return tools
```

### 修改 2：`src/adk_agent/main_web_start_steering.py`
在加载 Skill 时，将当前 Session 的 Queue 传进去。

```python
# src/adk_agent/main_web_start_steering.py

def _load_skill_tools(self, skill_id):
    # ...
    # 🟢 新增：将 self.queue 注入
    tools = module.get_tools(
        *common_args,
        status_reporter=self.report_swarm_event,
        interruption_queue=self.queue  # <--- 注入点
    )
    # ...
```

## 4. 为什么这样修改 (Why & Benefits)

### 核心收益
解决了 **僵尸任务** 问题。现在，无论底层是在跑 `ping`、`playwright` 还是其他耗时命令，只要用户一点停止，信号就会传递到最底层的执行循环，强制杀掉子进程，瞬间释放 Agent 锁。

### 引申：`get_tools(*args, **kwargs)` 定义方式的好处

在 Skill 开发中，推荐始终使用 `def get_tools(agent, session_service, **kwargs):` 这种签名，而不是硬编码参数。

**好处 1：随时注入上下文 (Context Injection)**
Agent 框架在不断演进，未来可能会有新的上下文对象（例如 `trace_id`、`user_preferences`、`cost_tracker` 等）。
使用 `**kwargs` 可以在不修改 Skill 代码的情况下，通过框架层（Loader）直接注入这些新对象。

**好处 2：动态能力绑定 (Capability Binding)**
如本次修复所示，我们可以将“中断能力” (`queue`) 或“实时上报能力” (`status_reporter`) 动态绑定到工具函数上。
- 工具本身只要写好逻辑（如果有 queue 就检查，没有就忽略），保持了松耦合。
- 只有在通过 Agent 加载时，才会赋予它中断和上报的能力。

**好处 3：测试便利性**
在单元测试中，我们可以不传这些复杂的对象，或者传 Mock 对象，工具依然能正常运行（因为参数是可选的或通过 kwargs 获取）。

**最佳实践建议**：
所有 Skill 的 `get_tools` 入口都应设计为：
```python
def get_tools(agent, session_service, config=None, **kwargs):
    # 1. 获取通用依赖
    reporter = kwargs.get('status_reporter')
    queue = kwargs.get('interruption_queue')
    
    # 2. 对需要这些依赖的工具进行 Partial Binding
    # ... binding logic ...
    
    return [tool1, tool2, ...]
```
这使得 Skill 具备了极强的适应性和可扩展性，能够随着宿主 Agent 的升级而获得新能力，而无需重写工具逻辑。
