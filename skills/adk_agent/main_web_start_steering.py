"""
ADK Dynamic Skills Agent - 主入口 (多租户并发安全版)

修正点：
1. Session 识别升级：使用 (app_name, user_id, session_id) 三元组。
2. claudecode风格的steering实时文本打断增强：在流式输出循环中增加强制检查。
3. AOP 拦截：使用 before_model/tool callback。

python -m skills.adk_agent.main_web_start_steering
"""

import asyncio
import os
import sys
import json
from contextvars import ContextVar
from typing import Dict, Tuple, Optional, Any

# 将当前目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.manager import SkillManager
from core.executor import execute_python_code
from core.logger import AgentLogger, logger
from config import AgentConfig, build_system_prompt
from google.genai import types
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

# ==========================================
# [AOP 基础设施] 多维度会话中断控制
# ==========================================

# 1. 定义三元组类型别名
# SessionKey = (app_name, user_id, session_id)
SessionKey = Tuple[str, str, str]

# 2. 定义中断异常
class UserInterruption(Exception):
    """用户手动触发的中断异常"""
    pass

# 3. 会话上下文 (存储当前运行的三元组 key)
# 默认值为 None
current_session_key: ContextVar[Optional[SessionKey]] = ContextVar("current_session_key", default=None)

# 4. 全局信号队列 { (app, user, session) : Queue }
# 键现在是三元组，确保多租户隔离
interruption_queues: Dict[SessionKey, asyncio.Queue] = {}

def get_or_create_queue(app_name: str, user_id: str, session_id: str) -> asyncio.Queue:
    key = (app_name, user_id, session_id)
    if key not in interruption_queues:
        interruption_queues[key] = asyncio.Queue()
    return interruption_queues[key]

# 5. [核心切面] 中断卫士 (Guard)
def interruption_guard(*args, **kwargs):
    """
    通用拦截卫士。
    1. 被 ADK Callbacks 调用 (args/kwargs 可能不同)
    2. 被 流式循环 手动调用 (args 为 None)
    """
    # 1. 从上下文获取当前的三元组 Key
    key = current_session_key.get()
    
    # 如果当前没有上下文（比如在非 Agent 线程运行），直接放行
    if not key:
        return None

    # 2. 根据三元组查找对应的队列
    queue = interruption_queues.get(key)
    
    if queue and not queue.empty():
        try:
            # 非阻塞偷看
            signal = queue.get_nowait()
            if signal == "CANCEL":
                # 打印日志时带上身份信息
                app, user, sess = key
                print(f"🛑 [AOP拦截] 检测到中断信号! Target: {app}/{user}/{sess}")
                
                # 清空队列
                while not queue.empty(): queue.get_nowait()
                
                # === 核心动作：抛出异常 ===
                raise UserInterruption("User requested to stop operation.")
        except asyncio.QueueEmpty:
            pass
    
    return None

# ==========================================
# 业务逻辑代码
# ==========================================

# 全局实例
my_agent = None
compactor_agent = None
session_service = None
sm = None
config = AgentConfig()

# 默认常量
DEFAULT_APP_NAME = "dynamic_expert"
DEFAULT_USER_ID = "user_001"
DEFAULT_SESSION_ID = "session_001"

def setup_env():
    """准备测试环境"""
    errors = config.validate()
    if errors:
        for err in errors: logger.warn(err)
    try:
        import pandas as pd
        pd.DataFrame({
            'date': ['2025-01-01', '2025-01-02'], 'sales_val': [100, 150]
        }).to_csv('data.csv', index=False)
    except ImportError:
        pass

# 注意：这里保持纯净，不需要装饰器
async def skill_load(skill_id: str) -> str:
    """动态网关"""
    global my_agent, sm
    print(f"[系统] 激活技能: {skill_id}")
    if not sm.skill_exists(skill_id):
        return f"[ERROR] 技能 '{skill_id}' 不存在。"
    _load_skill_tools(skill_id)
    return f"""[OK] 技能 '{skill_id}' 已加载。Instructions:\n{sm.load_full_sop(skill_id)}"""

def _load_skill_tools(skill_id: str):
    """加载工具"""
    global my_agent
    import importlib.util
    tools_path = os.path.join(config.skills_path, skill_id, "tools.py")
    if not os.path.exists(tools_path): return []
    
    try:
        spec = importlib.util.spec_from_file_location(f"skill_{skill_id}", tools_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        tools = []
        if hasattr(module, 'get_tools'):
             try:
                # 注入当前上下文的三元组信息到工具中 (如果工具支持)
                app_info = {"app_name": DEFAULT_APP_NAME, "user_id": DEFAULT_USER_ID, "session_id": DEFAULT_SESSION_ID}
                tools = module.get_tools(my_agent, session_service, app_info)
             except:
                tools = module.get_tools()
        elif hasattr(module, 'TOOLS'):
            tools = list(module.TOOLS.values())
        
        loaded = []
        existing_names = {t.__name__ for t in my_agent.tools if hasattr(t, '__name__')}
        for tool in tools:
            t_name = getattr(tool, '__name__', str(tool))
            if t_name not in existing_names:
                my_agent.tools.append(tool)
                loaded.append(tool)
                existing_names.add(t_name)
        return loaded
    except Exception as e:
        logger.error(f"加载工具失败: {skill_id}", error=str(e))
        return []

def create_agent(custom_config: AgentConfig = None):
    """创建 Agent 并注入 Callbacks"""
    global my_agent, session_service, sm, config, compactor_agent
    if custom_config: config = custom_config
    
    from google.adk.agents import LlmAgent
    from google.adk.sessions import InMemorySessionService
    from google.adk.models.lite_llm import LiteLlm
    from auto_compact_agent import AutoCompactAgent

    sm = SkillManager(base_path=config.skills_path)
    session_service = InMemorySessionService()
    system_prompt = build_system_prompt(config, sm.get_discovery_manifests())

    llm_model = LiteLlm(
        model=config.model, api_key=config.api_key, api_base=config.api_base, extra_body=config.extra_body
    )
    
    def handle_tool_error(tool, args, tool_context, error):
        return {"error": f"Tool failed: {str(error)}", "status": "failed"}

    # 创建 AutoCompactAgent (Sub-Agent)
    compactor_agent = AutoCompactAgent(config)

    # === [关键修改] 注册回调 ===
    my_agent = LlmAgent(
        name=config.name,
        model=llm_model,
        instruction=system_prompt,
        tools=[skill_load],
        sub_agents=[compactor_agent],
        on_tool_error_callback=handle_tool_error,
        
        # 1. 每次调用 LLM 前检查 (省钱)
        before_model_callback=interruption_guard,
        # 2. 每次调用 Tool 前检查 (安全)
        before_tool_callback=interruption_guard
    )
    return my_agent

def _process_event_stream(event):
    """处理事件单独一个event 而不是整个事件流"""
    chunks = []

    # [关键修复] 如果是最终响应事件，通常包含的是完整内容的汇总。
    # 我们已经在之前的流式事件中处理过这些 parts 了，所以在这里跳过常规处理，
    # 避免向前端发送重复的内容。
    is_final = hasattr(event, 'is_final_response') and event.is_final_response()

    # 1. 侦察：这个包里有没有工具？
    has_tool = False
    if not is_final and hasattr(event, 'content') and event.content and hasattr(event.content, 'parts'):
        for part in event.content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                has_tool = True
                break

    # 2. 处理 (仅在非最终响应时处理 parts)
    if not is_final and hasattr(event, 'content') and event.content and hasattr(event.content, 'parts'):
        for part in event.content.parts:
            # [关键修正] 仅当当前包里有工具，且当前 part 是文本或思考过程时，才跳过。
            # 必须放行 function_call 和 function_response 自身。
            is_text_part = hasattr(part, 'text') and part.text
            is_tool_related = (hasattr(part, 'function_call') and part.function_call) or \
                              (hasattr(part, 'function_response') and part.function_response)
            
            if has_tool and is_text_part and not is_tool_related:
                continue

            # 如果是文本
            if hasattr(part, 'text') and part.text:
                # [新增] 过滤思考过程 (thought parts)
                # Google GenAI SDK 中，思考过程会被标记为 thought=True
                if getattr(part, 'thought', False):
                    # 将思考过程标记为 thought 类型，前端可以根据需要选择隐藏或折叠显示
                    chunks.append({"type": "thought", "content": part.text})
                    continue
                
                text = part.text
                logger.thought(text)
                print(f"[streaming] {text}")
                chunks.append({"type": "text", "content": part.text})

            # 如果是工具 -> 正常发
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                fc_msg = f"{fc.name} 输入参数: {fc.args}"
                print(f"[streaming_工具调用] {fc_msg}")
                chunks.append({"type": "tool_call", "content": fc_msg})

            # 如果是结果 -> 正常发
            if hasattr(part, 'function_response') and part.function_response:
                fr = part.function_response
                fc_tool_response_msg= f"{fr.name} -> {fr.response}"
                print(f"[streaming_工具调用结果] {fc_tool_response_msg}")
                chunks.append({"type": "tool_result", "content": f"结果: {part.function_response.response}"})

    # 最终响应
    if is_final:
        if event.content and event.content.parts:
            print('\n*************')
            print(f'\n[event中根据is_final_response获取完整响应]\n{event}')
            final_text = event.content.parts[0].text
            logger.task_complete(final_text)
            print(f"\n{'='*60}")
            print(f"[event中根据is_final_response获取完整响应text]\n{final_text}")
            pass
    return chunks

# ==========================================
# 核心运行逻辑 (包含文本打断支持)
# ==========================================

async def run_agent(task: str, app_name: str, user_id: str, session_id: str):
    """
    运行 Agent，支持多参数 Session 定位
    """
    global my_agent, session_service
    if my_agent is None: create_agent()

    # === [关键步骤 1] 设置上下文三元组 ===
    # 这样后续的 callback 才知道去哪个队列查信号
    current_key = (app_name, user_id, session_id)
    token = current_session_key.set(current_key)
    
    # 确保队列存在
    get_or_create_queue(app_name, user_id, session_id)

    # Flag to track interruption Line#444设置True Line#480 finally处理分支在后台在打一遍方便看
    was_interrupted = False

    try:
        from google.adk.runners import Runner
        from google.adk.agents import RunConfig
        from google.adk.agents.run_config import StreamingMode

        runner = Runner(agent=my_agent, app_name=app_name, session_service=session_service)
        
        # 确保 session 存在 (略微简化逻辑)
        session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        if not session:
            session = await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)

        # === [新增] 压缩逻辑移植 ===
        turn_count = len(session.events) if session and hasattr(session, 'events') and session.events else 0
        tool_count = len(my_agent.tools) if my_agent.tools else 0
        
        # 阈值检查与自动截断
        WARN_TURNS = 20   # 软阈值
        MAX_TURNS = 20    # 硬阈值
        
        # 软阈值：提醒压缩
        if turn_count > WARN_TURNS and turn_count <= MAX_TURNS:
            print(f"\n[提醒] event个数 ({turn_count}) 超过软阈值 {WARN_TURNS}，建议执行 smart_compact 压缩上下文")
        
        # 硬阈值：强制截断
        if turn_count > MAX_TURNS:
            print(f"\n[警告] event个数 ({turn_count}) 超过硬阈值 {MAX_TURNS}，正在执行自动压缩...")
            yield {"type": "text", "content": f"\n[系统] 智能体执行超过MAX_TURNS={MAX_TURNS}，正在自动压缩上下文...\n"}
            
            try:
                # 1. 格式化历史记录
                history_text = ""
                if session and hasattr(session, 'events'):
                    for evt in session.events:
                        role = "unknown"
                        if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
                            role = evt.content.role
                        
                        content = ""
                        if hasattr(evt, 'content') and hasattr(evt.content, 'parts'):
                            for part in evt.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    content += part.text
                                if hasattr(part, 'function_call') and part.function_call:
                                    content += f" [ToolCall: {part.function_call.name}]"
                                if hasattr(part, 'function_response') and part.function_response:
                                    content += f" [ToolOutput: {part.function_response.name}]"
                        
                        history_text += f"{role}: {content}\n"

                # 2. 调用 AutoCompactAgent 生成摘要
                summary = "（自动摘要失败）"
                if compactor_agent:
                    print("[系统] 正在调用 AutoCompactAgent 生成摘要...")
                    summary = await compactor_agent.compact_history(history_text)
                    print(f"[系统] 摘要生成成功: {summary}")
                else:
                    print("[错误] compactor_agent 未初始化")

                # 3. 执行截断
                try:
                    print(f"[系统] 执行 Hard Reset，保留摘要...")
                    
                    # 3.1 收集 System 消息
                    system_events = []
                    for evt in session.events:
                        role = 'unknown'
                        if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
                            role = evt.content.role
                        if role == 'system':
                            system_events.append(evt)
                        else:
                            break
                    
                    # 3.2 构造占位符 User 消息
                    import copy
                    placeholder_user_evt = None
                    if session.events:
                        template_evt = session.events[0]
                        placeholder_user_evt = copy.deepcopy(template_evt)
                        if hasattr(placeholder_user_evt, 'content'):
                            placeholder_user_evt.content.role = 'user'
                            placeholder_user_evt.content.parts = [types.Part(text=f"[System] Context cleared. Summary of previous conversation:\n{summary}")]
                    
                    if placeholder_user_evt:
                        # 3.3 重组事件
                        new_events = system_events + [placeholder_user_evt]
                        
                        # [Critical Fix] InMemorySessionService returns a deepcopy, so we MUST update the internal storage
                        from google.adk.sessions import InMemorySessionService
                        if isinstance(session_service, InMemorySessionService):
                            try:
                                if (app_name in session_service.sessions and 
                                    user_id in session_service.sessions[app_name] and 
                                    session_id in session_service.sessions[app_name][user_id]):
                                    
                                    stored_session = session_service.sessions[app_name][user_id][session_id]
                                    if hasattr(stored_session.events, 'clear') and hasattr(stored_session.events, 'extend'):
                                        stored_session.events.clear()
                                        stored_session.events.extend(new_events)
                                    else:
                                        stored_session.events[:] = new_events
                                    print("[系统] 已强制同步会话状态到存储")
                                    
                                    # Update local session ref as well
                                    if hasattr(session.events, 'clear') and hasattr(session.events, 'extend'):
                                        session.events.clear()
                                        session.events.extend(new_events)
                                    else:
                                        session.events[:] = new_events
                                        
                            except Exception as e:
                                print(f"[警告] 强制同步会话失败: {e}")
                            
                        turn_count = len(session.events)
                        
                        # === [新增] 计算压缩后文本长度并通知前端 ===
                        original_len = len(history_text)
                        new_len = 0
                        for evt in session.events:
                            if hasattr(evt, 'content') and hasattr(evt.content, 'parts'):
                                for part in evt.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        new_len += len(part.text)
                        
                        stats_msg = f"\n[系统] 自动压缩完成。原始文本长度: {original_len} -> 压缩后: {new_len} (减少 {original_len - new_len} 字符)"
                        print(stats_msg)
                        yield {"type": "text", "content": stats_msg + "\n"}

                    else:
                        print("[错误] 无法构造占位消息，放弃压缩")
                        
                except Exception as e:
                    print(f"[错误] 执行截断逻辑失败: {e}")
                    import traceback
                    traceback.print_exc()

            except Exception as e:
                print(f"[错误] 自动压缩流程失败: {e}")
                import traceback
                traceback.print_exc()
                
        if tool_count > 12:
            print(f"\n[提醒] 已加载工具较多 ({tool_count})，建议卸载不常用的 skill")

        # 软阈值：提醒压缩 (注入到 Prompt 中)
        if turn_count > WARN_TURNS and turn_count <= MAX_TURNS:
            print(f"\n[提醒] event个数 ({turn_count}) 超过软阈值 {WARN_TURNS}，已注入压缩指令")
            task += "\n\n[System Note] Context is getting long (events > 40). Please call 'smart_compact' tool to summarize history and free up space."

        # 启动前先检票
        interruption_guard()

        user_query = types.Content(role='user', parts=[types.Part(text=task)])
        run_config = RunConfig(streaming_mode=StreamingMode.SSE)

        logger.task_start(task)
        print(f"\n[任务] {task}")
        print("-" * 60)

        try:
            # === 执行 Runner ===
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id, # 注意：runner 内部也会用到 session_id
                new_message=user_query,
                run_config=run_config
            ):
                # === [关键步骤 2] 文本输出时的打断检查 ===
                # 在流式输出的每一个 chunk 间隙都进行检查
                # 这保证了即便是普通文本输出，也能立刻响应 Cancel
                interruption_guard()

                chunks = _process_event_stream(event)
                for chunk in chunks:
                    yield chunk

        except UserInterruption:
            was_interrupted = True
            # === [优雅中断] ===
            print(f"\n🛑 [System] 任务已停止 ({app_name}/{user_id}/{session_id})")
            
            # 手动插入一条历史记录，防止追问时上下文断层
            try:
                from google.adk.sessions import Event
                stop_content = types.Content(role="system", parts=[types.Part(text="[System] 用户主动中断了当前对话。")])
                # Use the correct Event class from google.adk.sessions
                stop_event = Event(author="system", content=stop_content)
                
                if session and hasattr(session, 'events'):
                    session.events.append(stop_event)
                    print(f"[System] 已插入中断标记到历史记录")
            except Exception as e:
                print(f"[Warning] Failed to append interruption history: {e}")

            yield {"type": "text", "content": "\n\n[已停止] 任务已取消。"}
            return

    except Exception as e:
        logger.error(f"执行出错: {e}")
        yield f"[ERROR] {str(e)}"
        print(f"\n[ERROR] 执行出错: {e}")

    #
    # Extract content from structured chunks for printing
    # final_text_content = ""
    # for chunk in full_final_result_list:
    #     if isinstance(chunk, dict) and 'content' in chunk:
    #         final_text_content += chunk['content']
    #     elif isinstance(chunk, str):
    #         final_text_content += chunk
            
    # print(f'[拼接所得到的full_final_result]\n{final_text_content}')
    
    finally:
        # 打印 Session History (可选，用于调试)
        try:
            updated_session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
            print("\n\n***打印session events***\n===Session History Start===")
            if updated_session and updated_session.events:
                for event in updated_session.events:
                    if event.content and event.content.parts:
                        print(f"<{event.author}>: {event.content.parts}")
                        print('=='*10 + '\n')
            print("=" * 60)
        except Exception as e:
            print(f"[Warning] Failed to print session history: {e}")

        if was_interrupted:
             print(f"\n🛑 [System] 任务已停止 (Interrupted by User)")

        # === [清理] 重置上下文 ===
        current_session_key.reset(token)


# ==========================================
# Web 服务接口
# ==========================================

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

class ChatRequest(BaseModel):
    message: str
    # 允许前端传参，如果没传则用默认值
    app_name: str = DEFAULT_APP_NAME
    user_id: str = DEFAULT_USER_ID
    session_id: str = DEFAULT_SESSION_ID

class CancelRequest(BaseModel):
    # 取消时必须提供完整的三元组信息
    app_name: str = DEFAULT_APP_NAME
    user_id: str = DEFAULT_USER_ID
    session_id: str = DEFAULT_SESSION_ID

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    async def generate():
        # 传入完整的三元组
        async for chunk in run_agent(
            request.message, 
            request.app_name, 
            request.user_id, 
            request.session_id
        ):
            yield json.dumps({"chunk": chunk}) + "\n"
    return StreamingResponse(generate(), media_type="application/x-ndjson")

@app.post("/api/cancel")
async def cancel_endpoint(req: CancelRequest):
    """
    接收取消指令，精确定位到具体的 Queue
    """
    q = get_or_create_queue(req.app_name, req.user_id, req.session_id)
    await q.put("CANCEL")
    print(f"🛑 [API] 收到 Cancel 信号 -> {req.app_name}/{req.user_id}/{req.session_id}")
    return {"status": "success"}

@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

def start_web_server():
    print("Starting web server at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start_web_server()
