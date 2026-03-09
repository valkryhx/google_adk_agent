# Memory 保存实现过程

## 核心问题

ADK（Google Agent Development Kit）在流式输出模式下，`events_snapshot` 中包含大量重复事件。通过诊断 dump 发现，60 个 Event 中的真实结构如下：

| 类型           | `partial` 值           | 特征                                          | 占比 |
| -------------- | ---------------------- | --------------------------------------------- | ---- |
| 流式碎片       | `True`                 | 每个 Event 只含 1 个 Part，是独立的（非累加） | ~90% |
| 累加式完整事件 | `False`                | 包含本轮所有 Parts + 工具调用                 | 少量 |
| 工具返回事件   | `None`                 | `function_response`                           | 少量 |
| 最终响应       | `False` + `final=True` | 完整最终文本                                  | 1个  |

### 诊断数据示例

```
E[0]  partial=True  parts(1)=["text(T):'用户'"]              ← 流式碎片，跳过
E[1]  partial=True  parts(1)=["text(T):'想要知道...'"]        ← 流式碎片，跳过
...
E[14] partial=False parts(14)=[t0,t1,...,t11, text, fc:bash]  ← 累加完整事件，处理
E[15] partial=None  parts(1)=['fr:bash']                      ← 工具返回，处理
...
E[59] partial=False final=True parts(1)=[完整文本]             ← 最终响应，处理
```

### 诊断代码

**插入位置**：`src/adk_agent/main_web_start_steering.py` 的 `_archive_turn_to_memory` 方法内，`for evt in events_snapshot:` 循环之前（约第 1388 行）。

已从生产代码中移除，需要调试时可复制回去：

```python
# ===== [DEBUG] 临时诊断：dump events_snapshot 结构 =====
print(f"[Memory DEBUG] events_snapshot 包含 {len(events_snapshot)} 个 Event")
for idx, _evt in enumerate(events_snapshot):
    _role = getattr(_evt, 'author', '?')
    _partial = getattr(_evt, 'partial', None)
    _is_final = _evt.is_final_response() if hasattr(_evt, 'is_final_response') else '?'
    _parts = []
    if hasattr(_evt, 'content') and _evt.content and hasattr(_evt.content, 'parts'):
        _parts = _evt.content.parts
    _parts_info = []
    for _p in _parts:
        _info = ""
        if hasattr(_p, 'text') and _p.text:
            _thought = getattr(_p, 'thought', False)
            _info = f"text({'T' if _thought else 'N'}):{repr(_p.text[:30])}"
        elif hasattr(_p, 'function_call') and _p.function_call:
            _info = f"fc:{getattr(_p.function_call, 'name', '?')}"
        elif hasattr(_p, 'function_response') and _p.function_response:
            _info = f"fr:{getattr(_p.function_response, 'name', '?')}"
        else:
            _info = "other"
        _parts_info.append(_info)
    print(f"  E[{idx}] role={_role} partial={_partial} final={_is_final} parts({len(_parts)})={_parts_info}")
print(f"[Memory DEBUG] ===== END DUMP =====")
# ===== [/DEBUG] =====
```

输出每个 Event 的 `partial`、`is_final_response`、Parts 数量和类型（`T`=thought, `N`=normal text, `fc`=function_call, `fr`=function_response），以及每个 Part 文本的前 30 字符。

## 去重策略

**一行代码解决**：

```python
if getattr(evt, 'partial', False) is True:
    continue  # 跳过全部流式碎片
```

只处理 `partial != True` 的事件（约 10%），天然无重复。

## Thought 合并

### 问题

累加式完整事件（如 E[14]）内部仍包含多个独立的 thought Parts（每个流式 chunk 对应一个 Part）：

```
E[14].parts = [
  Part(text="用户", thought=True),        # thought chunk 0
  Part(text="想要知道...", thought=True),   # thought chunk 1
  ...
  Part(text="让我直接用...", thought=True), # thought chunk 11
  Part(text="我来帮你写...", thought=False), # 普通文本
  Part(function_call=fc:bash)              # 工具调用
]
```

如果不做合并，每个 thought Part 都会被单独渲染为一个 `<thought>` 块。

### 解决方案：`in_thought_stream` 状态机

用一个布尔标志跨 Part（也跨 Event）追踪 thought 流的状态：

```python
in_thought_stream = False

for part in evt_parts:
    if hasattr(part, 'text') and part.text:
        is_thought = getattr(part, 'thought', False)
        
        if is_thought:
            if not in_thought_stream:
                buffer.append("<thought>\n")    # 只写一次开始标签
                in_thought_stream = True
            buffer.append(part.text)            # 直接拼接文字
        else:
            if in_thought_stream:
                buffer.append("\n</thought>\n") # 遇到非 thought，关闭
                in_thought_stream = False
            buffer.append(f"{part.text.strip()}\n")
```

**效果**：多个 thought chunk 合并为一个连续的 `<thought>` 块。

## Tool Call / Tool Result 显示

### 工具调用（Function Call）

```python
if hasattr(part, 'function_call') and part.function_call:
    fc = part.function_call
    tool_name = getattr(fc, 'name', 'unknown')
    args_dict = dict(fc.args) if hasattr(fc, 'args') else {}
    buffer.append(f'<tool_call name="{tool_name}">\n')
    buffer.append(json.dumps(args_dict, indent=2, ensure_ascii=False) + "\n")
    buffer.append("</tool_call>\n")
```

### 工具返回（Function Response）

ADK 中 `function_response` 事件的 `content.role = 'user'`，会被 user 角色过滤误杀。需要特殊放行：

```python
if role == 'user':
    has_func_response = False
    for _p in evt.content.parts:
        if hasattr(_p, 'function_response') and _p.function_response:
            has_func_response = True
            break
    if not has_func_response:
        continue  # 只跳过真正的 user 输入，不跳过工具返回
```

渲染工具返回：

```python
if hasattr(part, 'function_response') and part.function_response:
    fr = part.function_response
    tool_name = getattr(fr, 'name', 'unknown')
    resp_val = getattr(fr, 'response', {})
    resp_dict = dict(resp_val) if hasattr(resp_val, 'items') else {"result": str(resp_val)}
    buffer.append(f'<tool_result name="{tool_name}">\n')
    buffer.append(json.dumps(resp_dict, indent=2, ensure_ascii=False) + "\n")
    buffer.append("</tool_result>\n")
```

## 最终输出格式（XML）

选择 XML 而非 Markdown `[]` 标记的原因：LLM 大量训练于 XML/HTML 数据，解析能力更强，语义边界更清晰。

```xml
<user time="19:01:00">
你随便背一首诗
</user>

<agent role="Ciri" time="19:01:01">
<thought>
用户要求我背诵一首诗。作为AI助手，我可以背诵经典古诗词。
让我选择李白的《静夜思》，这是最著名的唐诗之一。
</thought>
我来为你背诵一首李白的《静夜思》：
床前明月光，疑是地上霜。
举头望明月，低头思故乡。
</agent>
```

带工具调用的完整示例：

```xml
<user time="18:56:23">
现在几点了，写个python告诉我
</user>

<agent role="Ciri" time="18:56:24">
<thought>
用户想要知道现在的时间，并要求我写一个Python程序来获取当前时间并显示。
</thought>
我来帮你写一个Python程序获取当前时间：
<tool_call name="bash">
{
  "command": "python3 -c \"from datetime import datetime; print(datetime.now())\""
}
</tool_call>
<tool_result name="bash">
{
  "result": "2026-03-09 18:56:25.123456"
}
</tool_result>
当前时间是 2026-03-09 18:56:25。
</agent>
```

## 并发写入保护

使用 `filelock` 库保护文件写入，防止多 Agent 并发写入同一文件时数据错乱：

```python
lock_path = filepath + ".lock"
with FileLock(lock_path, timeout=5):
    with open(filepath, "a", encoding="utf-8") as f:
        f.write("".join(buffer))

# 写完后清理 .lock 文件（不影响保护功能，下次写入时自动重建）
try:
    os.remove(lock_path)
except OSError:
    pass
```

## 文件组织

```
memory_archive/
  {user_id}/
    {YYYY-MM}/
      {date}_{app_name}_{session_id}.md   ← 一个 Session 一个文件
```

- 同一 Session 的多轮对话**追加**到同一个文件（`mode="a"`）
- 跨天的同一 Session 会创建新文件（因为 `date_str` 变化）
- 文件头包含 YAML 前置元数据（user_id, app_name, session_id, created_at）
