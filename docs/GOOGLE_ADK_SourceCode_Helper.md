# Google ADK Source Code Helper

> 本文档为 Claude Code / Codex 开发者提供 Google ADK (Agent Development Kit) 源码阅读指引。
> 所有路径基于 `C:\anaconda3\Lib\site-packages\google\adk\`，行号为截至文档创建时的快照。

---

## 目录

1. [Agent 体系](#1-agent-体系)
2. [Context 上下文体系](#2-context-上下文体系)
3. [Tool 工具体系](#3-tool-工具体系)
4. [MCP 集成体系](#4-mcp-集成体系)
5. [Flow 流程体系](#5-flow-流程体系)
6. [Model 模型体系](#6-model-模型体系)
7. [Session / State / Event](#7-session--state--event)
8. [Runner 运行器](#8-runner-运行器)
9. [Auth 认证体系](#9-auth-认证体系)
10. [Artifact / Memory / 其他](#10-artifact--memory--其他)

---

## 1. Agent 体系

### 1.1 BaseAgent — 所有 Agent 的基类

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| BaseAgent 类 | 所有 Agent 抽象基类 | `agents/base_agent.py` | L699 |
| sub_agents | 子 Agent 列表，构建 Agent 树 | `agents/base_agent.py` | L134 |
| parent_agent | 父 Agent 引用（property） | `agents/base_agent.py` | L125 |
| root_agent | 递归获取根 Agent | `agents/base_agent.py` | L366-372 |
| find_agent / find_sub_agent | 按 name 查找 Agent | `agents/base_agent.py` | L374-399 |
| before_agent_callback | Agent 执行前回调 | `agents/base_agent.py` | L137-164 |
| after_agent_callback | Agent 执行后回调 | `agents/base_agent.py` | L137-164 |
| clone | 深拷贝 Agent（含 sub_agents） | `agents/base_agent.py` | L209-269 |
| run_async | 异步运行入口 | `agents/base_agent.py` | L272-303 |
| _handle_before_agent_callback | 前置回调处理 | `agents/base_agent.py` | L432-488 |
| BaseAgentState | Agent 状态基类（current_sub_agent） | `agents/base_agent.py` | L74-83 |

### 1.2 LlmAgent — 核心大模型 Agent

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| LlmAgent 类 | 带 LLM 能力的核心 Agent | `agents/llm_agent.py` | L1001 |
| BeforeModelCallback | 模型调用前回调类型 | `agents/llm_agent.py` | L70-128 |
| AfterModelCallback | 模型调用后回调类型 | `agents/llm_agent.py` | L70-128 |
| BeforeToolCallback | 工具调用前回调类型 | `agents/llm_agent.py` | L100-128 |
| AfterToolCallback | 工具调用后回调类型 | `agents/llm_agent.py` | L100-128 |
| instruction | Agent 指令（str / callable） | `agents/llm_agent.py` | L205-217 |
| tools | 工具列表 | `agents/llm_agent.py` | L283 |
| output_key | 自动保存输出到 state 的 key | `agents/llm_agent.py` | L328-334 |
| _convert_tool_union_to_tools | 将各种 tool 格式统一转为 BaseTool | `agents/llm_agent.py` | L137-182 |
| canonical_tools | 获取规范化的工具列表 | `agents/llm_agent.py` | L593-615 |
| _llm_flow property | 懒加载 LLM Flow | `agents/llm_agent.py` | L700-708 |
| __maybe_save_output_to_state | 通过 output_key 保存输出到 state | `agents/llm_agent.py` | L812-844 |
| _handle_before_model_callback | 模型前回调处理 | `agents/llm_agent.py` | L358-446 |
| _handle_after_model_callback | 模型后回调处理 | `agents/llm_agent.py` | L358-446 |
| _handle_before_tool_callback | 工具前回调处理 | `agents/llm_agent.py` | L402-446 |
| _handle_after_tool_callback | 工具后回调处理 | `agents/llm_agent.py` | L402-446 |

### 1.3 LoopAgent — 循环 Agent

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| LoopAgent 类 | 循环执行 sub_agents | `agents/loop_agent.py` | L167 |
| LoopAgentState | current_sub_agent, times_looped | `agents/loop_agent.py` | L42-49 |
| max_iterations | 最大循环次数 | `agents/loop_agent.py` | L62-67 |
| _run_async_impl | 循环逻辑：escalate 检测 + pause 处理 | `agents/loop_agent.py` | L70-123 |
| _run_live_impl | raise NotImplementedError | `agents/loop_agent.py` | L148-153 |

### 1.4 SequentialAgent — 顺序 Agent

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| SequentialAgent 类 | 顺序执行 sub_agents | `agents/sequential_agent.py` | L160 |
| SequentialAgentState | current_sub_agent | `agents/sequential_agent.py` | L41-45 |
| _run_async_impl | 顺序迭代 + pause 处理 | `agents/sequential_agent.py` | L54-93 |
| _run_live_impl | 添加 task_completed 函数给每个 LlmAgent | `agents/sequential_agent.py` | L119-159 |

### 1.5 ParallelAgent — 并行 Agent

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| ParallelAgent 类 | 并行执行 sub_agents | `agents/parallel_agent.py` | L217 |
| _create_branch_ctx_for_sub_agent | 为每个子 Agent 创建隔离分支上下文 | `agents/parallel_agent.py` | L35-48 |
| _merge_agent_run | 使用 asyncio.TaskGroup（Python 3.11+） | `agents/parallel_agent.py` | L51-86 |
| _merge_agent_run_pre_3_11 | Python 3.10 回退方案 | `agents/parallel_agent.py` | L89-147 |
| _run_async_impl | 并行执行，分支隔离 | `agents/parallel_agent.py` | L163-209 |

---

## 2. Context 上下文体系

### 2.1 Context — 统一上下文类

> `CallbackContext` 和 `ToolContext` 现在都是 `Context` 的别名。

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| Context(ReadonlyContext) | 统一上下文类 | `agents/context.py` | L41 |
| __init__ | 初始化（invocation_context, _state, _actions） | `agents/context.py` | L44-73 |
| state property | 可写 State（delta-aware） | `agents/context.py` | L95-103 |
| actions property | EventActions 引用 | `agents/context.py` | L105-108 |
| load_artifact / save_artifact | Artifact 读写 | `agents/context.py` | L114-197 |
| list_artifacts | 列出 artifacts | `agents/context.py` | L114-197 |
| save_credential / load_credential | 凭证读写 | `agents/context.py` | L203-271 |
| request_credential | 请求凭证 | `agents/context.py` | L203-271 |
| request_confirmation | 请求用户确认 | `agents/context.py` | L277-307 |
| add_session_to_memory | 将当前会话加入记忆 | `agents/context.py` | L313-412 |
| search_memory | 搜索记忆 | `agents/context.py` | L313-412 |

### 2.2 别名关系

| 别名 | 指向 | 路径 | 行号 |
|------|------|------|------|
| CallbackContext | `Context` | `agents/callback_context.py` | L22 |
| ToolContext | `Context` | `agents/tool_context.py` | L30 |

### 2.3 ReadonlyContext — 只读基类

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| ReadonlyContext | 只读上下文基类 | `agents/readonly_context.py` | L72 |
| state property | → MappingProxyType（不可变视图） | `agents/readonly_context.py` | L54-56 |

### 2.4 InvocationContext — 运行时上下文

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| InvocationContext | 核心运行时上下文 | `agents/invocation_context.py` | L420 |
| session | 当前 Session | `agents/invocation_context.py` | L166 |
| agent_states | Agent 状态字典 | `agents/invocation_context.py` | L169 |
| end_invocation | 结束调用标志 | `agents/invocation_context.py` | L175 |
| should_pause_invocation | 检查是否暂停 | `agents/invocation_context.py` | L362-396 |

---

## 3. Tool 工具体系

### 3.0 BaseTool — 所有工具的基类

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| BaseTool(ABC) | 所有工具的抽象基类 | `tools/base_tool.py` | L47 |
| name / description | 工具名和描述 | `tools/base_tool.py` | L50-53 |
| is_long_running | 是否长运行操作 | `tools/base_tool.py` | L55-57 |
| custom_metadata | 自定义元数据（JSON 可序列化） | `tools/base_tool.py` | L59-66 |
| __init__ | 初始化 | `tools/base_tool.py` | L68-79 |
| _get_declaration | 获取 FunctionDeclaration（子类覆写） | `tools/base_tool.py` | L81-94 |
| run_async | 运行工具（子类必须覆写） | `tools/base_tool.py` | L96-113 |
| process_llm_request | 处理出站 LLM 请求（默认 append_tools） | `tools/base_tool.py` | L115-129 |
| from_config | 从配置创建工具实例（inspect 自动映射） | `tools/base_tool.py` | L135-211 |

### 3.1 FunctionTool — Python 函数工具

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| FunctionTool(BaseTool) | 将 Python callable 包装为 ADK Tool | `tools/function_tool.py` | L38 |
| __init__ | 提取 name/doc，_ignore_params=['tool_context','input_stream'] | `tools/function_tool.py` | L45-84 |
| _get_declaration | 使用 build_function_declaration | `tools/function_tool.py` | L86-98 |
| _preprocess_args | Pydantic model 从 JSON dict 转换 | `tools/function_tool.py` | L100-154 |
| run_async | 必选参数检查 + require_confirmation | `tools/function_tool.py` | L156-218 |
| _invoke_callable | 处理 sync/async callable | `tools/function_tool.py` | L220-235 |
| _call_live | input_stream 支持 | `tools/function_tool.py` | L238-263 |
| _get_mandatory_args | 提取必选参数 | `tools/function_tool.py` | L265-288 |

### 3.2 BaseToolset — 工具集合基类

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| BaseToolset(ABC) | 工具集合抽象基类 | `tools/base_toolset.py` | L63 |
| ToolPredicate Protocol | 工具过滤谓词 | `tools/base_toolset.py` | L40-57 |
| __init__ | tool_filter, tool_name_prefix | `tools/base_toolset.py` | L69-82 |
| get_tools (abstract) | 获取工具列表 | `tools/base_toolset.py` | L84-97 |
| get_tools_with_prefix | 应用前缀到工具名 | `tools/base_toolset.py` | L99-150 |
| _is_tool_selected | 应用 ToolPredicate 或 list filter | `tools/base_toolset.py` | L178-190 |
| process_llm_request | 修改出站 LLM 请求的钩子 | `tools/base_toolset.py` | L192-207 |
| get_auth_config | 获取认证配置 | `tools/base_toolset.py` | L209-225 |

---

## 4. MCP 集成体系

### 4.1 McpTool — MCP Tool 适配器

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| McpTool(BaseAuthenticatedTool) | 将 MCP Tool 转为 ADK Tool | `tools/mcp_tool/mcp_tool.py` | L115 |
| ProgressCallbackFactory Protocol | 进度回调工厂（per-tool） | `tools/mcp_tool/mcp_tool.py` | L53-112 |
| __init__ | mcp_tool, session_manager, auth, confirmation, headers, progress | `tools/mcp_tool/mcp_tool.py` | L125-182 |
| _get_declaration | 从 MCP inputSchema 构建 FunctionDeclaration | `tools/mcp_tool/mcp_tool.py` | L184-207 |
| _run_async_impl | 执行工具调用：auth headers + trace + session.call_tool | `tools/mcp_tool/mcp_tool.py` | L288-337 |
| _resolve_progress_callback | 解析进度回调（工厂 vs 直接） | `tools/mcp_tool/mcp_tool.py` | L339-371 |
| _get_headers | 从 credential 提取认证头（OAuth2/Bearer/Basic/APIKey） | `tools/mcp_tool/mcp_tool.py` | L373-457 |
| MCPTool (deprecated) | 旧名，使用 McpTool | `tools/mcp_tool/mcp_tool.py` | L460-469 |

### 4.2 McpToolset — MCP 工具集

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| McpToolset(BaseToolset) | 连接 MCP Server 并获取工具 | `tools/mcp_tool/mcp_toolset.py` | L64 |
| __init__ | connection_params, tool_filter, auth, confirmation, resources | `tools/mcp_tool/mcp_toolset.py` | L95-183 |
| get_tools | 从 MCP Server 获取工具列表 | `tools/mcp_tool/mcp_toolset.py` | L289-334 |
| _execute_with_session | 创建会话并执行协程（含 timeout） | `tools/mcp_tool/mcp_toolset.py` | L251-287 |
| read_resource | 读取 MCP 资源 | `tools/mcp_tool/mcp_toolset.py` | L336-357 |
| list_resources | 列出可用资源 | `tools/mcp_tool/mcp_toolset.py` | L359-368 |
| get_resource_info | 获取资源元数据 | `tools/mcp_tool/mcp_toolset.py` | L370-382 |
| close | 关闭所有 MCP 会话 | `tools/mcp_tool/mcp_toolset.py` | L384-395 |
| _get_auth_headers | 从 exchanged credential 构建认证头 | `tools/mcp_tool/mcp_toolset.py` | L185-249 |
| McpToolsetConfig | Pydantic 配置模型 | `tools/mcp_tool/mcp_toolset.py` | L448-487 |
| from_config | 从配置创建 McpToolset | `tools/mcp_tool/mcp_toolset.py` | L407-433 |
| MCPToolset (deprecated) | 旧名，使用 McpToolset | `tools/mcp_tool/mcp_toolset.py` | L436-445 |

### 4.3 MCPSessionManager — 会话管理器

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| MCPSessionManager | MCP 会话生命周期管理 | `tools/mcp_tool/mcp_session_manager.py` | L181 |
| StdioConnectionParams | Stdio 连接参数（server_params + timeout） | `tools/mcp_tool/mcp_session_manager.py` | L74-84 |
| SseConnectionParams | SSE 连接参数（url + headers + timeout） | `tools/mcp_tool/mcp_session_manager.py` | L87-105 |
| StreamableHTTPConnectionParams | Streamable HTTP 连接参数 | `tools/mcp_tool/mcp_session_manager.py` | L113-139 |
| retry_on_errors | 自动重试装饰器（检测 CancelledError） | `tools/mcp_tool/mcp_session_manager.py` | L142-178 |
| create_session | 创建/复用会话（按 headers hash 池化） | `tools/mcp_tool/mcp_session_manager.py` | L410-501 |
| _generate_session_key | 基于 headers 生成会话键 | `tools/mcp_tool/mcp_session_manager.py` | L243-268 |
| _is_session_disconnected | 检查会话是否断开 | `tools/mcp_tool/mcp_session_manager.py` | L299-308 |
| _cleanup_session | 清理会话（跨 event loop 安全） | `tools/mcp_tool/mcp_session_manager.py` | L310-364 |
| close | 关闭所有会话 | `tools/mcp_tool/mcp_session_manager.py` | L527-532 |

### 4.4 McpInstructionProvider — MCP 指令提供者

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| McpInstructionProvider | 从 MCP Server prompts 获取指令 | `agents/mcp_instruction_provider.py` | L32 |
| __call__ | 执行获取逻辑 | `agents/mcp_instruction_provider.py` | L56-93 |

---

## 5. Flow 流程体系

### 5.0 BaseLlmFlow — LLM Flow 基类

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| BaseLlmFlow(ABC) | LLM Flow 抽象基类（循环调用 LLM 直到最终响应） | `flows/llm_flows/base_llm_flow.py` | L441 |
| request_processors | 请求处理器列表 | `flows/llm_flows/base_llm_flow.py` | L448 |
| response_processors | 响应处理器列表 | `flows/llm_flows/base_llm_flow.py` | L449 |
| run_live | Live API 模式运行（音频流） | `flows/llm_flows/base_llm_flow.py` | L454-603 |
| run_async | 异步运行主入口 | `flows/llm_flows/base_llm_flow.py` | L745-759 |
| _run_one_step_async | 单步异步执行（LLM 调用 + 工具执行循环） | `flows/llm_flows/base_llm_flow.py` | L760-844 |
| _preprocess_async | 前置处理（应用 request processors） | `flows/llm_flows/base_llm_flow.py` | L845-876 |
| _postprocess_async | 后置处理（应用 response processors） | `flows/llm_flows/base_llm_flow.py` | L877-934 |
| _postprocess_live | Live 模式后置处理 | `flows/llm_flows/base_llm_flow.py` | L935-1033 |
| _postprocess_run_processors_async | 运行 response processors | `flows/llm_flows/base_llm_flow.py` | L1034-1043 |
| _postprocess_handle_function_calls_async | 处理函数调用（工具执行） | `flows/llm_flows/base_llm_flow.py` | L1044-1087 |
| _get_agent_to_run | 获取要运行的 Agent | `flows/llm_flows/base_llm_flow.py` | L1088-1096 |
| _call_llm_async | 异步调用 LLM（含 tracing） | `flows/llm_flows/base_llm_flow.py` | L1097-1188 |
| _finalize_model_response_event | 完成模型响应事件 | `flows/llm_flows/base_llm_flow.py` | L1189-1198 |
| _resolve_toolset_auth | 解析 Toolset 认证 | `flows/llm_flows/base_llm_flow.py` | L1199-1209 |
| _handle_before_model_callback | 模型前回调 | `flows/llm_flows/base_llm_flow.py` | L1210-1219 |
| _handle_after_model_callback | 模型后回调 | `flows/llm_flows/base_llm_flow.py` | L1220-1229 |
| _run_and_handle_error | 运行并处理错误（含重试） | `flows/llm_flows/base_llm_flow.py` | L1230-1247 |
| __get_llm | 获取 LLM 实例 | `flows/llm_flows/base_llm_flow.py` | L1284-1291 |

### 5.1 SingleFlow — 基础 LLM Flow

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| SingleFlow(BaseLlmFlow) | 基础 LLM 流程 + 处理器链 | `flows/llm_flows/single_flow.py` | L78 |
| _create_request_processors | 构建 request 处理器链 | `flows/llm_flows/single_flow.py` | L38-67 |
| _create_response_processors | 构建 response 处理器链 | `flows/llm_flows/single_flow.py` | L70-75 |

**Request Processors（按顺序）：**
basic → auth → request_confirmation → instructions → identity → compaction → contents → context_cache → interactions → nl_planning → code_execution → output_schema

**Response Processors：**
nl_planning → code_execution

### 5.4 LLM Processor 索引

| Processor 类 | 说明 | 路径 | 行号 |
|------|------|------|------|
| BaseLlmRequestProcessor(ABC) | 请求处理器基类 | `flows/llm_flows/_base_llm_processor.py` | L32 |
| BaseLlmResponseProcessor(ABC) | 响应处理器基类 | `flows/llm_flows/_base_llm_processor.py` | L44 |
| _BasicLlmRequestProcessor | 基础请求处理（tools 追加） | `flows/llm_flows/basic.py` | L90 |
| _InstructionsLlmRequestProcessor | 指令注入 | `flows/llm_flows/instructions.py` | L122 |
| _IdentityLlmRequestProcessor | 身份信息注入 | `flows/llm_flows/identity.py` | L29 |
| _ContentLlmRequestProcessor | 内容（历史消息）追加 | `flows/llm_flows/contents.py` | L37 |
| _AgentTransferLlmRequestProcessor | Agent 转移工具注入 | `flows/llm_flows/agent_transfer.py` | L37 |
| _RequestConfirmationLlmRequestProcessor | 工具确认请求处理 | `flows/llm_flows/request_confirmation.py` | L40 |
| CompactionRequestProcessor | 上下文压缩处理 | `flows/llm_flows/compaction.py` | L32 |
| ContextCacheRequestProcessor | 上下文缓存处理 | `flows/llm_flows/context_cache_processor.py` | L35 |
| InteractionsRequestProcessor | 交互记录处理 | `flows/llm_flows/interactions_processor.py` | L32 |
| _NlPlanningRequestProcessor | NL 规划请求处理 | `flows/llm_flows/_nl_planning.py` | L39 |
| _NlPlanningResponseProcessor | NL 规划响应处理 | `flows/llm_flows/_nl_planning.py` | L69 |
| _CodeExecutionRequestProcessor | 代码执行请求处理 | `flows/llm_flows/_code_execution.py` | L116 |
| _CodeExecutionResponseProcessor | 代码执行响应处理 | `flows/llm_flows/_code_execution.py` | L150 |
| _OutputSchemaRequestProcessor | 输出 schema 处理 | `flows/llm_flows/_output_schema_processor.py` | L32 |
| AudioCacheManager | 音频缓存管理 | `flows/llm_flows/audio_cache_manager.py` | L32 |
| AudioTranscriber | 音频转录 | `flows/llm_flows/audio_transcriber.py` | L25 |
| TranscriptionManager | 转录管理 | `flows/llm_flows/transcription_manager.py` | L31 |

### 5.2 AutoFlow — 自动 Agent 转移 Flow

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| AutoFlow(SingleFlow) | 在 SingleFlow 基础上添加 Agent Transfer | `flows/llm_flows/auto_flow.py` | L23 |
| transfer 方向 | parent→sub, sub→parent, sub→peer | `flows/llm_flows/auto_flow.py` | L27-36 |

### 5.3 Agent Transfer 处理器

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| _AgentTransferLlmRequestProcessor | 添加 TransferToAgentTool 到请求 | `flows/llm_flows/agent_transfer.py` | L37-69 |
| _build_transfer_instruction_body | 构建转移指令文本 | `flows/llm_flows/agent_transfer.py` | L86-126 |
| _build_transfer_instructions | 添加父级特定指令 | `flows/llm_flows/agent_transfer.py` | L129-153 |
| _get_transfer_targets | 计算 Agent 树中可转移目标 | `flows/llm_flows/agent_transfer.py` | L156-175 |

---

## 6. Model 模型体系

### 6.0 BaseLlm — 模型基类

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| BaseLlm(BaseModel) | 所有 LLM 的抽象基类 | `models/base_llm.py` | L32 |
| model | 模型名称（如 gemini-2.5-flash） | `models/base_llm.py` | L41-42 |
| supported_models | 返回支持的模型列表（regex） | `models/base_llm.py` | L44-47 |
| generate_content_async | 抽象方法：生成内容（streaming/non-streaming） | `models/base_llm.py` | L49-151 |
| _maybe_append_user_content | 可能追加用户内容 | `models/base_llm.py` | L152-193 |
| connect | 建立 Live API 连接 | `models/base_llm.py` | L194-205 |

### 6.1 LlmRequest / LlmResponse — 请求与响应

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| LlmRequest(BaseModel) | LLM 请求模型 | `models/llm_request.py` | L49 |
| append_instructions | 追加指令 | `models/llm_request.py` | L102 |
| append_tools | 追加工具列表 | `models/llm_request.py` | L244 |
| set_output_schema | 设置输出 schema | `models/llm_request.py` | L276 |
| LlmResponse(BaseModel) | LLM 响应模型 | `models/llm_response.py` | L28 |
| create | 创建响应 | `models/llm_response.py` | L146 |

### 6.2 LLMRegistry — 模型注册表

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| LLMRegistry | 模型注册表（按 regex 匹配模型名） | `models/registry.py` | L38 |
| new_llm | 创建 LLM 实例 | `models/registry.py` | L42 |
| _register | 注册模型类（装饰器内部） | `models/registry.py` | L55 |
| register | 注册模型类（公开装饰器） | `models/registry.py` | L74 |
| resolve | 解析模型类 | `models/registry.py` | L86 |

### 6.3 其他 LLM 实现

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| Gemini(BaseLlm) | Gemini 原生 LLM | `models/google_llm.py` | L83 |
| AnthropicLlm(BaseLlm) | Anthropic Claude LLM | `models/anthropic_llm.py` | L269 |
| Claude(AnthropicLlm) | Claude 模型快捷方式 | `models/anthropic_llm.py` | L324 |
| Gemma(Gemini) | Gemma 模型（含函数调用 mixin） | `models/gemma_llm.py` | L163 |
| ApigeeLlm(Gemini) | Apigee 代理 LLM | `models/apigee_llm.py` | L64 |
| GeminiLlmConnection | Gemini Live API 连接 | `models/gemini_llm_connection.py` | L38 |
| GeminiContextCacheManager | Gemini 上下文缓存管理 | `models/gemini_context_cache_manager.py` | L40 |

### 6.4 LiteLlm — 多提供商 LLM 封装

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| LiteLlm(BaseLlm) | litellm 封装，支持多提供商 | `models/lite_llm.py` | L1877 |
| supported_models | 支持的模型列表（openai, azure, anthropic 等） | `models/lite_llm.py` | L2151-2197 |
| generate_content_async | 主生成方法（streaming + non-streaming） | `models/lite_llm.py` | L1927-2149 |
| LiteLLMClient | 可测试的 litellm 封装 | `models/lite_llm.py` | L425-474 |
| _content_to_message_param | Content → litellm 消息参数转换 | `models/lite_llm.py` | L596-712 |
| _get_content | 从 litellm 响应提取 Content | `models/lite_llm.py` | L776-928 |
| _ensure_tool_results | 确保工具结果配对 | `models/lite_llm.py` | L715-773 |
| _to_litellm_response_format | 结构化输出格式转换 | `models/lite_llm.py` | L1542-1616 |
| _enforce_strict_openai_schema | OpenAI strict 模式 schema 变换 | `models/lite_llm.py` | L1494-1539 |

---

## 7. Session / State / Event

### 7.0 BaseSessionService — Session 服务基类

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| GetSessionConfig | 获取 Session 的配置 | `sessions/base_session_service.py` | L29 |
| ListSessionsResponse | 列出 Session 的响应 | `sessions/base_session_service.py` | L36 |
| BaseSessionService(ABC) | Session 服务抽象基类 | `sessions/base_session_service.py` | L45 |
| create_session | 创建会话 | `sessions/base_session_service.py` | L52-73 |
| get_session | 获取会话 | `sessions/base_session_service.py` | L74-84 |
| list_sessions | 列出会话 | `sessions/base_session_service.py` | L85-99 |
| delete_session | 删除会话 | `sessions/base_session_service.py` | L100-104 |
| append_event | 追加事件到会话 | `sessions/base_session_service.py` | L105-113 |
| _trim_temp_delta_state | 清理临时 delta 状态 | `sessions/base_session_service.py` | L114-125 |
| _update_session_state | 更新会话状态 | `sessions/base_session_service.py` | L126-133 |

**Session 服务实现：**
- `InMemorySessionService` — 内存实现 | `sessions/in_memory_session_service.py`
- `DatabaseSessionService` — 数据库实现 | `sessions/database_session_service.py`
- `SqliteSessionService` — SQLite 实现 | `sessions/sqlite_session_service.py`
- `VertexAiSessionService` — Vertex AI 实现 | `sessions/vertex_ai_session_service.py`

### 7.1 State — Delta 感知状态

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| State 类 | delta 感知读写状态 | `sessions/state.py` | L82 |
| APP_PREFIX / USER_PREFIX / TEMP_PREFIX | "app:" / "user:" / "temp:" | `sessions/state.py` | L23-25 |
| __init__ | (value, delta) 初始化 | `sessions/state.py` | L27-34 |
| __getitem__ | 先查 delta，再查 value | `sessions/state.py` | L36-40 |
| __setitem__ | 同时写 _value 和 _delta | `sessions/state.py` | L42-47 |
| has_delta() | 检查是否有增量变更 | `sessions/state.py` | L61-63 |
| update() | 批量更新 | `sessions/state.py` | L71-74 |
| to_dict() | 导出为 dict | `sessions/state.py` | L76-81 |

### 7.2 Session — 会话数据模型

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| Session(BaseModel) | 会话数据模型 | `sessions/session.py` | L27 |
| 字段 | id, app_name, user_id, state, events, last_update_time | `sessions/session.py` | L27-51 |

### 7.3 Event — 事件

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| Event(LlmResponse) | 对话事件 | `events/event.py` | L30 |
| invocation_id | 调用 ID | `events/event.py` | L46 |
| author | 事件作者 | `events/event.py` | L48 |
| actions | EventActions | `events/event.py` | L51 |
| long_running_tool_ids | 长运行工具 ID | `events/event.py` | L54 |
| branch | 分支标识 | `events/event.py` | L59 |
| is_final_response() | 判断是否为最终响应 | `events/event.py` | L82-97 |
| get_function_calls() | 获取函数调用 | `events/event.py` | L99-106 |
| get_function_responses() | 获取函数响应 | `events/event.py` | L108-115 |

### 7.4 EventActions — 事件动作

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| EventActions(BaseModel) | 事件携带的动作 | `events/event_actions.py` | L50 |
| skip_summarization | 跳过摘要 | `events/event_actions.py` | L60-64 |
| state_delta | 状态增量（dict[str, object]） | `events/event_actions.py` | L66-67 |
| artifact_delta | Artifact 增量（filename→version） | `events/event_actions.py` | L69-71 |
| transfer_to_agent | 转移到指定 Agent | `events/event_actions.py` | L73-74 |
| escalate | 上报（LoopAgent 终止信号） | `events/event_actions.py` | L76-77 |
| requested_auth_configs | 请求的认证配置 | `events/event_actions.py` | L79-89 |
| requested_tool_confirmations | 请求的工具确认 | `events/event_actions.py` | L91-95 |
| compaction | 压缩标记 | `events/event_actions.py` | L97-98 |
| end_of_agent | Agent 结束标记 | `events/event_actions.py` | L100-103 |
| agent_state | Agent 状态快照 | `events/event_actions.py` | L105-107 |
| rewind_before_invocation_id | 回退到指定 invocation 之前 | `events/event_actions.py` | L109-110 |

---

## 8. Runner 运行器

> Runner 是 ADK 的顶层执行引擎，负责协调 Agent、Session、Event 的完整生命周期。
> 单文件模块 `runners.py`（1558 行），不是目录。

### 8.1 Runner — 顶层运行器

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| Runner 类 | 顶层运行器 | `runners.py` | L101 |
| app_name | 应用名称 | `runners.py` | L120 |
| agent | 根 Agent | `runners.py` | L122-123 |
| artifact_service | Artifact 存储服务 | `runners.py` | L124-125 |
| session_service | Session 服务（必须） | `runners.py` | L128-129 |
| memory_service | 记忆服务 | `runners.py` | L130-131 |
| credential_service | 凭证服务 | `runners.py` | L132-133 |
| context_cache_config | 上下文缓存配置 | `runners.py` | L134-135 |
| plugin_manager | 插件管理器 | `runners.py` | L126-127 |
| __init__ | 初始化（app 或 app_name+agent） | `runners.py` | L139-207 |
| _validate_runner_params | 验证参数合法性 | `runners.py` | L209-269 |
| _infer_agent_origin | 推断 Agent 来源 | `runners.py` | L270-321 |
| _enforce_app_name_alignment | 强制 app_name 对齐 | `runners.py` | L322-343 |
| run | 同步运行（本地测试用） | `runners.py` | L388-451 |
| run_async | 异步运行（主入口） | `runners.py` | L453-567 |
| rewind_async | 异步回退 | `runners.py` | L568-614 |
| _compute_state_delta_for_rewind | 计算回退的 state delta | `runners.py` | L615-648 |
| _compute_artifact_delta_for_rewind | 计算回退的 artifact delta | `runners.py` | L649-704 |
| _should_append_event | 判断是否追加事件到 session | `runners.py` | L705-722 |
| _exec_with_plugin | 插件包装执行 | `runners.py` | L723-855 |
| _append_new_message_to_session | 追加新消息到 session | `runners.py` | L856-925 |
| run_live | 实时模式运行（音频流） | `runners.py` | L926-1034 |
| _find_agent_to_run | 查找要运行的 Agent | `runners.py` | L1035-1088 |
| _is_transferable_across_agent_tree | 检查 Agent 是否可在树中转移 | `runners.py` | L1089-1110 |
| run_debug | 调试模式运行 | `runners.py` | L1111-1212 |
| _setup_context_for_new_invocation | 新调用上下文设置 | `runners.py` | L1213-1250 |
| _setup_context_for_resumed_invocation | 恢复调用上下文设置 | `runners.py` | L1251-1313 |
| _find_user_message_for_invocation | 查找调用的用户消息 | `runners.py` | L1314-1328 |
| _new_invocation_context | 创建新调用上下文 | `runners.py` | L1329-1381 |
| _new_invocation_context_for_live | 创建实时模式上下文 | `runners.py` | L1382-1407 |
| _handle_new_message | 处理新消息 | `runners.py` | L1408-1447 |
| _collect_toolset | 收集 Agent 的所有 Toolset | `runners.py` | L1448-1457 |
| _cleanup_toolsets | 清理关闭 Toolset | `runners.py` | L1458-1487 |
| close | 关闭 Runner（清理 Toolset + Plugin） | `runners.py` | L1488-1498 |
| __aenter__ / __aexit__ | 异步上下文管理器 | `runners.py` | L1505-1512 |

### 8.2 InMemoryRunner — 内存运行器

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| InMemoryRunner(Runner) | 内存版 Runner，用于测试开发 | `runners.py` | L1515 |
| __init__ | 默认 InMemorySessionService + InMemoryArtifactService | `runners.py` | L1528-1558 |

---

## 9. Auth 认证体系

### 9.1 AuthCredential — 认证凭证

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| AuthCredential(BaseModelWithConfig) | 统一凭证模型 | `auth/auth_credential.py` | L214 |
| HttpCredentials | HTTP 凭证（token, username, password） | `auth/auth_credential.py` | L40 |
| HttpAuth | HTTP 认证（scheme + credentials） | `auth/auth_credential.py` | L56 |
| OAuth2Auth | OAuth2 认证（access_token, refresh_token 等） | `auth/auth_credential.py` | L68 |
| ServiceAccountCredential | 服务账号凭证 | `auth/auth_credential.py` | L97 |
| ServiceAccount | 服务账号（client_email, private_key 等） | `auth/auth_credential.py` | L148 |
| AuthCredentialTypes | 凭证类型枚举 | `auth/auth_credential.py` | L190 |

### 9.2 AuthConfig — 认证配置

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| AuthConfig(BaseModelWithConfig) | 认证配置（auth_scheme + raw/exchanged credential） | `auth/auth_tool.py` | L51 |
| AuthToolArguments | 工具参数配置 | `auth/auth_tool.py` | L138 |

### 9.3 Auth Schemes — 认证方案

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| OpenIdConnectWithConfig | OIDC 方案 | `auth/auth_schemes.py` | L32 |
| OAuthGrantType | OAuth 授权类型枚举 | `auth/auth_schemes.py` | L49 |
| ExtendedOAuth2 | 扩展 OAuth2 方案 | `auth/auth_schemes.py` | L76 |

### 9.4 其他 Auth 组件

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| CredentialManager | 凭证管理器（交换 + 刷新） | `auth/credential_manager.py` | L41 |
| AuthHandler | 认证处理器 | `auth/auth_handler.py` | L38 |
| _AuthLlmRequestProcessor | 认证 LLM 请求处理器 | `auth/auth_preprocessor.py` | L38 |
| BaseCredentialService | 凭证服务基类 | `auth/credential_service/base_credential_service.py` | L28 |
| InMemoryCredentialService | 内存凭证服务 | `auth/credential_service/in_memory_credential_service.py` | L29 |
| SessionStateCredentialService | Session 状态凭证服务 | `auth/credential_service/session_state_credential_service.py` | L29 |
| BaseCredentialExchanger | 凭证交换器基类 | `auth/exchanger/base_credential_exchanger.py` | L38 |
| OAuth2CredentialExchanger | OAuth2 凭证交换器 | `auth/exchanger/oauth2_credential_exchanger.py` | L47 |
| BaseCredentialRefresher | 凭证刷新器基类 | `auth/refresher/base_credential_refresher.py` | L32 |
| OAuth2CredentialRefresher | OAuth2 凭证刷新器 | `auth/refresher/oauth2_credential_refresher.py` | L45 |

---

## 10. Artifact / Memory / 其他

### 10.1 Artifact 服务

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| ArtifactVersion | Artifact 版本模型 | `artifacts/base_artifact_service.py` | L29 |
| BaseArtifactService(ABC) | Artifact 存储抽象基类 | `artifacts/base_artifact_service.py` | L63 |
| save_artifact | 保存 artifact | `artifacts/base_artifact_service.py` | L67-99 |
| load_artifact | 加载 artifact | `artifacts/base_artifact_service.py` | L100-126 |
| list_artifact_keys | 列出 artifact 键名 | `artifacts/base_artifact_service.py` | L127-144 |
| delete_artifact | 删除 artifact | `artifacts/base_artifact_service.py` | L145-163 |
| list_versions | 列出版本 | `artifacts/base_artifact_service.py` | L164-185 |

**Artifact 服务实现：**
- `InMemoryArtifactService` — 内存实现 | `artifacts/in_memory_artifact_service.py`
- `GcsArtifactService` — GCS 实现 | `artifacts/gcs_artifact_service.py`
- `FileArtifactService` — 本地文件实现 | `artifacts/file_artifact_service.py`

### 10.2 Memory 服务

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| SearchMemoryResponse | 搜索记忆响应 | `memory/base_memory_service.py` | L34 |
| BaseMemoryService(ABC) | 记忆服务抽象基类 | `memory/base_memory_service.py` | L44 |
| add_session_to_memory | 将会话加入记忆 | `memory/base_memory_service.py` | L52-63 |
| add_events_to_memory | 将事件加入记忆 | `memory/base_memory_service.py` | L64-96 |
| add_memory | 添加记忆 | `memory/base_memory_service.py` | L97-123 |
| search_memory | 搜索记忆 | `memory/base_memory_service.py` | L124- |

**Memory 服务实现：**
- `InMemoryMemoryService` — 内存实现 | `memory/in_memory_memory_service.py`
- `VertexAiMemoryBankService` — Vertex AI 实现 | `memory/vertex_ai_memory_bank_service.py`
- `VertexAiRagMemoryService` — Vertex AI RAG 实现 | `memory/vertex_ai_rag_memory_service.py`

### 10.3 重要内置工具

| 特性 | 说明 | 路径 | 行号 |
|------|------|------|------|
| AgentTool(BaseTool) | Agent 作为 Tool（嵌套调用） | `tools/agent_tool.py` | L92 |
| AgentToolConfig | Agent Tool 配置 | `tools/agent_tool.py` | L297 |
| TransferToAgentTool(FunctionTool) | Agent 转移工具 | `tools/transfer_to_agent_tool.py` | L43 |
| LoadMcpResourceTool | 加载 MCP 资源工具 | `tools/load_mcp_resource_tool.py` | — |
| LoadMemoryTool | 加载记忆工具 | `tools/load_memory_tool.py` | — |
| LoadArtifactsTool | 加载 Artifact 工具 | `tools/load_artifacts_tool.py` | — |
| GoogleSearchTool | Google 搜索工具 | `tools/google_search_tool.py` | — |
| LangchainTool | LangChain 工具适配 | `tools/langchain_tool.py` | — |
| ToolboxToolset | Google Toolbox 工具集 | `tools/toolbox_toolset.py` | — |
| SkillToolset | 技能工具集 | `tools/skill_toolset.py` | — |
| LongRunningTool | 长运行工具 | `tools/long_running_tool.py` | — |
| AuthenticatedFunctionTool | 认证函数工具 | `tools/authenticated_function_tool.py` | — |
| BaseAuthenticatedTool | 认证工具基类 | `tools/base_authenticated_tool.py` | — |

---

## 关键设计模式速查

### Delta-Aware State（增量感知状态）
State 类同时维护 `_value`（完整状态）和 `_delta`（增量变更）。读取时先查 delta 再查 value；写入时同时更新两者。ADK 通过 `state_delta` 在 EventActions 中传播变更。

### Processor Chain（处理器链）
SingleFlow/AutoFlow 使用 request processors 和 response processors 链式处理 LLM 请求/响应。每个 processor 可修改 LlmRequest 或处理 LlmResponse。

### Session Pooling by Headers（会话池化）
MCPSessionManager 根据 headers 的 MD5 hash 生成 session key，实现相同认证头的会话复用。

### Branch Isolation（分支隔离）
ParallelAgent 为每个子 Agent 创建独立的 branch 上下文，避免状态互相污染。

### Two-Phase Lazy Loading（两阶段懒加载）
SkillManager 在启动时只扫描 SKILL.md 的 YAML frontmatter，实际执行时才加载完整内容和 tools.py。

### output_key 自动保存
LlmAgent 的 `output_key` 机制：Agent 的最终文本输出自动写入 `state[output_key]`，无需手动保存。

---

_文档生成时间：2026-04-22_
_源码版本：google-adk (anaconda3 site-packages)_
