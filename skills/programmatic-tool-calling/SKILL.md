---
name: programmatic-tool-calling
description: Guide and tool for Programmatic Tool Calling. Allows the Agent to write and execute Python code that can dynamically invoke other tools.
---

# Programmatic Tool Calling (ADK Enhanced)

This skill provides the capability to write Python code that runs in a sandbox but can **dynamically call other Agent tools**.

## Tool: `run_programmatic_task`

The primary tool exposed by this skill is `run_programmatic_task`.

### Usage

You should use this tool when:
1.  You need to perform a task that requires loops, conditionals, or complex data processing combined with tool calls.
2.  You want to "batch process" something (e.g., search for 10 different terms and aggregate the results).
3.  You need to feed the output of one tool into another loop.

### When NOT to Use
**Do not use this tool** for simple, linear tasks where `chain of thought` is sufficient.
- **Bad Use Case**: "Search for the weather in Paris." (Just call `web_search` directly)
- **Bad Use Case**: "Calculate 1+1." (Just execute code or output result directly)
- **Good Use Case**: "Search for the weather in 5 different cities, compare them, and print the hottest one." (Requires `programmatic-tool-calling`)

### How to Write Code

The code you write will run in an `async` environment. You have access to a special function:

```python
await call_tool(tool_name: str, **kwargs) -> Any
```

**Example:**

```python
# Task: Search for 'Apple', 'Banana', 'Cherry' and count the length of results.
results = {}
queries = ['Apple', 'Banana', 'Cherry']

for q in queries:
    # Notice the 'await' and the tool name string
    # 'web_search' or 'google_search' depending on what tools are loaded
    output = await call_tool('web_search', query=q)
    results[q] = len(str(output))

print(f"Search lengths: {results}")
```

### Supported Libraries
- `pandas` (as `pd`)
- `matplotlib.pyplot` (as `plt`)
- `asyncio`
- Standard Python 3.12 libraries

### Important Notes
1.  **Always use `await`** when using `call_tool`.
2.  **Check Tool Names**: You can only call tools that are currently loaded on the Agent. If you are unsure, just try to use the likely name or ask (internally).
3.  **Output**: The tool returns the `stdout` (print output) of your script. Ensure you `print()` the final result you want to see.
4.  **No `asyncio.run()`**: The code is executed in an already running event loop. Do NOT use `asyncio.run()`, `loop.run_until_complete()`, or `time.sleep()`. Instead, simply `await` your functions or use `await asyncio.sleep()`.
5.  **Entry Point**: Ensure your main logic is called at the top level, e.g., `await main()`.
6.  **Prevent UI Lag**: Since generating code takes time, **YOU MUST** output a brief "Thinking" or plan *before* calling this tool.
    *   **Bad**: (Silent) -> Calls tool -> User waits 10s -> Result.
    *   **Good**: "Thinking: I will write a script to fetch data..." -> Calls tool -> User sees text immediately.
