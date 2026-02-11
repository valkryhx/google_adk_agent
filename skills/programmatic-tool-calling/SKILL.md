---
name: programmatic-tool-calling
description: 编程化工具调用指南。允许 Agent 编写并执行 Python 代码，从而能够在一个沙箱环境中动态调用其他工具，实现循环、批处理和复杂逻辑。
---

# 编程化工具调用 (Programmatic Tool Calling) - ADK 增强版

本技能赋予了 Agent 编写并在沙箱中执行 Python 代码的能力。最强大的特性是：**可以在 Python 代码中动态调用 Agent 的其他工具**。

## 核心工具: `run_programmatic_task`

这是本技能提供的唯一工具。

### 何时使用 (Best Practice)

当遇到以下情况时，**必须**使用此工具，而不是尝试通过多轮对话来解决：

1.  **批处理任务 (Batch Processing)**: 例如 "搜索 10 个不同的关键词并汇总结果"。如果分 10 次调用 `web_search`，会浪费大量 Token 和时间。
2.  **数据聚合与处理 (Aggregation)**: 例如 "获取 A、B、C 三个文件，提取其中的数据，计算平均值，并画图"。
3.  **复杂逻辑控制 (Control Flow)**: 需要使用循环 (`for`/`while`)、条件判断 (`if`/`else`) 或重试逻辑来控制工具调用。
4.  **长输出处理**: 需要处理大量文本或数据，且中间过程不需要展示给用户。

### 何时不使用

- **简单直线性任务**: 如 "查询北京的天气"。直接调用 `web_search` 即可。
- **纯计算任务**: 如 "计算 1+1"。直接输出结果。

### 🚨 禁止使用的模式 (Forbidden Patterns)

**严禁使用 `bash` 工具来运行 Python 脚本以完成此类任务！**
- ❌ 错误:调用 `bash` 执行 `python -c "import requests..."`
  - 原因: 无法访问 Agent 的工具链 (`call_tool` 不可用)，无法复用 Session 状态，且难以处理异步逻辑。
- ✅ 正确: 直接调用 `run_programmatic_task` 工具，将代码作为参数传入。

---

## 编写代码指南

你编写的代码不仅是标准的 Python 代码，还运行在一个预配置的 `async` 环境中。

### 关键函数: `await call_tool(...)`

环境内置了一个特殊函数 `call_tool`，用于调用 Agent 已加载的其他工具。

```python
await call_tool(tool_name: str, **kwargs) -> Any
```

- **tool_name**: 工具的名称（字符串）。必须是 Agent 当前已加载的工具（如 `web_search`, `codebase_search`, `bash` 等）。
- **kwargs**: 传递给目标工具的参数。

### 可用库 (Pre-installed Libraries)

沙箱环境预装了以下数据科学和异步库：
- `pandas` (已导入为 `pd`)
- `matplotlib.pyplot` (已导入为 `plt`)
- `asyncio` (已导入为 `asyncio`)
- 标准库 (`json`, `os`, `re`, `math` 等)

---

## 示例 (Examples)

### 示例 1: 批量搜索并汇总 (Batch Search)

**任务**: "搜索 Python, JavaScript, Go 的最新特性，并统计结果长度。"

```python
# 注意：代码无需包裹在 def 中，但建议使用 main 函数保持整洁
# 必须使用 await 调用 call_tool

async def main():
    queries = [
        "Python 3.13 new features",
        "JavaScript ES2024 features",
        "Go 1.22 new features"
    ]
    
    results = {}
    print(f"开始批量搜索 {len(queries)} 个主题...")
    
    for q in queries:
        print(f"正在搜索: {q}")
        # 调用 web_search 工具 (假设该工具已加载)
        # 如果不确定工具名，可以使用 bash 调用脚本
        try:
            # 方式 A: 直接调用工具 (推荐)
            output = await call_tool('web_search', query=q)
        except:
            # 方式 B:降级使用 bash
            output = await call_tool('bash', command=f'echo "Search failed for {q}"')
            
        results[q] = len(str(output))
        print(f"  -> 结果长度: {len(str(output))}")

    print("\n统计结果:")
    print(pd.Series(results))

# 启动执行
await main()
```

### 示例 2: 数据处理与绘图 (Data Analysis)

**任务**: "生成一组随机数据并画图。"

```python
import numpy as np

# 生成数据
x = np.linspace(0, 10, 100)
y = np.sin(x)

# 绘图
plt.figure(figsize=(10, 6))
plt.plot(x, y, label='Sin(x)')
plt.title('Demo Plot')
plt.grid(True)

# 这一步不是必须的，但在某些环境中可以保存图片
plt.savefig('sine_wave.png')
print("图表已生成: sine_wave.png")

# 在 pandas 中处理
df = pd.DataFrame({'x': x, 'y': y})
print("\n数据摘要:")
print(df.describe())
```

---

## ⚠️ 重要注意事项 (Critical Notes)

1.  **必须使用 `await`**: 调用 `call_tool` 时必须加 `await`，否则会返回协程对象而不是结果。
2.  **打印结果**: 工具会捕获标准输出 (`stdout`) 作为返回值。**如果你不 `print()`，你将看不到任何结果**。
3.  **不要使用 `asyncio.run()`**: 代码是在一个已经在运行的事件循环中执行的。使用 `asyncio.run()` 会报错。直接 `await` 你的异步函数即可。
4.  **工具名准确性**: 调用 `call_tool` 前，请确认 Agent 加载了哪些工具。如果不确定，可以先调用 `get_tools` 或查看系统提示。
5.  **防止超时**: 如果任务非常耗时（超过 5 分钟），请分批执行或申请更多时间。
6.  **UI 交互**: 生成代码需要时间。在调用此工具前，**请先输出一段思考文本**（如 "正在编写脚本进行批量处理..."），以免用户觉得界面卡死。
