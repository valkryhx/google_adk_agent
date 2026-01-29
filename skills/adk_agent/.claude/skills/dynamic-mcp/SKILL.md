---
name: "Dynamic MCP Loader"
description: "动态 MCP 工具加载器，支持运行时连接远程 HTTP/SSE MCP 服务或启动本地 MCP 进程，让 Agent 根据需求即时扩展能力。适用于用户提到不熟悉的 MCP 服务时，通过搜索发现连接方式后动态加载。"
---

# Dynamic MCP Loader

## 概述

Dynamic MCP Loader 是一个**元工具**（Meta-Tool），赋予 Agent **"自主扩张能力"**。

它允许 Agent 在运行时动态加载新的 MCP 工具，而无需重启服务或修改配置文件。Agent 可以：
1. 通过 Web 搜索发现 MCP 服务的连接方式（URL 或 npx 命令）
2. 调用 `connect_mcp` 工具动态挂载该服务
3. 立即使用新加载的 MCP 工具完成用户任务

**核心优势**：实现"Just-in-Time Tooling"（即时工具化）模式，Agent 不再需要背负几百个工具运行，而是按需"下载"技能。

## 何时使用此 Skill

**触发场景**：
- 用户提到某个 MCP 服务名称（如 "用 context7 查文档"、"用 brave search"）
- 用户要求使用特定功能但当前工具列表中没有对应工具
- 用户明确要求"安装"或"连接"某个 MCP Server

**典型工作流**：
```
用户请求 → Web Search 查找连接方式 → connect_mcp 动态加载 → 使用新工具
```

## 核心工具

### connect_mcp

**功能**：全能型 MCP 加载器，支持远程和本地两种模式。


**参数说明**：

| 参数       | 类型                    | 必需         | 说明                                              |
| ---------- | ----------------------- | ------------ | ------------------------------------------------- |
| `mode`     | `"remote"` 或 `"local"` | 是           | 连接模式                                          |
| `source`   | `str`                   | 是           | 远程模式填 URL，本地模式填基础命令（如 `npx`）    |
| `args`     | `List[str]`             | 本地模式必需 | 命令参数列表                                      |
| `env_vars` | `Dict[str, str]`        | 否           | 本地模式专用，环境变量（如 `BRAVE_API_KEY`）      |
| `api_key`  | `str`                   | 否           | 远程模式专用，API Key 用于服务认证（如 Context7） |

**返回值**：执行结果信息字符串

## 使用指南

### 模式 A：远程 HTTP/SSE 服务

**适用场景**：MCP 服务以 HTTP 或 Server-Sent Events (SSE) 方式提供。

**执行步骤**：
1. 通过搜索获取 MCP 服务的 URL
2. 调用 `connect_mcp`，`mode="remote"`，`source` 填写 URL
3. ADK 会自动连接并提取工具定义

**示例 1：无需认证的远程服务**

用户请求："连接公开的 MCP 服务"

```
Tool: connect_mcp(
    mode="remote",
    source="https://example.com/mcp"
)
Result: "[Success] remote MCP 工具加载成功！"
```

**示例 2：需要 API Key 认证的远程服务（Context7）**

用户请求："用 context7 查一下 fastmcp 库的最新版本，我的 API Key 是 ctx7sk-xxxxx"

```
Step 1: Web Search
Tool: web_search("context7 mcp server url")
Result: "Context7 MCP is available at https://mcp.context7.com/mcp"

Step 2: Dynamic Load with API Key
Tool: connect_mcp(
    mode="remote",
    source="https://mcp.context7.com/mcp",
    api_key="ctx7sk-xxxxx"
)
Result: "[Success] remote MCP 工具加载成功！"

Step 3: Use New Tool
Tool: resolve_library_id(library_name="fastmcp")
Tool: query_docs(library_id="/...", query="latest version")
```

**重要说明**：
- Context7 使用自定义认证 header `CONTEXT7_API_KEY`（非标准 Bearer Token）
- API Key 格式：`ctx7sk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- 工具会自动检测 `context7.com` 域名并使用正确的 header 名称

### 模式 B：本地进程启动

**适用场景**：MCP 服务需要通过 `npx`、`python` 等命令在本地启动。

**执行步骤**：
1. 通过搜索获取启动命令（如 `npx -y @modelcontextprotocol/server-git`）
2. 将命令拆解为 `command` 和 `args` 列表
3. 调用 `connect_mcp`，`mode="local"`
4. 如果需要 API Key，通过 `env_vars` 传入

**示例 1：Git MCP**

用户请求："帮我启用 git 的 mcp 工具"

```
Step 1: Web Search (如果不知道启动方式)
Tool: web_search("modelcontextprotocol git server npx")
Result: "Run using: npx -y @modelcontextprotocol/server-git"

Step 2: Dynamic Load
Tool: connect_mcp(
    mode="local",
    source="npx",
    args=["-y", "@modelcontextprotocol/server-git"]
)
Result: "[Success] local MCP 工具加载成功！"

Step 3: Use New Tool
Tool: git_status()
Tool: git_log(limit=10)
```

**示例 2：Brave Search MCP（需要 API Key）**

用户请求："用 Brave Search 的 MCP，我的 Key 是 BS-xxxxx"

```
Step 1: Web Search
Tool: web_search("brave search mcp server installation")
Result: "npx -y @modelcontextprotocol/server-brave-search"

Step 2: Dynamic Load with Env Vars
Tool: connect_mcp(
    mode="local",
    source="npx",
    args=["-y", "@modelcontextprotocol/server-brave-search"],
    env_vars={"BRAVE_API_KEY": "BS-xxxxx"}
)
Result: "[Success] local MCP 工具加载成功！"

Step 3: Use New Tool
Tool: brave_web_search(query="AI news today")
```

## 参数构造技巧

**关键点**：从搜索结果的**字符串命令**转化为**结构化参数**。

### 命令拆解规则

**原始命令**：`npx -y @modelcontextprotocol/server-sqlite --db-path ./data.db`

**拆解为**：
```python
mode="local"
source="npx"
args=["-y", "@modelcontextprotocol/server-sqlite", "--db-path", "./data.db"]
```

**注意事项**：
- `args` 必须是**列表**，不能是字符串
- 每个参数和值都是独立的列表项
- 如果用户提供了具体文件路径，替换掉搜索结果中的示例路径

### 环境变量处理

**何时使用 env_vars**：
- MCP 文档提到需要设置环境变量（如 `BRAVE_API_KEY`, `OPENAI_API_KEY`）
- 用户明确提供了 API Key

**示例**：
```python
env_vars={
    "BRAVE_API_KEY": "用户提供的Key",
    "DEBUG": "true"  # 如果需要调试模式
}
```

## 安全机制

### 1. 命令白名单

**本地模式仅允许以下基础命令**：
- `npx`, `uvx`: Node.js 包管理工具
- `node`: Node.js 运行时
- `python`, `python3`: Python 解释器

**拒绝示例**：
```python
connect_mcp(mode="local", source="rm", args=["-rf", "/"])
# 返回: "[Security] 拒绝执行：命令 'rm' 不在白名单中"
```

### 2. 参数注入防护

**禁止参数中包含以下字符**：
- 管道符 `|`
- 重定向 `>`, `<`
- 命令分隔 `;`, `&`
- 命令替换 `` ` ``, `$(`

**拒绝示例**：
```python
connect_mcp(mode="local", source="npx", args=["-y", "package; rm -rf /"])
# 返回: "[Security] 参数 'package; rm -rf /' 含非法字符"
```

### 3. 智能去重

**防止重复加载同一服务**：
- 远程模式：对比 URL（忽略末尾斜杠）
- 本地模式：对比 `command + args` 完全匹配

**示例**：
```python
# 第一次调用
connect_mcp(mode="remote", source="https://mcp.context7.com/mcp")
# 返回: "[Success] ..."

# 第二次调用相同 URL
connect_mcp(mode="remote", source="https://mcp.context7.com/mcp/")
# 返回: "无需重复连接：已连接到远程服务 https://mcp.context7.com/mcp"
```

## 故障排查

### 常见问题

**问题 1**：`[System] 找不到命令 'npx'`

**原因**：系统未安装 Node.js。

**解决**：提示用户安装 Node.js，或使用 `bash` skill 先执行 `node --version` 确认环境。

---

**问题 2**：`[Error] 加载 MCP 失败: Connection timeout`

**原因**：
- 远程模式：URL 错误或服务不可用
- 本地模式：NPM 包下载超时（首次运行需要下载）

**解决**：
- 检查网络连接
- 确认 URL 是否正确
- 本地模式：等待更长时间或提示用户手动预安装包

---

**问题 3**：工具加载成功但 Agent 没有调用新工具

**原因**：ADK 的工具列表更新需要在下一轮对话时生效。

**解决**：确保 `connect_mcp` 成功返回后，Agent 在**下一次思考**时会自动看到新工具。如果仍未调用，可能是工具描述不够清晰或用户需求表述不明确。

## 进阶用法

### 结合 Bash Skill 预检查环境

**最佳实践**：在动态加载前，先用 `bash` skill 确认环境。

```
Step 1: Environment Check
Tool: bash(command="node --version", timeout=5)
Result: "v20.10.0"

Step 2: Install if Needed
Tool: bash(command="npm install -g @modelcontextprotocol/server-git", timeout=60)

Step 3: Dynamic Load
Tool: connect_mcp(mode="local", source="npx", args=["-y", "@..."])
```

### 会话生命周期管理

**重要提示**：
- 动态加载的 MCP 工具仅在**当前会话**有效
- 用户的每个会话都有独立的 `agent` 实例，修改 `agent.tools` 不会影响其他用户
- 会话结束后，本地启动的进程会被自动清理（由 ADK 的 `McpToolset` 管理）

### 探索新 MCP 服务

**通用流程模板**：

```
User: "我想试用一个叫 [SERVICE_NAME] 的 MCP 工具"

Agent 执行:
1. web_search("[SERVICE_NAME] mcp server installation")
2. 分析搜索结果，识别连接方式
3. 如果是 URL → connect_mcp(mode="remote", source="URL")
4. 如果是命令 → 拆解后 connect_mcp(mode="local", ...)
5. 等待工具加载成功提示
6. 探索新工具的功能并完成用户任务
```

## 系统提示词建议

**为了让 Agent 正确使用此 Skill，建议在 System Prompt 中添加**：

```markdown
### 动态 MCP 能力扩展

你可以使用 `connect_mcp` 工具来扩展你的能力。使用步骤：

1. **先搜索**：使用搜索引擎查找目标 MCP 的安装或连接方式。

2. **后连接**：
   - **远程服务**（HTTP URL）→ `connect_mcp(mode="remote", source="URL")`
   - **本地包**（npx/python 命令）→ `connect_mcp(mode="local", source="npx", args=[...])`

3. **参数构造**：
   - 将搜索到的命令字符串拆解为列表
   - 例如：`npx -y pkg arg` → `args=["-y", "pkg", "arg"]`
   - 如果需要 API Key，通过 `env_vars` 参数传入

4. **使用新工具**：连接成功后，下一轮思考时即可看到并使用新工具。
```

## 技术原理

**运行时工具注入**：
- 利用 ADK 的依赖注入机制，`get_tools(agent, ...)` 获取当前 `agent` 实例
- 通过 `agent.tools.append(new_toolset)` 直接修改运行中的工具列表
- ADK 在下一次生成 Prompt 时会自动读取更新后的 `agent.tools`，将新工具 Schema 发送给 LLM

**McpToolset 自动发现**：
- `McpToolset` 对象被添加到工具列表后，ADK 会自动调用其内部的工具发现机制
- 远程模式：发送 `tools/list` JSON-RPC 请求获取工具定义
- 本地模式：通过 Stdio 管道与子进程通信，握手后获取工具列表

## 资源目录说明

**此 Skill 不包含额外的 scripts/references/assets 资源**，因为：
- 核心逻辑已完全封装在 `tools.py` 中
- 不需要外部脚本或模板文件
- 所有必要的安全规则和逻辑都在代码内部实现

**如果未来需要扩展**，可以添加：
- `references/mcp_registry.json`：预定义的常用 MCP 服务列表
- `scripts/validate_mcp.py`：MCP 服务健康检查脚本
