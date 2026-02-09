# Programmatic Tool Calling (PTC / 编程方式调用工具)

Programmatic Tool Calling (PTC) 是一种强大的范式，允许 Agent 使用**代码作为编排手段**。Agent 不必为了顺序步骤与 LLM 进行多次往返（ReAct 循环），而是编写一个 Python 脚本一次性执行复杂的逻辑、循环和条件工具调用。

## 1. 概念

**传统 Agent 循环:**
1.  Agent: "列出文件。" -> Tool Output: [file1, file2, file3]
2.  Agent: "读取 file1。" -> Tool Output: content1
3.  Agent: "读取 file2。" -> Tool Output: content2
...

**PTC 方法:**
1.  Agent: "编写脚本读取所有文件并找到包含 'password' 的文件。"
2.  脚本执行: 列出文件，循环遍历，读取内容，检查条件，返回结果。
3.  Agent 收到最终答案。

## 2. 实现

*   **Skill**: `skills/programmatic-tool-calling`
*   **Tool**: `run_programmatic_task(code: str)`
*   **关键机制**: 执行的代码可以访问一个特殊的异步函数：
    ```python
    await call_tool(tool_name: str, **kwargs) -> Any
    ```
    这个桥接允许受沙盒限制的 Python 代码调用 Agent 可用的任何其他工具（例如 `web_search`, `file_editor`）。

## 3. 使用示例

**任务**: 搜索 Apple, Google, 和 Microsoft 的股价，并找到最高的一个。

**生成的代码**:
```python
tickers = ['AAPL', 'GOOGL', 'MSFT']
prices = {}

for ticker in tickers:
    # 编程方式调用 web_search 工具！
    result = await call_tool('web_search', query=f"{ticker} stock price")
    # ... 从结果中解析价格 ...
    prices[ticker] = parsed_price

highest = max(prices, key=prices.get)
print(f"最高股价是 {highest}: {prices[highest]}")
```

## 4. 最佳实践

*   **用于编排**: 非常适合 "Map-Reduce" 类型的任务（对列表 Y 中的每一项做 X）。
*   **不要滥用**: 对于简单的单步操作，直接工具调用更快，且不易出错。
*   **错误处理**: Agent 应在生成的代码中包含 try-except 块，以优雅地处理潜在的工具故障。
