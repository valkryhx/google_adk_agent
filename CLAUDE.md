# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 强制执行规则（工具调用）

- 执行任何任务时，**必须调用工具**（如 Read / Edit / Grep / Bash 等）来产生可验证的实际操作。
- **禁止**只回复“好的”“收到”“我来处理”等无实质执行内容的文本。
- 若当前步骤确实无法直接执行，也必须先通过工具进行必要检查（如读取文件、检索路径、查看状态）后再反馈。

## Windows 中文/Emoji 命令执行

在 Windows 上执行任何会输出中文或 emoji 的命令时，必须加环境变量，否则会得到乱码或 UnicodeDecodeError：

```bash
# Python 脚本
PYTHONIOENCODING=utf-8 python script.py

# 启动 Agent 服务
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8000

# 读取 Python 脚本输出时（subprocess）
# 使用 encoding='utf-8' + PYTHONIOENCODING=utf-8 环境变量
```

日志文件重定向（`> logs/xxx.log 2>&1`）同样需要此变量，否则 emoji 会导致进程在写入 log 前崩溃。

## Running the Agent

All commands run from the project root:

```bash
# Start the main agent server (multi-tenant steering version)
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering [--port 8000]

# Alternative entry points
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering_single_agent
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

`private_key.yaml` at the project root is the single config file. It is **not committed** (contains secrets). Structure:

```yaml
active_model: <label-name>   # which llm_configs entry to use
warn_turns: 600
max_turns: 700
max_context_tokens: 200000
llm_configs:
  <label-name>:
    model: openai/<model-id>  # litellm model string
    api_key: "..."
    api_base: "https://..."
tavily_api_key: "..."
```

`AgentConfig` (`src/adk_agent/config.py`) reads this file and hot-reloads on every access. The active model can also be overridden via the `ACTIVE_MODEL` environment variable.

## Architecture

### Request Flow

```
HTTP/WebSocket (FastAPI)
  └─ SteeringSession          # per-session state + interruption control
       └─ google.adk.Runner
            └─ LlmAgent (Ciri)
                 ├─ LiteLlm backend (via litellm, any OpenAI-compatible API)
                 ├─ SkillManager  ← lazy-loads skills from skills/
                 └─ AutoCompactAgent  ← sub-agent for context compression
```

### Session Persistence

`FullyCustomDbService` (`src/shared/db/custom_table_db_service.py`) implements `BaseSessionService` from ADK using async SQLAlchemy + SQLite (`aiosqlite`). Table names are dynamic (generated from port number) to support physical isolation between swarm nodes running on different ports.

### Skills System (Two-Phase Lazy Loading)

`SkillManager` (`src/adk_agent/core/manager.py`) manages skill lifecycle:

1. **Discovery phase** (startup): scans `skills/*/SKILL.md`, reads only the YAML frontmatter to build a manifest of `{name, description}` pairs injected into the system prompt.
2. **Execution phase** (on demand): when the agent chooses a skill, the full SKILL.md body (SOP/instructions) is loaded and the `tools.py` module is imported.

Every skill directory contains:
- `SKILL.md` — YAML frontmatter (`name`, `description`) followed by `---` and the full instruction body
- `tools.py` — tool functions; **must expose `get_tools(*args, **kwargs) -> List`** for deferred initialization (avoids loading heavy deps like browsers/DBs at startup)

### Context Compression

`AutoCompactAgent` (`src/adk_agent/auto_compact_agent.py`) is a sub-`LlmAgent` that runs a one-shot summarization task via a temporary `Runner`. It is invoked when conversation history approaches the token limit, replacing raw history with a condensed summary.

### Async Task Execution (Dex)

The `dex` skill decouples long-running tasks (>10s) from the agent loop. Workflow: `dex_create_task` → `dex_start_task` (runs command as background subprocess) → poll with `dex_list_tasks` → `dex_get_task_details`. Use `dex` instead of `bash` for anything that blocks.

## Adding a New Skill

1. Create `skills/<skill-name>/SKILL.md`:
   ```markdown
   ---
   name: "Human-readable name"
   description: "One-line description for agent routing"
   ---
   # Full instructions / SOP for the agent
   ...
   ```
2. Create `skills/<skill-name>/tools.py` with a `get_tools()` function returning a list of callable tools.

The skill is auto-discovered on next server start — no registration required.

## Windows Encoding Fix

On Windows, Python's default console encoding (GBK/CP936) causes `UnicodeEncodeError` when printing emoji or Chinese characters. Any new skill module or script that uses emoji in `print()` statements must include this block near the top of the file (after standard library imports):

```python
import sys
if sys.platform == "win32":
    import codecs
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")
```

This pattern is already applied in: `verification_hooks.py`, `inbox_watcher.py`, `task_queue.py`, `self_claim_loop.py`.

## Key Paths

| Path | Purpose |
|---|---|
| `src/adk_agent/main_web_start_steering.py` | Primary entry point (multi-tenant) |
| `src/adk_agent/config.py` | `AgentConfig` + system prompt builder |
| `src/adk_agent/core/manager.py` | `SkillManager` (lazy skill loader) |
| `src/adk_agent/core/executor.py` | `execute_python_code` sandbox |
| `src/adk_agent/auto_compact_agent.py` | Context compression sub-agent |
| `src/shared/db/custom_table_db_service.py` | SQLite session persistence |
| `skills/` | All skill directories |
| `private_key.yaml` | API keys + model config (not committed) |
