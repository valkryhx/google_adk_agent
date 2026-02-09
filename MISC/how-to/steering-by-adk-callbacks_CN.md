# Steering by ADK Callbacks (基于 ADK 回调的转向控制)

本文档解释了 Ciri 中的 "Steering" (转向/驾驶) 机制，这种机制允许对 Agent 的执行流进行实时控制和打断，类似于 `claudecode`。

## 1. 核心机制

Steering 能力建立在 **Google ADK 的回调系统 (Callback System)** 之上（面向切面编程 AOP）。它允许我们在 Agent 生命周期的关键点注入控制逻辑，而不会混淆主要业务逻辑。

### 关键组件

1.  **Callbacks (回调)**:
    *   `before_model_callback`: 在 Agent 调用 LLM 之前触发。
    *   `before_tool_callback`: 在 Agent 执行工具之前触发。
    
2.  **SteeringSession**:
    *   管理每个用户会话的状态。
    *   维护一个专门用于中断信号的 `asyncio.Queue`。

3.  **Interruption Guard (中断卫士)**:
    *   绑定到会话实例的方法 `interruption_guard(self, ...)`。
    *   它检查中断队列。如果存在 "CANCEL" 信号，立即引发 `UserInterruption` 异常。

## 2. 实现细节

**源码**: `src/adk_agent/main_web_start_steering.py`

```python
class SteeringSession:
    def __init__(self, ...):
        # ...
        self.queue = asyncio.Queue() # 中断通道
    
    def interruption_guard(self, *args, **kwargs):
        """中断卫士 (AOP切面)"""
        if not self.queue.empty():
            try:
                signal = self.queue.get_nowait()
                if signal == "CANCEL":
                    print(f"🛑 [Steering] 检测到中断! Target: {self.key}")
                    # 清空队列
                    while not self.queue.empty(): self.queue.get_nowait()
                    raise UserInterruption("用户请求停止操作。")
            except asyncio.QueueEmpty:
                pass

    def _create_agent(self) -> LlmAgent:
        # ...
        agent = LlmAgent(
            # ...
            # 将卫士绑定到关键生命周期钩子
            before_model_callback=self.interruption_guard,
            before_tool_callback=self.interruption_guard
        )
        return agent
```

## 3. 为什么这很重要？

### 实时控制 (Real-time Control)
在传统的 Agent 循环中，一旦发送请求，你必须等待它完成。有了 Steering，如果 Agent 开始走错路（例如，"我现在读取所有 100 万个文件..."），用户可以点击"停止"，Agent 会在执行昂贵的工具调用或下一个网络请求**之前**有效地停止。

### Agent Team 安全 (Agent Team Safety)
此机制也适用于 **Agent Team (Swarm)**。如果子 Agent 任务耗时过长或偏离目标，Leader 或用户可以触发中断，实施"快速失败 (Fail Fast)" 理念。这节省了 Token、时间，并防止错误级联。
