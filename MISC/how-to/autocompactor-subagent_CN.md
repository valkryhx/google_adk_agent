# AutoCompactAgent 指南

`AutoCompactAgent` 是一个专门设计的子 Agent (Sub-Agent)，用于管理 Ciri 的上下文窗口。它充当后台的"清洁工"，确保主 Agent 的记忆保持在可管理的范围内，同时不丢失关键信息。

## 1. 实现概览

*   **源码**: `src/adk_agent/auto_compact_agent.py`
*   **继承**: 继承自 `LlmAgent`，使其成为一个功能完整的 Agent，但用途特定。
*   **独立性**: 它在自己独立的临时会话 (`temp_compact_task`) 中运行，以避免污染主 Agent 的上下文或状态。

## 2. 核心逻辑

### System Prompt (系统提示词)
该 Agent 初始化时带有一个特定的系统提示词，指示它充当"对话摘要专家"。
摘要生成的关键规则：
1.  **保留核心目标**: 跟踪用户的意图。
2.  **记录关键步骤**: 记录已完成的重要操作和决策。
3.  **忽略冗余细节**: 移除长代码块和重复的工具输出。
4.  **保持上下文连贯**: 确保摘要足够连贯，以便另一个 Agent（或清除记忆后的主 Agent）能够接手。

### 安全执行 (Safe Execution)
*   **输入截断**: 在处理之前，它会检查 `MAX_SAFE_CHARS`。如果历史记录太长（这正是它要解决的问题！），它会智能地截断中间部分，保留开头（上下文设置）和结尾（最近的操作），防止压缩器本身因上下文溢出而崩溃。

### `compact_history` 方法
1.  接收原始历史文本。
2.  执行安全检查（截断）。
3.  创建一个临时的 `InMemorySessionService`。
4.  为自己启动一个临时的 `Runner`。
5.  将历史记录发送给自己，并请求生成摘要。
6.  返回生成的摘要。

## 3. 集成

这个子 Agent 通常在以下情况由 `compactor` 技能（或主循环）调用：
*   **Token 计数过高**: 当前会话的 Token 使用量超过阈值。
*   **对话轮数过高**: 对话进行了太多轮次。

触发时，主 Agent 暂停，`AutoCompactAgent` 运行，主 Agent 的历史记录被替换为 `[System Summary] <new_summary>` + 最近的几条消息。
