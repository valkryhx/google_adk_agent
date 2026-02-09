# 技能导入指南 (Import Skills)

本文档说明了 Ciri 中的技能如何管理和导入，重点介绍核心技能和动态加载机制。

## 1. 核心技能概览

Ciri 自带一组必要的技能，定义了其基础能力。

### Bash Skill (系统终端)
*   **用途**: 执行系统命令。
*   **实现**: `skills/bash/tools.py`
*   **关键特性**: 使用 `get_tools` 模式实现懒加载。提供安全的执行环境，内置黑名单拦截危险命令（如 `rm -rf`, `format`）。

### File Edit Skill (文件编辑)
*   **用途**: 修改文件（读取、写入、替换）。
*   **实现**: `skills/file_editor/tools.py`
*   **关键特性**: Agent "Vibe Coding" 能力的核心，使其能够直接修改代码库。

### Playwright-CLI Skill (浏览器操作)
*   **用途**: 自动化浏览器交互，用于网页测试和数据抓取。
*   **实现**: `skills/playwright-cli/SKILL.md` (CLI 工具封装)
*   **能力**:
    *   **浏览器自动化**: 可以打开网页、点击元素、填写表单、截图。
    *   **JS 执行**: 扩展了 Web Search 能力，允许在页面上执行 JavaScript，从而与静态爬虫无法获取的动态内容交互。
    *   **会话管理**: 支持持久化浏览器会话。

## 2. 动态技能加载机制

`SkillManager` (`src/adk_agent/core/manager.py`) 负责管理技能的生命周期。

*   **懒加载 (Lazy Loading)**: 技能在启动时不会完全加载。
    1.  **发现阶段**: 管理器只需要扫描 `skills/` 目录并读取 `SKILL.md` 的 `frontmatter` (YAML 头) 来获取技能名称和描述。这用于路由分发。
    2.  **执行阶段**: 只有当 Agent 决定使用某个技能时，才会加载完整的指令集 (`SKILL.md` 正文) 和工具定义 (`tools.py`)。
*   **`get_tools` 模式**: 我们强烈建议在 `tools.py` 中使用 `def get_tools(*args, **kwargs) -> List:`。这种延迟加载确保了繁重的初始化（如数据库连接或浏览器启动）仅在真正需要技能时才发生。

## 3. Dynamic MCP (动态模型上下文协议)

Dynamic MCP 允许 Ciri 在运行时连接到外部 MCP 服务器，无需预先配置。

*   **实现**: `skills/dynamic-mcp/tools.py`
*   **工作流**:
    1.  **发现**: 你可以让 Ciri "查找一个天气 MCP 服务器"。
    2.  **网络搜索**: Ciri 使用 Web Search 找到公开的 MCP 服务器 URL 或部署指南。
    3.  **直接连接**: Ciri 调用 `connect_mcp(url=...)`。该技能自动处理协议协商 (SSE vs HTTP) 和认证头。
    4.  **无需配置**: 与静态 MCP 客户端不同，你不需要编辑配置文件。只需告诉 Ciri URL，它就会连接。

## 4. Compactor Skill (记忆压缩)

*   **用途**: 管理上下文压缩。
*   **实现**: `skills/compactor/tools.py`
*   **角色**: 这是一个关键的"元技能"，帮助管理 Agent 的记忆。它定义了触发压缩的工具，但真正的智能驻留在 `AutoCompactAgent` 中。
