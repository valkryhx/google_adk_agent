
# 修复 Google ADK Agent 对话中 Thought 重复显示的故障排查

## 1. 故障现象
用户在与 Agent 对话时发现，当 Agent 进行思考（Thought）并随后输出文本（Text）时，前端界面上会显示重复的内容。具体表现为：
-   **Thought 内容**和**Text 内容**均出现了**重复显示**（累积式重复）。
-   例如：先显示 "Thinking..."，然后显示 "Thinking... Result"。
-   普通对话（无 Thought）或纯 Tool Call 场景下有时未观察到此问题（原因见下文）。

## 2. 排查思路

### 2.1 初步分析
-   查看后端日志：日志中 Event 流看似正常，没有明显的重复记录。
-   查看前端代码：前端接收到的 SSE (Server-Sent Events) 数据流中确实包含了重复的文本片段。

### 2.2 深入后端逻辑
定位到 `src/adk_agent/main_web_start_steering.py` 中的 `run_task` 和 `_process_event_stream` 函数。

**发现核心机制：**
Google ADK 的 `runner.run_async` 生成的 Event 对象是**累积式**的（Accumulated History）。
这意味着：
-   T1 时刻：Event A 包含 Part [P1]
-   T2 时刻：Event B 包含 Part [P1, P2]
-   T3 时刻：Event C 包含 Part [P1, P2, P3]

后端 `run_task` 会持续 yield 这些 Event。如果直接处理 Event，就会导致处理 P1 三次，P2 两次，P3 一次。

**为什么只有 Thought 场景复现最明显？**
在 `_process_event_stream` 中原本有一段过滤逻辑：
```python
if has_tool and is_text_part and not is_tool_related and not has_thought:
    continue
```
-   **普通对话/工具调用**：如果不涉及 Thought，该过滤逻辑可能会跳过某些被视为“冗余”的纯文本 Part，从而**意外地掩盖了**部分累积重复的问题。
-   **Thought 场景**：Event 中包含 `thought=True` 的 Part，导致 `not has_thought` 为 False，**“免死金牌”生效**。于是，累积的旧 Parts（包括之前的 Text 和 Thought）被完整放行，导致前端收到显式的重复数据。

## 3. 解决方案

### 3.1 核心修复：在 `run_task` 层去重
我们不能依赖 `_process_event_stream` 的过滤逻辑（因为太复杂且容易漏），必须在数据源头解决“累积包”的问题。

**算法逻辑：**
1.  在 `run_task` 循环外维护一个 `processed_part_history` 列表。
2.  每次收到新 Event，获取其 `parts`。
3.  对比 `parts` 和 `processed_part_history`，计算**重合前缀**。
    -   如果 `parts[0] == processed_part_history[0]`，说明是同一个累积流。
    -   计算重合长度 `match_count`。
4.  只截取新增部分：`new_parts = parts[match_count:]`。
5.  将 `new_parts` 追加到历史记录，并仅将这些新 Parts 传递给 `_process_event_stream` 进行处理。

### 3.2 代码变更
-   **`run_task`**: 引入 `processed_part_history` 和去重切片逻辑。
-   **`_process_event_stream`**: 增加 `parts_override` 参数，允许外部传入已去重的 Parts 列表，不再强制使用 `event.content.parts`。

### 3.3 为什么 Thought 也不重复了？
因为 Thought 本身也是 Event 中的一个 `Part`（带有 `thought=True` 属性）。

在没有修复前，T1 时刻 Event A 包含 `[Part(Thought1)]`，T2 时刻 Event B 包含 `[Part(Thought1), Part(Text1)]`。`_process_event_stream` 会先后收到这两个 Event，导致 `Part(Thought1)` 被处理两次。

修复后，**在 `run_task` 层就已经完成了去重**：
-   T1 时刻：收到 Event A，`processed_part_history` 为空。此包也是全新的。传递 `[Part(Thought1)]` 给 `_process_event_stream`。记录到历史。
-   T2 时刻：收到 Event B `[Part(Thought1), Part(Text1)]`。
    -   去重逻辑发现前缀 `Part(Thought1)` 已经在历史中。
    -   计算出新增部分仅为 `[Part(Text1)]`。
    -   仅传递 `[Part(Text1)]` 给 `_process_event_stream`。
-   因此，`_process_event_stream` 永远只会收到**增量**的 Parts，无论它是 Thought 还是 Text。

## 4. Google ADK SDK 深入调研结论
在修复过程中，我们进一步调研了 `google.adk` SDK 是否原生支持增量（Delta）输出模式，以确认是否有配置项可以避免手动去重。

通过编写脚本（见附录）检查源码定义，发现：

1.  **`Runner.run_async`**: 其参数列表 `(user_id, session_id, new_message, run_config, ...)` 中没有发现任何配置增量输出的参数。
2.  **`RunConfig`**: 其中的 `streaming_mode` 参数只支持 `NONE`, `SSE`, `BIDI` 三种模式。目前使用的是 `StreamingMode.SSE`。
3.  **`StreamingMode`**: 这种模式下默认的行为就是返回累积的 Event 对象。

**结论**：
官方 SDK (及当前使用的版本) **并不提供直接的“纯增量 (Delta Only)”配置选项**。因此，我们在 `run_task` 中手动实现的去重逻辑（Deduplication Logic）是必要的且正确的架构决策，它充当了一个中间件，将 SDK 的累积式输出转换为了前端需要的增量流。

### 附录：检查脚本列表
已归档至当前目录：
- `inspect_llmagent.py`: 检查 LlmAgent 类签名
- `inspect_runconfig.py`: 检查 RunConfig 类签名
- `inspect_runner.py`: 检查 Runner.run_async 方法签名
- `inspect_streaming_mode.py`: 检查 StreamingMode 枚举值

## 5. 总结
对于流式响应（Streaming Response），必须明确上游数据源是**Delta（增量）**还是**Accumulated（全量）**。
-   如果是 Delta，直接转发。
-   如果是 Accumulated，必须在网关层或处理层维护状态进行去重（Dedup），将其转换为 Delta 再发给前端，否则不仅浪费带宽，还会导致客户端渲染重复。

## 6. 当前逻辑流程与案例分析
经过 `run_task` 的去重处理后，`_process_event_stream` 函数接收到的 `parts_override` 参数仅包含本次新增的增量部分（Delta）。以下是不同场景下的逻辑流转演示：

**前提条件：**
`_process_event_stream` 内部包含预扫描逻辑，会检测当前处理的 Delta 包中是否含有工具调用（`has_tool`）或思考过程（`has_thought`）。

```python
# 过滤逻辑核心（简化版）
if has_tool and is_text_part and not is_tool_related and not has_thought:
    continue  # 跳过与工具无关而且与思考无关的纯文本
```

### 案例 1: 纯文本流 (Pure Text)
**场景**：Agent 正在分块输出回答，例如 "Hello, world!"
**Delta Input**: `[Part(text="Hello")]` (假设)

1.  **预扫描**:
    -   `has_tool` = False
    -   `has_thought` = False
2.  **处理循环**:
    -   当前 Part 是文本。
    -   过滤条件检查：`has_tool` (False) -> 条件不成立。
    -   **结果**：正常输出文本 "Hello"。

### 案例 2: 思考 + 文本 (Thought + Text)
**场景**：Agent 先思考，然后输出文本。
**Delta Input**: `[Part(text="Thinking process...", thought=True), Part(text="Result")]`

1.  **预扫描**:
    -   `has_tool` = False
    -   `has_thought` = True (检测到 `thought=True` 的 Part)
2.  **处理循环**:
    -   **Part 1 (Thought)**:
        -   识别为 `thought` 类型。
        -   输出 `{type: "thought", content: "..."}`。
    -   **Part 2 (Text)**:
        -   过滤条件检查：`has_tool` (False) -> 条件不成立。
        -   **结果**：正常输出文本 "Result"。

### 案例 3: 思考 + 文本 + 工具调用 (Thought + Text + Function Call)
**场景**：Agent 思考后决定调用工具，并可能附带一些解释性文本。
**Delta Input**: `[Part(text="Thinking...", thought=True), Part(text="I will run check."), Part(function_call=...)]`

1.  **预扫描**:
    -   `has_tool` = True (检测到 Function Call)
    -   `has_thought` = True (检测到 Thought)
2.  **处理循环**:
    -   **Part 1 (Thought)**:
        -   输出 `{type: "thought", ...}`。
    -   **Part 2 (Text)**:
        -   过滤条件检查：
            -   `has_tool` = True
            -   `is_text_part` = True
            -   `not is_tool_related` = True
            -   `not has_thought` = **False** (因为 `has_thought` 为 True，取反为 False)
        -   **关键点**：由于检测到了 Thought，过滤条件整体为 False，“免死金牌”生效。
        -   **结果**：正常输出文本 "I will run check."。
    -   **Part 3 (Function Call)**:
        -   输出 `{type: "tool_call", ...}`。

### 案例 4: 文本 + 工具调用 (无 Thought)
**场景**：Agent 仅仅输出一句话然后调用工具，且没有被标记为 Thought。
**Delta Input**: `[Part(text="Running tool..."), Part(function_call=...)]`

1.  **预扫描**:
    -   `has_tool` = True
    -   `has_thought` = False
2.  **处理循环**:
    -   **Part 1 (Text)**:
        -   过滤条件检查：
            -   `has_tool` = True
            -   `is_text_part` = True
            -   `not is_tool_related` = True
            -   `not has_thought` = **True**
        -   **结果**：条件成立，`continue` 执行。**该文本被跳过，不会发送给前端**。
        -   *注：这是为了防止 Agent 在调用工具时输出冗余的自言自语，除非它是明确的 Thought。*
    -   **Part 2 (Function Call)**:
        -   输出 `{type: "tool_call", ...}`。
        
## 7. 附录：去重器 `processed_part_history` 深度逻辑解析

为了彻底解决累积流重复输出的问题，我们在 `run_task` 层实现了**Part 级增量去重器**。

### 7.1 数据结构
`processed_part_history` 是一个列表 (list)，用于存储**当前对话轮次（Turn）内已经处理过的所有 Event Part**。每次新的 Event 到来时，它都充当“已阅列表”。

### 7.2 核心算法流程
处理每个 Event 主要包括三个步骤：**前缀匹配**、**提取增量**、**更新历史**。

#### 步骤 1: 初始化与获取
在每一轮对话开始时，初始化为空列表：
```python
processed_part_history = []
```
对于每个收到的 Event (例如 `T2` 时刻)，获取其包含的 Parts 列表 `evt_parts`。

#### 步骤 2: 前缀匹配 (Check for prefix match)
假设当前历史为 `[P1]`，新 Event Parts 为 `[P1, P2]`。
算法会计算 `evt_parts` 与 `processed_part_history` 的**公共前缀长度** (`match_count`)。

```python
match_count = 0
min_len = min(len(evt_parts), len(processed_part_history))

# 此处包含优化：如果首元素都不匹配，直接视为全量新增 (match_count=0)
if evt_parts and processed_part_history and evt_parts[0] == processed_part_history[0]:
    for i in range(min_len):
        if evt_parts[i] == processed_part_history[i]:
            match_count += 1
        else:
            break
```

- 如果 `T1` 收到 `Event(parts=[P1])`：历史为空，匹配数为 0。
- 如果 `T2` 收到 `Event(parts=[P1, P2])`：`evt_parts[0]` (`P1`) 与历史 `[P1]` 匹配，`match_count` 为 1。

#### 步骤 3: 提取增量 (Slice New Parts)
根据匹配长度，对 `evt_parts` 进行切片，只保留新增的部分：
```python
new_parts = evt_parts[match_count:]
```

- 对于 `T1`：`new_parts = [P1][0:]` -> `[P1]`。
- 对于 `T2`：`new_parts = [P1, P2][1:]` -> `[P2]`。

#### 步骤 4: 更新历史与分发 (Update & Dispatch)
将**新增的部分**追加到历史中，确保存储了完整的累积状态，以备下一轮对比使用。
```python
if new_parts:
    processed_part_history.extend(new_parts)
    # 将且仅将增量部分传递给后续逻辑
    chunks = _process_event_stream(result, parts_override=new_parts)
```
- `T1` 更新后历史：`[P1]`
- `T2` 更新后历史：`[P1, P2]`

### 7.3 为什么能彻底解决重复？
Google SDK 的累积流是典型的 Append-Only Log 模式。我们的去重器本质上是在应用层实现了一个 **Delta Decoder**。因为 `_process_event_stream` 函数是**无状态**的（它只负责转换当前给它的数据），所以只要保证**喂给它的数据永远是 Delta（增量）**，就能从根本上杜绝重复输出。
