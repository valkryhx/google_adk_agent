# How-to: 排查与修复 Swarm 任务结果丢失 Bug

## 1. 问题背景 (Problem Background)

在一个典型的 Swarm (集群) 模式下，用户向 Leader (8000) 发送了一个复杂的多模态任务（如：搜索图片中的电影信息），并要求通过 Agent Team 技能并行处理。

**观察到的异常现象：**
1.  **Worker 端正常**：从后台日志看，Worker 节点（如 8004）成功执行了 `web-search` 工具，并获得了完整的电影搜索结果。
2.  **Leader 端汇总为空**：Leader 前端显示的报告中，"执行结果摘要"部分只有 `...`，没有任何实质内容。
3.  **LLM 误判**：Leader Agent 看到摘要为空，认为 Worker 没返回结果，于是说："我还没有看到完整的搜索结果返回，让我直接调用 web-search 来搜索..." 导致了重复执行和资源浪费。

## 2. 排查过程 (Debugging Journey)

### 第一步：确认数据流向
整个数据传输链路如下：
`Worker Agent (执行任务)` -> `run_task() (流式事件生成)` -> `_process_event_stream` -> `FastAPI StreamingResponse` -> `Leader dispatch_task() (收集响应流)` -> `final_report`

### 第二步：定位瓶颈
通过分析 `skills/agent_team/tools.py` 里的 `dispatch_task` 函数，我们发现了结果收集逻辑的致命限制：

```python
# 原始逻辑：只过滤 type == "text" 的 chunk
async for line in response.aiter_lines():
    data = json.loads(line)
    chunk = data.get("chunk", {})
    if chunk.get("type") == "text":  # <--- 问题根源
        content = chunk.get("content", "")
        final_report += content
```

### 第三步：分析 Worker 行为
在执行工具任务（如搜索）时，Worker Agent 的主要产出其实是 `tool_result` 类型的 chunk，而不是纯文本 `text`。
*   如果 Agent 在工具执行完后，没有再生成一段额外的总结文本，`final_report` 就会保持为空。
*   即使 Agent 生成了总结，如果内容包含在 `is_final_response` 事件中，也会因为 `_process_event_stream` 的 `is_final` 保护逻辑而被跳过（不产生 chunk）。

## 3. 根因结论 (Root Cause)

**Bug 根因**：`dispatch_task` 的结果收集逻辑过于狭窄，它只捕获了 Worker 返回的纯文本 chunk，却忽略了最重要的**工具执行结果 (tool_result)** 和**过程记录 (tool_call)**，导致汇总报告缺失核心信息。

## 4. 修复方案 (Resolution)

### 改进 1：全方位收集结果
修改收集器，使其能够处理多种类型的 chunk：

```python
# 改进后的收集逻辑
if chunk_type == "text":
    final_report += content
elif chunk_type == "tool_result":
    # 核心：将工具返回的具体结果加入报告
    final_report += f"\n[Tool Result]\n{content}\n"
elif chunk_type == "tool_call":
    # 记录调用了哪个工具
    tool_name = chunk.get("tool_name", "unknown")
    final_report += f"\n[Called: {tool_name}]\n"
```

### 改进 2：输出格式去误导化
原逻辑在结果末尾总是硬编码一个 `...`，这会产生两个负面影响：
1.  **摘要为空时**：只显示 `...`，看起来像是什么都没拿到。
2.  **摘要完整时**：LLM 看到 `...` 结尾会误以为结果被截断了，从而诱发其重复提问或尝试“补全”。

**修复**：改为动态判断，仅在确实超过 20,000 字符发生截断时才添加 `...(truncated)`。

## 5. 总结 (Post-Mortem)

在构建 Agent Swarm 时，节点间的通信协议比单体 Agent 更为复杂。Leader 节点不仅是任务的派发者，更是结果的**过滤器**。
*   **教训**：不要假设 Worker 只会通过文本回复。工具执行结果 (`tool_result`) 是协作链路中最重要的数据资产。
*   **最佳实践**：在进行流式响应收集时，应尽力捕获所有的语义化阶段，并在汇总时保留足够的证据链，以防止 Leader 节点产生幻觉。
