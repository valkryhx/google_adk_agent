# Programmatic Tool Calling (PTC)

Programmatic Tool Calling (PTC) is a powerful paradigm that allows the agent to use **code as orchestration**. Instead of making multiple round-trips to the LLM for sequential steps (React Loop), the agent writes a single Python script to execute complex logic, loops, and conditional tool calls in one go.

## 1. The Concept

**Traditional Agent Loop:**
1.  Agent: "List files." -> Tool Output: [file1, file2, file3]
2.  Agent: "Read file1." -> Tool Output: content1
3.  Agent: "Read file2." -> Tool Output: content2
...

**PTC Approach:**
1.  Agent: "Write a script to read all files and find the one containing 'password'."
2.  Script executes: Lists files, loops through them, reads content, checks condition, returns result.
3.  Agent receives final answer.

## 2. Implementation

*   **Skill**: `skills/programmatic-tool-calling`
*   **Tool**: `run_programmatic_task(code: str)`
*   **Key Mechanism**: The executed code has access to a special async function:
    ```python
    await call_tool(tool_name: str, **kwargs) -> Any
    ```
    This bridge allows the sandboxed Python code to invoke any other tool available to the agent (e.g., `web_search`, `file_editor`).

## 3. Usage Example

**Task**: Search for the stock price of Apple, Google, and Microsoft, and find the highest one.

**Generated Code**:
```python
tickers = ['AAPL', 'GOOGL', 'MSFT']
prices = {}

for ticker in tickers:
    # Programmatically calling the web_search tool!
    result = await call_tool('web_search', query=f"{ticker} stock price")
    # ... parse price from result ...
    prices[ticker] = parsed_price

highest = max(prices, key=prices.get)
print(f"The highest stock is {highest} at {prices[highest]}")
```

## 4. Best Practices

*   **Use for Orchestration**: Perfect for "Map-Reduce" type tasks (do X for every item in list Y).
*   **Don't Overuse**: For simple, single-step actions, direct tool calling is faster and less prone to code errors.
*   **Error Handling**: The agent should include try-except blocks in the generated code to handle potential tool failures gracefully.
