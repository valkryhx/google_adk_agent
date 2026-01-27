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
import time
import secrets
from contextvars import ContextVar
from typing import Dict, Tuple, Optional, Any, List

# 将当前目录添加到路径
#sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skills.adk_agent.core.manager import SkillManager
from skills.adk_agent.core.executor import execute_python_code
from skills.adk_agent.core.logger import AgentLogger, logger
from skills.adk_agent.config import AgentConfig, build_system_prompt
from google.genai import types
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from google.adk.agents import LlmAgent
from src.core.custom_table_db_service import FullyCustomDbService
from google.adk.models.lite_llm import LiteLlm
from skills.adk_agent.auto_compact_agent import AutoCompactAgent

# ==========================================
# [AOP 基础设施] 中断控制（已废弃，保留用于兼容）
# ==========================================

# SessionKey = (app_name, user_id, session_id)
SessionKey = Tuple[str, str, str]

# 中断异常定义（仍然被 SteeringSession 使用）
class UserInterruption(Exception):
    """用户手动触发的中断异常"""
    pass

# [DEPRECATED] 以下代码已废弃，新架构中由 SteeringSession 管理
# - current_session_key (ContextVar)
# - interruption_queues (Dict)
# - get_or_create_queue()
# - interruption_guard()

# ==========================================
# 业务逻辑代码
# ==========================================

# 全局单例服务（无状态，线程安全）
session_service = None
sm = None
config = AgentConfig()
compactor_agent = None

# 默认常量
DEFAULT_APP_NAME = "dynamic_expert"
DEFAULT_USER_ID = "user_001"
DEFAULT_SESSION_ID = "session_001"

# ==========================================
# [新架构] SteeringSession 类
# ==========================================

class SteeringSession:
    """
    封装单个会话的所有状态和逻辑
    - agent: 该会话专属的 LlmAgent 实例
    - queue: 该会话专属的中断队列
    - 所有业务方法（skill_load、interruption_guard 等）都是实例方法
    """
    def __init__(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        config: AgentConfig,
        session_service,
        skill_manager: SkillManager,
        compactor_agent  # 保留参数以兼容，但不再使用
    ):
        self.app_name = app_name
        self.user_id = user_id
        self.session_id = session_id
        self.key = (app_name, user_id, session_id)
        
        # 会话专属状态
        self.session_service = session_service
        self.skill_manager = skill_manager
        # 不再存储全局 compactor_agent，每个 agent 内部会创建自己的
        self.config = config
        
        # 中断控制
        self.queue = asyncio.Queue()
        
        # 创建会话专属的 Agent（内部会创建自己的 compactor）
        self.agent = self._create_agent()
        
        print(f"[SteeringSession] Created session for {self.key}")
    
    def _create_agent(self) -> LlmAgent:
        """创建会话专属的 LlmAgent 实例"""
        system_prompt = build_system_prompt(self.config, self.skill_manager.get_discovery_manifests())
        
        llm_model = LiteLlm(
            model=self.config.model, 
            api_key=self.config.api_key, 
            api_base=self.config.api_base, 
            extra_body=self.config.extra_body
        )
        
        def handle_tool_error(tool, args, tool_context, error):
            return {"error": f"Tool failed: {str(error)}", "status": "failed"}
        
        # ⚠️ 关键修复：每个会话创建自己的 compactor_agent 实例
        # 不能共享全局的 compactor_agent，因为 sub_agent 只能有一个 parent
        session_compactor = AutoCompactAgent(self.config)
        
        agent = LlmAgent(
            name=self.config.name,
            model=llm_model,
            instruction=system_prompt,
            tools=[self.skill_load],  # 绑定实例方法
            sub_agents=[session_compactor],  # 使用会话专属的实例
            on_tool_error_callback=handle_tool_error,
            before_model_callback=self.interruption_guard,  # 绑定实例方法
            before_tool_callback=self.interruption_guard   # 绑定实例方法
        )
        
        return agent
    
    async def skill_load(self, skill_id: str) -> str:
        """动态加载技能工具（实例方法，直接访问 self.agent）"""
        print(f"[{self.key}] 激活技能: {skill_id}")
        if not self.skill_manager.skill_exists(skill_id):
            return f"[ERROR] 技能 '{skill_id}' 不存在。"
        
        self._load_skill_tools(skill_id)
        return f"""[OK] 技能 '{skill_id}' 已加载。Instructions:\n{self.skill_manager.load_full_sop(skill_id)}"""
    
    def _load_skill_tools(self, skill_id: str):
        """加载技能工具到当前 agent"""
        import importlib.util
        tools_path = os.path.join(self.config.skills_path, skill_id, "tools.py")
        if not os.path.exists(tools_path): 
            return []
        
        try:
            spec = importlib.util.spec_from_file_location(f"skill_{skill_id}", tools_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            tools = []
            if hasattr(module, 'get_tools'):
                try:
                    # 注入会话信息
                    app_info = {
                        "app_name": self.app_name, 
                        "user_id": self.user_id, 
                        "session_id": self.session_id
                    }
                    tools = module.get_tools(self.agent, self.session_service, app_info)
                except:
                    tools = module.get_tools()
            elif hasattr(module, 'TOOLS'):
                tools = list(module.TOOLS.values())
            
            loaded = []
            existing_names = {t.__name__ for t in self.agent.tools if hasattr(t, '__name__')}
            for tool in tools:
                t_name = getattr(tool, '__name__', str(tool))
                if t_name not in existing_names:
                    self.agent.tools.append(tool)
                    loaded.append(tool)
                    existing_names.add(t_name)
            return loaded
        except Exception as e:
            logger.error(f"加载工具失败: {skill_id}", error=str(e))
            return []
    
    def interruption_guard(self, *args, **kwargs):
        """中断卫士（实例方法，直接访问 self.queue）"""
        if self.queue and not self.queue.empty():
            try:
                signal = self.queue.get_nowait()
                if signal == "CANCEL":
                    print(f"🛑 [AOP拦截] 检测到中断信号! Target: {self.key}")
                    
                    # 清空队列
                    while not self.queue.empty(): 
                        self.queue.get_nowait()
                    
                    raise UserInterruption("User requested to stop operation.")
            except asyncio.QueueEmpty:
                pass
        
        return None
    
    async def run_task(self, task: str):
        """
        执行任务主逻辑（原 run_agent 函数的核心部分）
        使用 yield 返回流式数据块
        """
        was_interrupted = False
        
        try:
            from google.adk.runners import Runner
            from google.adk.agents import RunConfig
            from google.adk.agents.run_config import StreamingMode
            
            runner = Runner(agent=self.agent, app_name=self.app_name, session_service=self.session_service)
            
            # 确保 session 存在
            session = await self.session_service.get_session(
                app_name=self.app_name, 
                user_id=self.user_id, 
                session_id=self.session_id
            )
            print(f"[调试] get_session 返回: app_name={self.app_name}, user_id={self.user_id}, session_id={self.session_id}, session存在={session is not None}")
            if session and hasattr(session, 'events'):
                print(f"[调试] session.events数量={len(session.events)}")
            
            if not session:
                print(f"[调试] 创建新session: app_name={self.app_name}, user_id={self.user_id}, session_id={self.session_id}")
                session = await self.session_service.create_session(
                    app_name=self.app_name, 
                    user_id=self.user_id, 
                    session_id=self.session_id
                )
            
            # === 自动标题生成 ===
            user_event_count = 0
            if session and hasattr(session, 'events'):
                for evt in session.events:
                    role = 'unknown'
                    if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
                        role = evt.content.role
                    elif hasattr(evt, 'author'):
                        role = evt.author
                    if role == 'user':
                        user_event_count += 1
            
            if user_event_count == 0:
                title = task[:30] + ("..." if len(task) > 30 else "")
                if not hasattr(session, 'state') or session.state is None:
                    session.state = {}
                session.state['title'] = title
                await self.session_service.save_session(session)
                print(f"[系统] 自动生成会话标题: {title}")
            
            # === 压缩逻辑 ===
            turn_count = len(session.events) if session and hasattr(session, 'events') and session.events else 0
            tool_count = len(self.agent.tools) if self.agent.tools else 0
            
            WARN_TURNS = 20
            MAX_TURNS = 20
            
            if turn_count > WARN_TURNS and turn_count <= MAX_TURNS:
                print(f"\n[提醒] event个数 ({turn_count}) 超过软阈值 {WARN_TURNS}，建议执行 smart_compact 压缩上下文")
            
            if turn_count > MAX_TURNS:
                print(f"\n[警告] event个数 ({turn_count}) 超过硬阈值 {MAX_TURNS}，正在执行自动压缩...")
                yield {"type": "text", "content": f"\n[系统] 智能体执行超过MAX_TURNS={MAX_TURNS}，正在自动压缩上下文...\n"}
                
                # 执行压缩（复用原有逻辑）
                session = await self._auto_compact_session(session)
                
                # ⚠️ 关键修复：更新turn_count，确保后续不再触发压缩
                turn_count = len(session.events) if session and hasattr(session, 'events') else 0
                print(f"[系统] 压缩完成，当前events数量: {turn_count}")
            
            if tool_count > 12:
                print(f"\n[提醒] 已加载工具较多 ({tool_count})，建议卸载不常用的 skill")
            
            if turn_count > WARN_TURNS and turn_count <= MAX_TURNS:
                task += "\n\n[System Note] Context is getting long (events > 40). Please call 'smart_compact' tool to summarize history and free up space."
            
            # 启动前检票
            self.interruption_guard()
            
            user_query = types.Content(role='user', parts=[types.Part(text=task)])
            run_config = RunConfig(streaming_mode=StreamingMode.SSE)
            
            logger.task_start(task)
            print(f"\n[任务] {task}")
            print("-" * 60)
            
            try:
                async for event in runner.run_async(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    new_message=user_query,
                    run_config=run_config
                ):
                    # 文本输出时的打断检查
                    self.interruption_guard()
                    
                    chunks = _process_event_stream(event)
                    for chunk in chunks:
                        yield chunk
            
            except UserInterruption:
                was_interrupted = True
                print(f"\n🛑 [System] 任务已停止 ({self.key})")
                
                # 插入中断标记
                try:
                    from google.adk.sessions import Event
                    stop_content = types.Content(role="system", parts=[types.Part(text="[System] 用户主动中断了当前对话。")])
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
        
        finally:
            # 打印 Session History（调试用）
            try:
                updated_session = await self.session_service.get_session(
                    app_name=self.app_name, 
                    user_id=self.user_id, 
                    session_id=self.session_id
                )
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
    
    async def _auto_compact_session(self, session):
        """自动压缩会话历史（内部方法）"""
        try:
            # 格式化历史记录
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
                # 从 agent 的 sub_agents 中获取 compactor
                compactor = None
                if self.agent.sub_agents:
                    from skills.adk_agent.auto_compact_agent import AutoCompactAgent # Import here to avoid circular dependency
                    for sub in self.agent.sub_agents:
                        if isinstance(sub, AutoCompactAgent):
                            compactor = sub
                            break
                
                if compactor:
                    print("[系统] 正在调用 AutoCompactAgent 生成摘要...")
                    summary = await compactor.compact_history(history_text)
                    print(f"[系统] 摘要生成成功: {summary}")
                else:
                    print("[错误] compactor_agent 未找到")
            
            # 执行截断
            try:
                print(f"[系统] 执行 Hard Reset，保留摘要...")
                
                # 收集 System 消息
                system_events = []
                for evt in session.events:
                    role = 'unknown'
                    if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
                        role = evt.content.role
                    if role == 'system':
                        system_events.append(evt)
                    else:
                        break
                
                # 构造占位符 User 消息
                import copy
                placeholder_user_evt = None
                if session.events:
                    template_evt = session.events[0]
                    placeholder_user_evt = copy.deepcopy(template_evt)
                    if hasattr(placeholder_user_evt, 'content'):
                        placeholder_user_evt.content.role = 'user'
                        placeholder_user_evt.content.parts = [
                            types.Part(text=f"[System] Context cleared. Summary of previous conversation:\n{summary}")
                        ]
                
                if placeholder_user_evt:
                    new_events = system_events + [placeholder_user_evt]
                    
                    print(f"[系统] 压缩前 event 数量: {len(session.events)}")
                    
                    if hasattr(session.events, 'clear') and hasattr(session.events, 'extend'):
                        session.events.clear()
                        session.events.extend(new_events)
                    else:
                        session.events[:] = new_events
                    
                    print(f"[系统] 压缩后 event 数量: {len(session.events)}")
                    
                    # 持久化
                    from google.adk.sessions import InMemorySessionService
                    if isinstance(self.session_service, InMemorySessionService):
                        try:
                            if (self.app_name in self.session_service.sessions and 
                                self.user_id in self.session_service.sessions[self.app_name] and 
                                self.session_id in self.session_service.sessions[self.app_name][self.user_id]):
                                
                                stored_session = self.session_service.sessions[self.app_name][self.user_id][self.session_id]
                                if hasattr(stored_session.events, 'clear') and hasattr(stored_session.events, 'extend'):
                                    stored_session.events.clear()
                                    stored_session.events.extend(new_events)
                                else:
                                    stored_session.events[:] = new_events
                                print("[系统] 已强制同步会话状态到 InMemorySessionService")
                        except Exception as e:
                            print(f"[警告] InMemory 强制同步会话失败: {e}")
                    else:
                        try:
                            await self.session_service.save_session(session)
                            print(f"[系统] ✅ 已通过 save_session() 持久化压缩后的 events 到数据库")
                        except Exception as e:
                            print(f"[错误] ❌ 数据库持久化失败: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # 计算压缩统计
                    original_len = len(history_text)
                    new_len = 0
                    for evt in session.events:
                        if hasattr(evt, 'content') and hasattr(evt.content, 'parts'):
                            for part in evt.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    new_len += len(part.text)
                    
                    stats_msg = f"\n[系统] 自动压缩完成。原始文本长度: {original_len} -> 压缩后: {new_len} (减少 {original_len - new_len} 字符)"
                    print(stats_msg)
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
        
        return session


# ==========================================
# [新架构] SessionManager 类
# ==========================================

class SessionManager:
    """
    会话管理器：维护所有活跃的 SteeringSession 实例
    - 负责创建和查找会话
    - 未来可以添加 LRU Cache、过期清理等功能
    """
    def __init__(self, config: AgentConfig, session_service, skill_manager: SkillManager, compactor_agent):
        self._sessions: Dict[SessionKey, SteeringSession] = {}
        self.config = config
        self.session_service = session_service
        self.skill_manager = skill_manager
        self.compactor_agent = compactor_agent
        
        print("[SessionManager] Initialized")
    
    def get_or_create(self, app_name: str, user_id: str, session_id: str) -> SteeringSession:
        """获取或创建会话实例"""
        key = (app_name, user_id, session_id)
        
        if key not in self._sessions:
            self._sessions[key] = SteeringSession(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                config=self.config,
                session_service=self.session_service,
                skill_manager=self.skill_manager,
                compactor_agent=self.compactor_agent
            )
            print(f"[SessionManager] Created new session: {key}")
        
        return self._sessions[key]
    
    def get(self, app_name: str, user_id: str, session_id: str) -> Optional[SteeringSession]:
        """仅获取会话（不创建）"""
        key = (app_name, user_id, session_id)
        return self._sessions.get(key)
    
    def remove(self, app_name: str, user_id: str, session_id: str):
        """移除会话（用于清理）"""
        key = (app_name, user_id, session_id)
        if key in self._sessions:
            del self._sessions[key]
            print(f"[SessionManager] Removed session: {key}")


# 全局 SessionManager 实例
session_manager: Optional[SessionManager] = None


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

# ==========================================
# [DEPRECATED] 旧的全局函数（兼容层）
# ==========================================

async def skill_load(skill_id: str) -> str:
    """
    [DEPRECATED] 旧的 skill_load 函数，现在已废弃
    新架构中 skill_load 是 SteeringSession 的实例方法
    """
    print(f"[WARNING] 调用了已废弃的全局 skill_load 函数")
    return "[ERROR] 该函数已废弃，请使用 SteeringSession.skill_load"

async def create_agent(custom_config: AgentConfig = None):
    """
    [DEPRECATED] 旧的 create_agent 函数，现在已废弃
    新架构中 Agent 由 SteeringSession 在初始化时自动创建
    
    该函数现在用于初始化全局服务（session_service, sm, compactor_agent）
    """
    global session_service, sm, config, compactor_agent, session_manager
    if custom_config: 
        config = custom_config
    
    sm = SkillManager(base_path=config.skills_path)
    
    # 计算项目根目录
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_folder = os.path.join(base_dir, "sqlite_db")
    if not os.path.exists(db_folder):
        os.makedirs(db_folder, exist_ok=True)
    
    db_path = os.path.join(db_folder, "adk_sessions.db")
    if sys.platform == 'win32':
        db_path = db_path.replace('\\', '/')
        
    # 使用自定义 DB Service
    session_service = FullyCustomDbService(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        session_table_name="adk_sessions",
        event_table_name="adk_events"
    )
    await session_service.init_db()
    
    # 创建 AutoCompactAgent (Sub-Agent)
    compactor_agent = AutoCompactAgent(config)
    
    # 创建 SessionManager
    session_manager = SessionManager(
        config=config,
        session_service=session_service,
        skill_manager=sm,
        compactor_agent=compactor_agent
    )
    
    print("[系统] 全局服务初始化完成 (session_service, sm, compactor_agent, session_manager)")
    
    return None  # 不再返回 my_agent

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
# 核心运行逻辑 (新架构适配层)
# ==========================================

async def run_agent(task: str, app_name: str, user_id: str, session_id: str):
    """
    [新架构] 运行 Agent（适配器函数）
    委托给 SessionManager 来获取/创建会话，然后调用 session.run_task()
    """
    global session_manager
    
    if session_manager is None:
        raise RuntimeError("SessionManager 未初始化，请先调用 startup_event 或 create_agent")
    
    # 获取或创建会话
    session = session_manager.get_or_create(app_name, user_id, session_id)
    
    # 委托给会话实例执行任务
    async for chunk in session.run_task(task):
        yield chunk

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

class CreateSessionRequest(BaseModel):
    app_name: str = DEFAULT_APP_NAME
    user_id: str = DEFAULT_USER_ID

class SessionInfo(BaseModel):
    session_id: str
    title: str
    message_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]

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
    [新架构] 接收取消指令，通过 SessionManager 定位会话并发送中断信号
    """
    global session_manager
    
    if session_manager is None:
        return {"status": "error", "message": "SessionManager not initialized"}
    
    # 获取会话（不创建）
    session = session_manager.get(req.app_name, req.user_id, req.session_id)
    
    if session is None:
        print(f"🛑 [API] 无法找到会话 -> {req.app_name}/{req.user_id}/{req.session_id}")
        return {"status": "error", "message": "Session not found"}
    
    # 向会话的队列发送中断信号
    await session.queue.put("CANCEL")
    print(f"🛑 [API] 收到 Cancel 信号 -> {req.app_name}/{req.user_id}/{req.session_id}")
    return {"status": "success"}

@app.post("/api/sessions")
async def create_session(request: CreateSessionRequest):
    """创建新会话"""
    # 生成唯一 session_id (依赖 ADK 的双键隔离：user_id + session_id)
    timestamp = int(time.time() * 1000)
    random_suffix = secrets.token_hex(4)
    new_session_id = f"session_{timestamp}_{random_suffix}"
    
    print(f"[创建会话] app_name={request.app_name}, user_id={request.user_id}, session_id={new_session_id}")
    
    # 创建会话
    from datetime import datetime
    session = await session_service.create_session(
        app_name=request.app_name,
        user_id=request.user_id, 
        session_id=new_session_id
    )
    
    return {
        "session_id": new_session_id,
        "title": "新对话",
        "created_at": datetime.utcnow().isoformat()
    }

@app.get("/api/sessions")
async def get_sessions(
    app_name: str = DEFAULT_APP_NAME,
    user_id: str = DEFAULT_USER_ID
):
    """获取会话列表"""
    result = await session_service.list_sessions(
        app_name=app_name,
        user_id=user_id
    )
    
    sessions = []
    for s in result.sessions:
        # 从 session.state 中提取标题
        title = "新对话"
        message_count = len(s.events) if hasattr(s, 'events') else 0
        
        if hasattr(s, 'state') and s.state:
            title = s.state.get('title', '新对话')
        
        # 提取自定义属性 (由 custom_table_db_service 添加)
        created_at = None
        updated_at = None
        if hasattr(s, '_db_created_at'):
            created_at = s._db_created_at.isoformat() if s._db_created_at else None
        if hasattr(s, '_db_updated_at'):
            updated_at = s._db_updated_at.isoformat() if s._db_updated_at else None
        
        sessions.append({
            "session_id": s.id,
            "title": title,
            "message_count": message_count,
            "created_at": created_at,
            "updated_at": updated_at
        })
    
    return {"sessions": sessions}

@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    app_name: str = DEFAULT_APP_NAME, 
    user_id: str = DEFAULT_USER_ID
):
    """删除会话"""
    await session_service.delete_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id
    )
    return {"status": "success"}

@app.get("/api/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    app_name: str = DEFAULT_APP_NAME,
    user_id: str = DEFAULT_USER_ID
):
    """获取会话历史消息"""
    session = await session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id
    )
    
    if not session:
        return {"messages": []}
    
    messages = []
    for event in session.events:
        if hasattr(event, 'content') and event.content:
            role = 'unknown'
            if hasattr(event.content, 'role'):
                role = event.content.role
            elif hasattr(event, 'author'):
                role = event.author
            
            # 提取文本内容
            text_content = ""
            blocks = []
            
            if hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        # 检查是否是思考过程
                        if getattr(part, 'thought', False):
                            blocks.append({"type": "thought", "content": part.text})
                        else:
                            blocks.append({"type": "text", "content": part.text})
                            text_content += part.text
                    
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        blocks.append({
                            "type": "tool_call",
                            "content": f"{fc.name} 输入参数: {fc.args}"
                        })
                    
                    if hasattr(part, 'function_response') and part.function_response:
                        fr = part.function_response
                        blocks.append({
                            "type": "tool_result",
                            "content": f"结果: {fr.response}"
                        })
            
            if role == 'user' or role == 'model':
                messages.append({
                    "role": role,
                    "blocks": blocks,
                    "text": text_content  # 兼容性字段
                })
    
    return {"messages": messages}

@app.on_event("startup")
async def startup_event():
    """
    [新架构] FastAPI 启动时初始化全局服务
    不再初始化全局 Agent，Agent 由 SteeringSession 按需创建
    """
    global session_service, session_manager
    print("[系统] 正在初始化全局服务...")
    await create_agent()  # 初始化 session_service, sm, compactor_agent, session_manager
    print("[系统] ✓ 全局服务初始化完成")

@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

def start_web_server():
    print("Starting web server at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start_web_server()
