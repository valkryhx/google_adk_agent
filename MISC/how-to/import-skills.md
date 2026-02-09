# Import Skills Guide

This guide explains how skills are managed and imported in Ciri, highlighting the core skills and the dynamic loading mechanism.

## 1. Core Skills Overview

Ciri comes with a set of essential skills that define its foundational capabilities.

### Bash Skill
*   **Purpose**: Executes system commands.
*   **Implementation**: `skills/bash/tools.py`
*   **Key Feature**: Uses the `get_tools` pattern for lazy loading. It provides a safe execution environment with a blacklist of dangerous commands (e.g., `rm -rf`, `format`).

### File Edit Skill
*   **Purpose**: Modifies files (read, write, replace).
*   **Implementation**: `skills/file_editor/tools.py`
*   **Key Feature**: Essential for the agent's "Vibe Coding" capability, allowing it to modify codebases directly.

### Playwright-CLI Skill
*   **Purpose**: Automates browser interactions for web testing and data extraction.
*   **Implementation**: `skills/playwright-cli/SKILL.md` (CLI tool wrapper)
*   **Capabilities**:
    *   **Browser Automation**: Can open pages, click elements, fill forms, and take screenshots.
    *   **JS Execution**: Extends web search capabilities by allowing JavaScript execution on pages, enabling interaction with dynamic content that static scrapers miss.
    *   **Session Management**: Supports persistent browser sessions.

## 2. Dynamic Skill Loading Mechanism

The `SkillManager` (`src/adk_agent/core/manager.py`) handles the lifecycle of skills.

*   **Lazy Loading**: Skills are not fully loaded at startup.
    1.  **Discovery Phase**: The manager scans the `skills/` directory and reads only the `frontmatter` (YAML header) of `SKILL.md` to get the skill name and description. This is used for routing.
    2.  **Execution Phase**: Only when the agent decides to use a skill is the full instruction set (body of `SKILL.md`) and the tool definitions (`tools.py`) loaded.
*   **`get_tools` Pattern**: We strongly recommend using `def get_tools(*args, **kwargs) -> List:` in `tools.py`. This deferral ensures that heavy initializations (like database connections or browser launches) only happen when the skill is actually needed.

## 3. Dynamic MCP (Model Context Protocol)

Dynamic MCP allows Ciri to connect to external MCP servers at runtime without pre-configuration.

*   **Implementation**: `skills/dynamic-mcp/tools.py`
*   **Workflow**:
    1.  **Discovery**: You can ask Ciri to "Find a weather MCP server".
    2.  **Web Search**: Ciri uses web search to find a public MCP server URL or deployment guide.
    3.  **Direct Connection**: Ciri calls `connect_mcp(url=...)`. The skill automatically handles protocol negotiation (SSE vs HTTP) and authentication headers.
    4.  **No Config Needed**: Unlike static MCP clients, you don't need to edit a config file. Just tell Ciri the URL, and it connects.

## 4. Compactor Skill

*   **Purpose**: Manages context compression.
*   **Implementation**: `skills/compactor/tools.py`
*   **Role**: It is a critical "meta-skill" that helps manage the agent's memory. It defines tools for triggering compression, but the actual intelligence resides in the `AutoCompactAgent`.

