"""
ADK Dynamic Skills Agent - 不依赖服务端 Function Calling 的版本

核心特性：
1. 不依赖服务端的 function calling 能力
2. 手动实现 ReAct 循环：解析 LLM 输出 → 执行工具 → 返回结果
3. 复用现有的动态技能加载机制
4. 支持流式输出和 Web API

启动 web服务，在 localhost:8000 打开测试页面
python -m skills.adk_agent.main_web_start_without_function_calling
"""

import asyncio
import os
import sys
import json
import re
import inspect
from typing import Dict, List, Optional, Any, Callable

# 将当前目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.manager import SkillManager
from core.executor import execute_python_code
from core.logger import AgentLogger, logger
from config import AgentConfig
from prompt_without_function_calling_config import build_system_prompt
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

# 全局实例
tool_registry: Dict[str, Callable] = {}  # 工具注册表：工具名 -> 函数对象
sm: Optional[SkillManager] = None
config = AgentConfig()
conversation_history: List[Dict[str, str]] = []  # 对话历史

# 会话标识常量
DEFAULT_APP_NAME = "dynamic_expert"
DEFAULT_USER_ID = "user_001"
DEFAULT_SESSION_ID = "session_001"


def setup_env():
    """准备测试环境"""
    errors = config.validate()
    if errors:
        for err in errors:
            logger.warn(err)
    
    try:
        import pandas as pd
        pd.DataFrame({
            'date': ['2025-01-01', '2025-01-02', '2025-01-03'],
            'sales_val': [100, 150, 120]
        }).to_csv('data.csv', index=False)
        logger.info("测试数据文件 data.csv 已创建")
    except ImportError:
        logger.debug("pandas 未安装，跳过测试数据创建")


async def skill_load(skill_id: str) -> str:
    """
    动态网关：按需加载 Instructions 并注册工具
    
    这是 Agent 唯一初始拥有的工具。当 Agent 需要某个技能时，
    会调用此函数来加载完整的 Instructions 并注册对应的工具。
    
    Args:
        skill_id: 技能标识符，如 "data_analyst", "codebase_search"
        
    Returns:
        技能的完整 Instructions 内容，包含执行指令和示例
    """
    global sm, tool_registry
    
    print(f"[系统] 激活技能: {skill_id}")
    logger.info(f"激活技能: {skill_id}")

    # 验证技能是否存在
    if not sm.skill_exists(skill_id):
        available = sm.list_skills()
        return f"[ERROR] 技能 '{skill_id}' 不存在。可用技能: {available}"

    # 动态加载技能的工具模块
    tools_loaded = _load_skill_tools(skill_id)
    if tools_loaded:
        logger.skill_loaded(skill_id, tools_loaded)

    # 返回完整的 Instructions
    sop = sm.load_full_sop(skill_id)
    return f"""[OK] 技能 '{skill_id}' 已加载，以下是执行指令：

{sop}

---
[注意] 请严格按照上述 Instructions 执行任务。如需调用工具，请使用 JSON 格式输出工具调用。
"""


async def _local_smart_compact(summary: str) -> str:
    """
    智能压缩上下文：清空历史并保留摘要 (Local Shim)
    """
    return "[OK] 已重置历史 (Hard Reset)。\n[状态] Agent 已重置为轻量化状态"

async def _local_get_compression_status() -> str:
    """
    获取当前压缩状态建议 (Local Shim)
    """
    return f"当前对话轮数: {len(conversation_history)}。建议压缩。"


def _load_skill_tools(skill_id: str) -> List[Callable]:
    """从技能目录加载 tools.py 并注册工具"""
    global tool_registry, config
    
    # 特殊处理：compactor 技能使用本地垫片 (Shim)
    if skill_id == "compactor":
        logger.info("加载 compactor 技能的本地垫片 (Local Shim)")
        tools = [_local_smart_compact, _local_get_compression_status]
        for tool in tools:
            tool_name = tool.__name__
            if tool_name.startswith("_local_"):
                tool_name = tool_name.replace("_local_", "")
                tool.__name__ = tool_name # 重命名以匹配预期
            
            if tool_name not in tool_registry:
                tool_registry[tool_name] = tool
                print(f"[工具注册] {tool_name} (Local Shim)")
        return tools

    import importlib.util
    
    tools_path = os.path.join(config.skills_path, skill_id, "tools.py")
    
    if not os.path.exists(tools_path):
        # 如果没有 tools.py，回退到通用执行器
        if skill_id == "data_analyst" and "execute_python_code" not in tool_registry:
            tool_registry["execute_python_code"] = execute_python_code
            return [execute_python_code]
        return []
    
    try:
        # 动态加载模块
        spec = importlib.util.spec_from_file_location(f"skill_{skill_id}", tools_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 获取工具函数
        tools = []
        if hasattr(module, 'get_tools'):
            try:
                tools = module.get_tools()
            except TypeError:
                tools = module.get_tools()
        elif hasattr(module, 'TOOLS'):
            tools = list(module.TOOLS.values())
        else:
            # 查找所有可调用对象（排除内置函数）
            tools = [
                getattr(module, name) for name in dir(module)
                if callable(getattr(module, name)) 
                and not name.startswith('_')
                and hasattr(getattr(module, name), '__module__')
            ]
        
        # 注册工具
        loaded = []
        for tool in tools:
            tool_name = tool.__name__ if hasattr(tool, '__name__') else str(tool)
            if tool_name not in tool_registry:
                tool_registry[tool_name] = tool
                loaded.append(tool)
                print(f"[工具注册] {tool_name}")
        
        return loaded
    except Exception as e:
        logger.error(f"加载工具模块失败: {skill_id}", error=str(e))
        return []


def build_enhanced_system_prompt(skill_manifests: str) -> str:
    """构建增强的系统提示词，要求 LLM 以 JSON 格式输出工具调用"""
    base_prompt = build_system_prompt(config, skill_manifests)
    
    # 获取当前已注册的工具列表
    tool_list = "\n".join([f"- {name}" for name in sorted(tool_registry.keys())])
    if not tool_list:
        tool_list = "- skill_load (用于加载技能)"
    
    tool_calling_instruction = f"""

## 可用工具列表

当前已注册的工具：
{tool_list}

## 工具调用格式（重要）

当你需要调用工具时，请使用以下 JSON 格式输出：

```json
{{
  "action": "tool_call",
  "tool_name": "工具名称",
  "arguments": {{
    "参数1": "值1",
    "参数2": "值2"
  }}
}}
```

如果不需要调用工具，直接输出文本回复即可。

**示例**：
- 需要调用工具时：
```json
{{
  "action": "tool_call",
  "tool_name": "skill_load",
  "arguments": {{
    "skill_id": "data_analyst"
  }}
}}
```

- 不需要工具时，直接输出：
```
根据分析，数据平均值为 125。
```

**重要提示**：
1. 工具调用必须严格按照 JSON 格式，包含 action、tool_name 和 arguments 字段
2. 如果工具调用失败，请分析错误信息并重试或选择其他工具
3. 可以连续调用多个工具来完成复杂任务
"""
    
    return base_prompt + tool_calling_instruction


def parse_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 输出中解析工具调用
    
    Args:
        text: LLM 的文本输出
        
    Returns:
        工具调用字典，格式：{"tool_name": str, "arguments": dict}，如果未找到则返回 None
    """
    # 尝试提取 JSON 代码块
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    match = re.search(json_pattern, text, re.DOTALL)
    
    if match:
        json_str = match.group(1)
    else:
        # 尝试直接查找 JSON 对象
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            json_str = text[start:end+1]
        else:
            return None
    
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict) and parsed.get("action") == "tool_call":
            return {
                "tool_name": parsed.get("tool_name"),
                "arguments": parsed.get("arguments", {})
            }
    except json.JSONDecodeError:
        pass
    
    return None


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    执行工具调用
    
    Args:
        tool_name: 工具名称
        arguments: 工具参数
        
    Returns:
        工具执行结果
    """
    global tool_registry
    
    if tool_name not in tool_registry:
        return f"[ERROR] 工具 '{tool_name}' 未注册。可用工具: {list(tool_registry.keys())}"
    
    tool_func = tool_registry[tool_name]
    
    try:
        # 检查工具函数签名
        sig = inspect.signature(tool_func)
        params = sig.parameters
        
        # 准备参数
        kwargs = {}
        for param_name, param in params.items():
            if param_name in arguments:
                kwargs[param_name] = arguments[param_name]
            elif param.default != inspect.Parameter.empty:
                # 使用默认值
                pass
            else:
                # 必需参数缺失
                return f"[ERROR] 缺少必需参数: {param_name}"
        
        # 执行工具
        if asyncio.iscoroutinefunction(tool_func):
            result = await tool_func(**kwargs)
        else:
            result = tool_func(**kwargs)
        
        # 确保返回字符串
        if not isinstance(result, str):
            result = str(result)
        
        return result
    except Exception as e:
        error_msg = f"[ERROR] 工具执行失败: {type(e).__name__}: {str(e)}"
        logger.error(f"工具 {tool_name} 执行出错", error=str(e))
        return error_msg


async def call_llm(messages: List[Dict[str, str]]) -> str:
    """
    调用 LLM 模型（使用 OpenAI 兼容 API）
    
    Args:
        messages: 消息列表，格式：[{"role": "user", "content": "..."}, ...]
        
    Returns:
        LLM 的文本回复
    """
    try:
        import httpx
        
        # 构建 OpenAI 兼容的请求
        openai_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            # 将 system 角色映射为 user（某些 API 不支持 system）
            if role == "system":
                role = "user"
            openai_messages.append({
                "role": role,
                "content": msg.get("content", "")
            })
        
        # 调用 OpenAI 兼容 API
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{config.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": config.model.replace("openai/", ""),  # 移除 openai/ 前缀
                    "messages": openai_messages,
                    "temperature": 0.7,
                    **config.extra_body  # 包含 enable_thinking 等参数
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    return content
                else:
                    return "[ERROR] LLM 返回格式异常"
            else:
                error_msg = f"[ERROR] LLM API 调用失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return error_msg
                
    except Exception as e:
        error_msg = f"[ERROR] LLM 调用失败: {str(e)}"
        logger.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg


async def run_agent_react(task: str):
    """
    运行 Agent 的 ReAct 循环
    
    Args:
        task: 用户任务
        
    Yields:
        流式输出块
    """
    global sm, conversation_history, tool_registry
    
    # 初始化
    if sm is None:
        sm = SkillManager(base_path=config.skills_path)
        skill_manifests = sm.get_discovery_manifests()
        print(f"[系统] 发现 {len(sm.list_skills())} 个技能")
        
        # 注册 skill_load 工具
        tool_registry["skill_load"] = skill_load
        
        # 构建系统提示词（需要在注册 skill_load 之后）
        system_prompt = build_enhanced_system_prompt(skill_manifests)
        conversation_history = [
            {"role": "system", "content": system_prompt}
        ]
    
    # 添加用户消息
    conversation_history.append({"role": "user", "content": task})
    yield {"type": "text", "content": f"[任务] {task}\n"}
    
    max_iterations = 15  # 最大迭代次数
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # 调用 LLM
        yield {"type": "text", "content": f"\n[思考中... (第 {iteration} 轮)]\n"}
        llm_response = await call_llm(conversation_history)
        
        if not llm_response or llm_response.startswith("[ERROR]"):
            yield {"type": "text", "content": f"\n{llm_response}\n"}
            break
        
        # 检查是否包含工具调用
        tool_call = parse_tool_call(llm_response)
        
        if tool_call:
            # 执行工具调用
            tool_name = tool_call["tool_name"]
            arguments = tool_call["arguments"]
            
            yield {"type": "tool_call", "content": f"\n[工具调用] {tool_name}({json.dumps(arguments, ensure_ascii=False)})\n"}
            
            tool_result = await execute_tool(tool_name, arguments)
            
            yield {"type": "tool_result", "content": f"[工具结果] {tool_result}\n"}
            
            # 特殊处理：如果是 smart_compact 且执行成功，则清空本地历史
            if tool_name == "smart_compact" and ("[OK] 已重置历史" in tool_result or "[状态] Agent 已重置为轻量化状态" in tool_result):
                logger.info("检测到压缩操作，正在重置本地对话历史...")
                conversation_history.clear()
                
                # 从参数中获取摘要
                summary = arguments.get("summary", "（未提供摘要）")
                
                # 重建历史，注入摘要
                conversation_history.append({
                    "role": "user",
                    "content": f"[系统通知] 历史对话已压缩。以下是上下文摘要：\n\n{summary}\n\n请基于此摘要继续服务。"
                })
                conversation_history.append({
                    "role": "assistant",
                    "content": "明白，已接收上下文摘要。我已准备好继续处理新任务。"
                })
                
                yield {"type": "text", "content": f"\n[系统] 本地历史已重置，摘要已注入。\n"}
                continue
            
            # 将 LLM 回复和工具结果添加到对话历史
            # 注意：保留完整的 LLM 回复，以便后续参考
            conversation_history.append({
                "role": "assistant",
                "content": llm_response
            })
            conversation_history.append({
                "role": "user",
                "content": f"[工具执行结果] {tool_result}\n请根据工具执行结果继续处理任务。"
            })
        else:
            # 没有工具调用，直接返回回复
            conversation_history.append({"role": "assistant", "content": llm_response})
            yield {"type": "text", "content": f"\n[最终回复]\n{llm_response}\n"}
            break
    
    if iteration >= max_iterations:
        yield {"type": "text", "content": f"\n[警告] 达到最大迭代次数 ({max_iterations})，停止执行\n"}


# FastAPI App Setup
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    async def generate():
        yield json.dumps({"app_name": DEFAULT_APP_NAME}) + "\n"
        
        async for chunk in run_agent_react(request.message):
            yield json.dumps({"chunk": chunk}) + "\n"
    
    return StreamingResponse(generate(), media_type="application/x-ndjson")

@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

def start_web_server():
    print("Starting web server at http://localhost:8000")
    setup_env()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    start_web_server()

