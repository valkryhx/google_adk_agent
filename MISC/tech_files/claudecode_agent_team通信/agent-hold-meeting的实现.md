# Agent Hold Meeting (Swarm Meeting) 实现报告

## 1. 问题定义 (Problem Definition)

### 目标
实现 Swarm 内部的“会议”机制，让多个 Agent (Worker Nodes) 就一个特定议题进行多轮讨论，并在前端以结构化、直观的方式展示会议进程。

### 挑战
1.  **多 Agent 协同**: 如何在后端协调多个 Worker 轮流发言，并保证上下文连贯？
2.  **前端展示**: 如何跳出传统的“流水账”日志，将会议按“轮次”分组展示？
3.  **历史回显**: 刷新页面后，如何从有限的日志文本中还原出结构化的会议视图？
4.  **数据完整性**: 如何确保长文本、多行发言不丢失？

---

## 2. 实现思路与核心代码 (Implementation & Core Code)

### 2.1 后端架构 (`tools.py`)

后端采用了**双层循环结构**来控制会议流程，并特别注意了日志的生成顺序，以确保前端能正确解析。

#### 关键逻辑：Round Details 构建顺序
为了修复 "Round 顺序错乱" 的 Bug，我们在 `hold_meeting` 中严格规定了写入 `round_details` 的顺序：
1.  **Header**: 必须最先写入，作为本轮数据的锚点。
2.  **Participants**: 随后写入并发执行的 Worker 结果。
3.  **Secretary**: 最后写入本轮的总结（作为下一轮的 Context）。

```python
# tools.py (Simplified)

for round_idx in range(1, max_rounds + 1):
    # [Critical Fix] 1. 先插入 Header
    # 之前错误的重排序逻辑试图在事后插入这个，导致了顺序颠倒
    round_details.append(f"--- Round {round_idx} ({actual_count} participants) ---")

    # 2. 并发派发任务 (Dispatch)
    results = await dispatch_batch_tasks(...)

    # 3. 收集参与者发言
    for res in results:
        # ... 解析 content ...
        # 写入参与者条目
        round_details.append(f"[P{res['index']+1}-Port{worker_port}]: {content}")

    # 4. 秘书总结 (Secretary)
    if last_round_raw:
        # ... 调用秘书 Agent ...
        round_details.append(f"[Secretary-Port{sec_port}]: {summary_text}")
```

---

### 2.2 前端架构 (`script.js`)

前端面临的最大挑战是**历史回显**。在实时模式下，我们可以通过事件即时渲染。但在刷新页面后，我们只有一堆静态的 Message Logs。

#### 关键逻辑 1：Message Merging (消息合并)
Adk Agent 的底层机制会将 `tool_call`（工具调用）和 `tool_result`（工具结果）存为两条独立的消息。这导致 `hold_meeting` 的解析逻辑（位于 `tool_call` 渲染块中）无法直接读取到 `tool_result` 中的会议日志。

为此，我们在 `loadSessionHistory` 中实现了**预读合并**逻辑：

```javascript
// script.js - loadSessionHistory

for (let i = 0; i < data.messages.length; i++) {
    const msg = data.messages[i];
    
    // [Fix] 预读下一条消息
    if (i + 1 < data.messages.length) {
        const nextMsg = data.messages[i + 1];
        
        // 如果当前是 tool_call 且下一条是 tool_result
        const hasToolCall = msg.blocks.some(b => b.type === 'tool_call');
        const hasToolResult = nextMsg.blocks.some(b => b.type === 'tool_result');

        if (hasToolCall && hasToolResult) {
            console.log(`[History] Merging tool_call with tool_result`);
            // 将下一条的 blocks 合并到当前消息
            msg.blocks = msg.blocks.concat(nextMsg.blocks);
            // 跳过下一条消息的处理
            i++; 
        }
    }
    // ... 渲染 msg ...
}
```

#### 关键逻辑 2：Line-by-Line Parsing + Buffer (逐行解析与缓冲)
为了解决“最后一轮丢失”和“多行内容截断”的问题，我们摒弃了脆弱的正则表达式（Regex-only），改用了**状态机 + 缓冲区**的解析方式。

```javascript
// script.js - hold_meeting history rendering

const lines = resultContent.split('\\n');
let buffer = []; // [Fix] 多行内容缓冲区
let currentEntry = null;

for (const line of lines) {
    // 1. 尝试匹配 Round Header
    const roundMatch = line.match(/^--- Round (\d+)/);
    if (roundMatch) {
        if (currentEntry) flushEntry(currentEntry, buffer); // 结算上一条
        // ... 创建新 Round ...
        continue;
    }

    // 2. 尝试匹配 Participant/Secretary Entry
    // [Fix] 正则改为 ^\s*\[ 允许缩进
    const entryMatch = line.match(/^\s*\[(P\d+|Secretary)-Port(\d+|\?)\]:\s*(.*)/);
    if (entryMatch) {
        if (currentEntry) flushEntry(currentEntry, buffer); // 结算上一条
        
        // 开始新条目
        currentEntry = { 
            role: entryMatch[1], 
            port: entryMatch[2], 
            preview: entryMatch[3] // 第一行内容
        };
        buffer = []; // 清空缓冲
        continue;
    }

    // 3. [Critical Fix] 处理多行内容/孤儿行
    // 如果当前有活跃的 Entry，且该行不是新 Header/Entry，则认为是上一条内容的延续
    if (currentEntry) {
        buffer.push(line.trim());
    }
}
// 循环结束，结算最后一条
if (currentEntry) flushEntry(currentEntry, buffer);
```

---

## 3. 前端优化与 Bug 修复历程 (The Bug Fix Journey)

### Round 1: 交互失效 (The "Unexpandable" Card)
- **Problem**: 历史卡片无法点击展开。
- **Fix**: 在生成 HTML 时补全了 `<details>` 和 `<summary>` 标签。
  ```javascript
  html += `<details class="swarm-card ...">
             <summary class="swarm-card-header">...</summary>
             <div class="swarm-card-body">${fullContent}</div>
           </details>`;
  ```

### Round 2: 最后一轮丢失 (The "Missing Last Round")
- **Problem**: 最后一轮参与者（通常是长文本）消失。
- **Root Cause**: 旧逻辑只认带有 `[Px-Port]:` 前缀的行。如果参与者第一行是空的，或者内容被换行符截断，后续内容会被丢弃。
- **Fix**: 上述的 **Buffer Mechanism**。只要 `currentEntry` 不为空，遇到无法识别的行就无脑 `push` 到 buffer 中。

### Round 3: 缩进陷阱 (The "Indentation" Bug)
- **Problem**: 日志中带有缩进的行被忽略。
- **Root Cause**: 正则 `^\[` 过于严格。
- **Fix**: 改为 `^\s*\[`，允许行首出现任意数量的空白字符。

### Round 4: 顺序颠倒 (The "Secret Reorder" Bug)
- **Problem**: Round 3 显示“秘书在前”，Round 4 丢失。
- **Root Cause**: `tools.py` 曾包含一段用于“美化”输出的重排序代码，试图将 Header 提前。但逻辑写反了：
  ```python
  # [Buggy Code]
  if line.startswith("--- Round"):
      organized.extend(previous_parts) # 把攒下的（上一轮的）参与者放到了 Header 前面！
  ```
- **Fix**: 删除所有重排序逻辑，在生成时直接保证顺序（见 2.1 节）。

---

## 4. Dispatch 优化 (Dispatch Optimization)

用户提到的 **"居然莫名的好了"** 的部分，是因为我们重构了 `dispatch_batch_tasks` 的结果解析正则。

### 问题场景
当 Worker 返回包含代码块（Code Block）或转义字符的结果时：
```text
Port 8000 Result: Here is a function:\ndef test():\n    pass
```

### 优化前的正则
```javascript
/Port (\d+).*?Result: (.*)/g
```
`.` 不匹配换行符，且 `(.*)` 贪婪匹配在遇到复杂的嵌套换行时容易失效。

### 优化后的正则
在 `script.js` 的 `dispatch_batch_tasks` 处理块中：
```javascript
// [Optimization] 使用 [\s\S] 匹配所有字符包括换行
// 兼容 \\n 转义符
const regex = /Port (\d+)[\s\S]*?(?:Result|Error): ([\s\S]*?)(?=(?:Port \d+|$))/g;
```
这一改动使得 `dispatch_batch_tasks` 能够从一整块混合文本中，精准提取出每个 Port 对应的、即便是多行的复杂结果。

---

> By Antigravity Agent
