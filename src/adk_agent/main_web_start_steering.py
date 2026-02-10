"""
ADK Dynamic Skills Agent - 主入口 (多租户并发安全版)

修正点：
1. Session 识别升级：使用 (app_name, user_id, session_id) 三元组。
2. claudecode风格的steering实时文本打断增强：在流式输出循环中增加强制检查。
3. AOP 拦截：使用 before_model/tool callback。

python -m src.adk_agent.main_web_start_steering
"""

import asyncio
import os
import sys
import json
import time
import secrets
import sqlite3
import functools
from contextvars import ContextVar
from typing import Dict, Tuple, Optional, Any, List

# 将当前目录添加到路径
#sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 将项目根目录添加到路径 (3层目录向上)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
from src.adk_agent.core.manager import SkillManager
from src.adk_agent.core.executor import execute_python_code
from src.adk_agent.core.logger import AgentLogger, logger
from src.adk_agent.config import AgentConfig, build_system_prompt
import litellm
from litellm import ContextWindowExceededError
from google.genai import types
from fastapi import FastAPI, Response, status, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import datetime

from google.adk.agents import LlmAgent
from src.shared.db.custom_table_db_service import FullyCustomDbService
from google.adk.models.lite_llm import LiteLlm
from src.adk_agent.auto_compact_agent import AutoCompactAgent


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
# 1. 节点配置与全局变量 (新增)
# ==========================================
class NodeConfig:
    port: int = 8000
    # 数据库名由 port 自动生成，实现物理隔离

node_config = NodeConfig()

# ==========================================
# [新增] 全局工作锁与状态管理
# ==========================================
class WorkerState:
    def __init__(self):
        self.locked = False
        self.current_task_summary = ""
        self.current_session_id = ""
        self.start_time = None
        
    def set_busy(self, task_summary, session_id):
        self.locked = True
        self.current_task_summary = task_summary
        self.current_session_id = session_id
        self.start_time = datetime.datetime.now()
        
    def set_idle(self):
        self.locked = False
        self.current_task_summary = ""
        self.current_session_id = ""
        self.start_time = None

worker_state = WorkerState()
WORKER_LOCK = asyncio.Lock()

# ==========================================
# 2. SQLite 服务注册逻辑 (Service Discovery)
# ==========================================
# 使用与 session DB 相同的路径策略，基于 __file__ 计算绝对路径，不依赖 CWD
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_DB = os.path.join(_PROJECT_ROOT, "sqlite_db", "swarm_registry.db")

def init_registry_db():
    """初始化注册表数据库 (幂等操作)"""
    # 确保父目录存在，防止 unable to open database file 错误
    os.makedirs(os.path.dirname(REGISTRY_DB), exist_ok=True)
    try:
        with sqlite3.connect(REGISTRY_DB, timeout=10.0) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    port INTEGER PRIMARY KEY,
                    url TEXT NOT NULL,
                    status TEXT,
                    last_seen REAL
                )
            """)
    except Exception as e:
        print(f"[Registry Init] ⚠️ 初始化警告: {e}")

def register_self():
    """启动时将自己注册到 SQLite"""
    try:
        url = f"http://localhost:{node_config.port}"
        with sqlite3.connect(REGISTRY_DB, timeout=10.0) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO nodes (port, url, status, last_seen)
                VALUES (?, ?, ?, ?)
            """, (node_config.port, url, "active", time.time()))
        print(f"[Node-{node_config.port}] 📝 已注册到 Swarm 集群")
    except Exception as e:
        print(f"[Node-{node_config.port}] ❌ 注册失败: {e}")

def deregister_self():
    """关闭时将自己移除"""
    try:
        with sqlite3.connect(REGISTRY_DB, timeout=10.0) as conn:
            conn.execute("DELETE FROM nodes WHERE port = ?", (node_config.port,))
        print(f"[Node-{node_config.port}] 👋 已退出 Swarm 集群")
    except Exception as e:
        print(f"[Node-{node_config.port}] ⚠️ 注销失败: {e}")

async def heartbeat_daemon():
    """[Dynamic Elasticity] 周期性更新心跳时间戳, 让 Leader 知道本节点还活着"""
    print(f"[Heartbeat] 启动心跳守护进程 (Port {node_config.port})")
    while True:
        try:
            await asyncio.sleep(5)
            current_time = time.time()
            with sqlite3.connect(REGISTRY_DB, timeout=2.0) as conn:
                conn.execute(
                    "UPDATE nodes SET last_seen = ? WHERE port = ?",
                    (current_time, node_config.port)
                )
        except Exception as e:
            print(f"[Heartbeat] 心跳更新失败: {e}")


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
        
        # [新特性] 旁路事件流队列 (用于 Swarm 实时状态汇报)
        self.stream_queue = asyncio.Queue()

        # 创建会话专属的 Agent（内部会创建自己的 compactor）
        self.agent = self._create_agent()
        
        print(f"[SteeringSession] Created session for {self.key}")
    
    def report_swarm_event(self, event_type: str, payload: dict):
        """
        供 Tool 调用的回调函数，用于实时汇报 Swarm 状态。
        消息会被放入 stream_queue，最终合并到 HTTP SSE 流中推给前端。
        """
        print(f"[SteeringSession] Reporting Event: {event_type}")
        event = {
            "type": "swarm_event",
            "sub_type": event_type, # init, chunk, finish, fail
            "data": payload
        }
        # 使用 put_nowait 防止工具被阻塞，如果队列满了(极其罕见)则丢弃或报错
        try:
            self.stream_queue.put_nowait(event)
        except asyncio.QueueFull:
            print(f"[SteeringSession] ⚠️ stream_queue full, dropping event: {event_type}")

    def _create_agent(self) -> LlmAgent:
        """创建会话专属的 LlmAgent 实例"""
        system_prompt = build_system_prompt(self.config, self.skill_manager.get_discovery_manifests())
        
        llm_model = LiteLlm(
            model=self.config.model, 
            api_key=self.config.api_key, 
            api_base=self.config.api_base, 
            extra_body=self.config.extra_body,
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries
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
        
        
        self.agent = agent  # 临时设置,供 _load_skill_tools 使用
        
        # 🟢 [Feature] 注入 Core Tool: File Editor (Anthropic Native)
        try:
            from skills.file_editor.tools import get_tools as get_file_tools
            file_tools = get_file_tools(self.agent, self.session_service, {
                "app_name": self.app_name, 
                "user_id": self.user_id, 
                "session_id": self.session_id
            })
            self.agent.tools.extend(file_tools)
            print(f"[SteeringSession] 已加载 Core Tool: file_editor")
        except Exception as e:
            print(f"[SteeringSession] ⚠️ 加载 file_editor 失败: {e}")
        
        # # 🔑 自动加载 bash 作为第3个自带工具
        # 加载 bash 时也尝试注入 reporter (虽然 bash 可能用不上)
        bash_tools = self._load_skill_tools('bash')
        print(f"[SteeringSession] 已自动加载 bash 工具: {[t.__name__ for t in bash_tools]}")
        
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
        import functools
        
        tool_files = [
            os.path.join(self.config.skills_path, skill_id, "tools.py"),
            os.path.join(self.skill_manager.base_path, ".claude/skills", skill_id, "tools.py")
        ]
        
        loaded_tools = []
        # 获取当前已加载工具的名称集合
        existing_names = {t.__name__ for t in self.agent.tools if hasattr(t, '__name__')}

        for tool_file in tool_files:
            if os.path.exists(tool_file):
                try:
                    spec = importlib.util.spec_from_file_location(f"skills.{skill_id}", tool_file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, 'get_tools'):
                        # 尝试注入 app_info 和 reporter
                        # get_tools(agent, session_service, app_info, status_reporter)
                        # 我们通过检查参数数量或直接传递 kwargs 来兼容
                        
                        common_args = (self.agent, self.session_service, {
                            "app_name": self.app_name,
                            "user_id": self.user_id,
                            "session_id": self.session_id
                        })
                        
                        try:
                            # 尝试传入 status_reporter
                            tools = module.get_tools(*common_args, status_reporter=self.report_swarm_event)
                        except TypeError:
                            # 如果报错 (unexpected keyword argument), 则回退到旧调用
                            tools = module.get_tools(*common_args)
                            
                        if tools:
                            # 绑定 interruption_guard
                            wrapped_tools = []
                            for tool in tools:
                                # 确保是异步函数才能被 agent 正确执行 (agent 内部会检查 iscoroutinefunction)
                                # 这里 agent 框架会自动处理，我们只需要 extend
                                
                                # [FIX] 检查是否重复加载
                                if hasattr(tool, '__name__') and tool.__name__ in existing_names:
                                    print(f"[{self.key}] ⚠️ 跳过重复工具: {tool.__name__} (from {skill_id})")
                                    continue

                                wrapped_tools.append(tool)
                                
                            if wrapped_tools:
                                self.agent.tools.extend(wrapped_tools)
                                loaded_tools.extend(wrapped_tools)
                                # 更新 existing_names 以防止同一次加载中的重复（虽然不太可能）
                                for t in wrapped_tools:
                                    if hasattr(t, '__name__'):
                                        existing_names.add(t.__name__)
                                        
                except Exception as e:
                     print(f"Failed to load tools from {tool_file}: {e}")
        return loaded_tools
    
    def interruption_guard(self, *args, **kwargs):
        """中断卫士（实例方法，直接访问 self.queue）"""
        if self.queue and not self.queue.empty():
            try:
                signal = self.queue.get_nowait()
                if signal == "CANCEL":
                    print(f"🛑 [AOP拦截] 检测到中断信号! Target: {self.key}")
                    print(f"🛑 [AOP拦截] 检测到中断信号! Target: {self.key}")
                    
                    # 清空队列
                    while not self.queue.empty(): 
                        self.queue.get_nowait()
                    
                    raise UserInterruption("User requested to stop operation.")
            except asyncio.QueueEmpty:
                pass
        
        return None

    async def _check_and_compact_context(self, session, limit_token_count: int):
        """检查并压缩上下文 (Token 基于)"""
        if session is None or not hasattr(session, 'events'):
             return

        # 只有当 events 数量足够多时才检查，避免频繁计算
        if len(session.events) < 10:
            return

        try:
            # 粗略估算不做精细化 Tokenize，性能优先
            total_chars = 0
            for evt in session.events:
                if hasattr(evt, 'content') and evt.content and evt.content.parts:
                    for part in evt.content.parts:
                        if part.text:
                            total_chars += len(part.text)
            
            estimated_tokens = total_chars // 3  # 保守一点，除以3
            
            # 阈值为 Limit 的 90%
            threshold = limit_token_count * 0.9
            
            if estimated_tokens > threshold:
                print(f"[系统] ⚠️ Context Token 预警: 估算 {estimated_tokens} > 阈值 {threshold} (Limit: {limit_token_count})")
                print(f"[系统] 触发主动压缩...")
                #await self._compact_context(session)
                #session = await self._auto_compact_session(session)
                await self._auto_compact_session(session)
                
        except Exception as e:
            print(f"[系统] Token 检查失败: {e}")

    # async def _compact_context(self, session):
    #     """执行上下文压缩逻辑"""
    #     print(f"[系统] 开始上下文压缩...")
        
    #     # 1. 提取历史文本
    #     history_text = ""
    #     for i, evt in enumerate(session.events):
    #         role = "unknown"
    #         content = ""
    #         if hasattr(evt, 'content'):
    #             role = evt.content.role if hasattr(evt.content, 'role') else "unknown"
    #             if evt.content.parts:
    #                 content = evt.content.parts[0].text if evt.content.parts[0].text else ""
            
    #         # Skip system prompt in history text for summarization to save tokens
    #         if role == 'system': 
    #             continue
                
    #         history_text += f"{role}: {content}\n\n"
            
    #     if not history_text:
    #         return

    #     # 2. 调用 Compactor
    #     try:
    #         # 查找会话专属的 compactor sub-agent
    #         compactor = None
    #         if self.agent.sub_agents:
    #              for sub in self.agent.sub_agents:
    #                  if isinstance(sub, AutoCompactAgent):
    #                      compactor = sub
    #                      break
            
    #         if not compactor:
    #              print("[Error] No compactor found in sub_agents")
    #              return

    #         summary = await compactor.compact_history(history_text)
    #         print(f"[系统] 摘要生成完成: {summary[:100]}...")
            
    #         # 3. 重构 Context
    #         # 保留 System Prompt
    #         system_events = []
    #         for evt in session.events:
    #             role = 'unknown'
    #             if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
    #                 role = evt.content.role
    #             if role == 'system':
    #                 system_events.append(evt)
    #             else:
    #                 break 
            
    #         # 构造摘要消息 (注入为 User 消息)
    #         if session.events:
    #             import copy
    #             # 复用一个 Event 对象以保持结构正确
    #             template_evt = session.events[-1] 
    #             new_evt = copy.deepcopy(template_evt)
    #             new_evt.content.role = 'user' 
    #             new_evt.content.parts = [types.Part(text=f"[System] Context compacted. Summary of previous conversation:\n{summary}")]
                
    #             new_events = system_events + [new_evt]
                
    #             print(f"[系统] 清理 Context: {len(session.events)} -> {len(new_events)}")
                
    #             # 更新 events
    #             if hasattr(session.events, 'clear') and hasattr(session.events, 'extend'):
    #                 session.events.clear()
    #                 session.events.extend(new_events)
    #             else:
    #                 session.events[:] = new_events
                
    #             # 持久化
    #             if isinstance(self.session_service, FullyCustomDbService):
    #                  await self.session_service.save_session(session)
                
    #     except Exception as e:
    #         print(f"[系统] 压缩失败: {e}")
    #         import traceback
    #         traceback.print_exc()

    
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
                # [DEBUG] Check DB ID
                print(f"[DEBUG] Session Object ID: {id(session)}")
            
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
            
            WARN_TURNS = 600
            MAX_TURNS = 700
            
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
                print(f"[DEBUG] Post-compact Session Object ID: {id(session)}")
            
            if tool_count > 12:
                print(f"\n[提醒] 已加载工具较多 ({tool_count})，建议卸载不常用的 skill")
            
            # [新增] 动态 Token 分配逻辑
            # 获取模型 Token 上限
            token_limit = self.config.max_context_tokens
            try:
                # 尝试动态获取
                model_name = self.config.model
                dynamic_limit = litellm.get_max_tokens(model_name)
                if dynamic_limit:
                    token_limit = dynamic_limit
                    # print(f"[系统] 模型 {model_name} Token 上限: {token_limit}")
            except:
                pass 
            
            # [Layer 1] 主动检查 Token 并在超限前压缩
            await self._check_and_compact_context(session, token_limit)

            if turn_count > WARN_TURNS and turn_count <= MAX_TURNS:
                task += "\n\n[System Note] Context is getting long. Please call 'smart_compact' tool."
            
            # 启动前检票
            self.interruption_guard()
            
            user_query = types.Content(role='user', parts=[types.Part(text=task)])
            run_config = RunConfig(streaming_mode=StreamingMode.SSE)
            
            logger.task_start(task)
            print(f"\n[任务] {task}")
            print("-" * 60)
            
            try:
                # 每次进入 Loop 前也检查一下 (防止 Function Call 产生的中间结果导致超限)
                await self._check_and_compact_context(session, token_limit)

                # =================================================================
                # [Merge Strategy] 将 Runner 的生成流与 StreamQueue 的旁路流合并
                # 这样 Tool 执行期间产生的消息也能实时推送到前端
                # =================================================================
                
                runner_queue = asyncio.Queue()
                
                async def _driver_coro():
                    try:
                        async for evt in runner.run_async(
                            user_id=self.user_id,
                            session_id=self.session_id,
                            new_message=user_query, # 只有第一次是 user_query, 后面由 Runner 管理
                            run_config=run_config
                        ):
                             await runner_queue.put(evt)
                        await runner_queue.put(None) # Sentinel for EOF
                    except Exception as e:
                        await runner_queue.put(e)

                driver_task = asyncio.create_task(_driver_coro())
                
                # 创建两个 listener task
                pending_runner_get = asyncio.create_task(runner_queue.get())
                pending_stream_get = asyncio.create_task(self.stream_queue.get())
                
                while True:
                    # 等待任意一个队列有消息
                    done, pending = await asyncio.wait(
                        [pending_runner_get, pending_stream_get], 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # 1. 处理 Runner 的消息 (LLM Token, Tool Call 等)
                    if pending_runner_get in done:
                        result = pending_runner_get.result()
                        
                        # 准备下一次获取
                        pending_runner_get = asyncio.create_task(runner_queue.get())
                        
                        if result is None:
                            # Runner 结束，退出循环
                            break
                        
                        elif isinstance(result, Exception):
                             # Runner 报错
                             if not pending_stream_get.done(): pending_stream_get.cancel()
                             driver_task.cancel()
                             raise result
                        
                        else:
                            # 正常 Event
                            self.interruption_guard()
                            chunks = _process_event_stream(result)
                            for chunk in chunks:
                                yield chunk

                    # 2. 处理 Side-Channel 消息 (Swarm Log, Progress 等)
                    if pending_stream_get in done:
                        event = pending_stream_get.result()
                        
                        # 准备下一次获取
                        pending_stream_get = asyncio.create_task(self.stream_queue.get())
                        
                        yield event

                # 清理
                if not pending_runner_get.done(): pending_runner_get.cancel()
                if not pending_stream_get.done(): pending_stream_get.cancel()
                # driver_task 应该已经结束了，不过保险起见
                if not driver_task.done(): driver_task.cancel()
        
            except ContextWindowExceededError:
                print(f"!!! [CRITICAL] Context Window Exceeded !!!")
                print(f"!!! [CRITICAL] 触发紧急压缩恢复流程 !!!")
                
                # [Layer 2] 异常兜底：紧急压缩
                session = await self._auto_compact_session(session)
                
                # 必须重新抛出或者想办法重试
                # 这里我们简单提示用户重试，因为完全自动重试整个流式请求比较复杂
                yield {"type": "text", "content": "\n\n[System] Context limit reached. Auto-compaction triggered. Please retry your request."}
                return

            except Exception as e:
                    raise e  # 交给外层处理常规异常
            
            except UserInterruption:
                was_interrupted = True
                print(f"\n🛑 [System] 任务已停止 ({self.key})")
                
                # 插入中断标记
                try:
                    from google.adk.sessions import Event
                    
                    # ===【关键修复】检查是否有未完成的 function_call ===
                    if session and hasattr(session, 'events') and session.events:
                        last_event = session.events[-1]
                        
                        # 检查最后一个 event 是否包含未完成的 function_call
                        has_pending_call = False
                        pending_calls = []
                        
                        if hasattr(last_event, 'content') and last_event.content and hasattr(last_event.content, 'parts'):
                            for part in last_event.content.parts:
                                if hasattr(part, 'function_call') and part.function_call:
                                    has_pending_call = True
                                    pending_calls.append(part.function_call)
                        
                        # 如果有未完成的调用,插入 synthetic FunctionResponse
                        if has_pending_call:
                            print(f"[System] 检测到 {len(pending_calls)} 个未完成的工具调用,正在补全...")
                            
                            response_parts = []
                            for fc in pending_calls:
                                # 构造 FunctionResponse
                                func_response = types.FunctionResponse(
                                    name=fc.name,
                                    id=fc.id if hasattr(fc, 'id') else None,
                                    response={"status": "cancelled", "message": "工具执行被用户中断"}
                                )
                                response_parts.append(types.Part(function_response=func_response))
                            
                            # 插入为 model role 的 event
                            response_content = types.Content(role='model', parts=response_parts)
                            response_event = Event(author='model', content=response_content)
                            session.events.append(response_event)
                            print(f"[System] 已补全 {len(pending_calls)} 个 FunctionResponse")
                    
                    # 插入中断标记(system 消息)
                    stop_content = types.Content(role="system", parts=[types.Part(text="[System] 用户主动中断了当前对话。")])
                    stop_event = Event(author="system", content=stop_content)
                    
                    if session and hasattr(session, 'events'):
                        session.events.append(stop_event)
                        print(f"[System] 已插入中断标记到历史记录")
                except Exception as e:
                    print(f"[Warning] Failed to append interruption history: {e}")
                
                yield {"type": "text", "content": "\n\n[已停止] 任务已取消。"}
                return
        
        except UserInterruption:
            # 这个块通常不会被到达，因为 run_task 内部有局部处理，但为了双重保险
            yield {"type": "text", "content": "\n\n[已停止] 任务已取消。"}
            return
            
        except Exception as e:
            # 过滤掉包含中断信息的特定错误字符串
            err_msg = str(e)
            if "User requested to stop operation" in err_msg:
                yield {"type": "text", "content": "\n\n[已停止] 任务已取消。"}
            else:
                logger.error(f"执行出错: {e}")
                yield f"[ERROR] {err_msg}"
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
                    from src.adk_agent.auto_compact_agent import AutoCompactAgent # Import here to avoid circular dependency
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
                            # [DEBUG] Verify what we just saved
                            print(f"[DEBUG] Saving session state. Events count: {len(session.events)}")
                            # [DEBUG] Immediate read-back verification
                            try:
                                test_load = await self.session_service.get_session(self.app_name, self.user_id, self.session_id)
                                print(f"[DEBUG] Immediate read-back event count: {len(test_load.events)}")
                            except Exception as e:
                                print(f"[DEBUG] Read-back failed: {e}")

                            if hasattr(session, 'events'):
                                print(f"[DEBUG] First event type: {type(session.events[0])}")
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

    # def find_session(self, app_name_pattern: str, user_id: str, session_id: str) -> Optional[SteeringSession]:
    #     """
    #     [New] 支持 app_name="*" 的模糊查找
    #     用于 Cancel 等操作，此时前端可能不知道确切的 app_name
    #     """
    #     if app_name_pattern == "*":
    #         # 遍历寻找匹配 user_id 和 session_id 的会话
    #         for key, session in self._sessions.items():
    #             # key = (app_name, user_id, session_id)
    #             if key[1] == user_id and key[2] == session_id:
    #                  print(f"[SessionManager] Fuzzy found session: {key}")
    #                  return session
    #         return None
    #     else:
    #         return self.get(app_name_pattern, user_id, session_id)


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

# async def skill_load(skill_id: str) -> str:
#     """
#     [DEPRECATED] 旧的 skill_load 函数，现在已废弃
#     新架构中 skill_load 是 SteeringSession 的实例方法
#     """
#     print(f"[WARNING] 调用了已废弃的全局 skill_load 函数")
#     return "[ERROR] 该函数已废弃，请使用 SteeringSession.skill_load"

async def create_agent(custom_config: AgentConfig = None):
    """
    [Restored] 初始化全局服务（session_service, sm, compactor_agent）
    虽然新架构中 Agent 由 SteeringSession 创建，但全局服务仍需在此初始化。
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
    
    # [物理隔离] 数据库文件名绑定端口
    db_filename = f"adk_sessions_port_{node_config.port}.db"
    db_path = os.path.join(db_folder, db_filename)
    if sys.platform == 'win32': db_path = db_path.replace('\\', '/')
        
    print(f"[Node-{node_config.port}] 🔒 挂载私有记忆库: {db_filename}")
    
    session_service = FullyCustomDbService(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        session_table_name="adk_sessions",
        event_table_name="adk_events"
    )
    await session_service.init_db()
    
    # 创建 AutoCompactAgent (Sub-Agent)
    compactor_agent = AutoCompactAgent(config)
    session_manager = SessionManager(config, session_service, sm, compactor_agent)
    print(f"[Node-{node_config.port}] ✅ 智能体就绪")

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
                chunks.append({
                    "type": "tool_call", 
                    "content": fc_msg,
                    "tool_name": fc.name,
                    "tool_args": fc.args
                })

            # 如果是结果 -> 正常发
            if hasattr(part, 'function_response') and part.function_response:
                fr = part.function_response
                result_content = part.function_response.response
                if isinstance(result_content, dict) and 'result' in result_content:
                    result_content = result_content['result']
                
                fc_tool_response_msg= f"{fr.name} -> {result_content}"
                print(f"[streaming_工具调用结果] {fc_tool_response_msg}")
                # Send clean string for streaming result too
                chunks.append({"type": "tool_result", "content": str(result_content)})

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
async def chat_endpoint(request: ChatRequest, response: Response):
    # 1. 检查是否忙碌
    if WORKER_LOCK.locked():
        # === 核心逻辑：智能忙碌响应 ===
        duration = 0
        if worker_state.start_time:
            duration = (datetime.datetime.now() - worker_state.start_time).seconds
        
        # 如果请求标记为【紧急中断】
        is_urgent_interrupt = "[URGENT_INTERRUPT]" in request.message

        if is_urgent_interrupt:
            print(f"[Node-{node_config.port}] ⚠️ 收到紧急中断指令！正在终止旧任务...")
            # 找到正在运行的 session 并发送 CANCEL
            if session_manager:
                busy_session = session_manager.get(request.app_name, request.user_id, worker_state.current_session_id)
                if busy_session:
                    await busy_session.queue.put("CANCEL") # 发送中断信号
                    # 等待一小会儿让它退出锁
                    # 轮询等待锁释放
                    for _ in range(20): # 最多等待 2秒
                        if not WORKER_LOCK.locked(): break
                        await asyncio.sleep(0.1)
            
            # 此时锁应该释放了（因为 run_agent 会抛出异常并 finally 释放）
        else:
            # 普通请求，返回详细的忙碌状态
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "error": "Worker is busy",
                "status": "busy",
                "current_task": worker_state.current_task_summary,
                "running_time_seconds": duration,
                "suggestion": "Append '[URGENT_INTERRUPT]' to message to force execution if the task is really urgent."
            }

    # 2. 抢锁并执行
    try:
        # 手动获取锁（确保在 generator 执行期间一直持有）
        await WORKER_LOCK.acquire()
        worker_state.set_busy(request.message[:50], request.session_id)
        print(f"[Node-{node_config.port}] 🔒 锁定: 开始执行任务 (Session: {request.session_id})")

        async def generate():
            try:
                # 传入完整的三元组
                async for chunk in run_agent(
                    request.message, 
                    request.app_name, 
                    request.user_id, 
                    request.session_id
                ):
                    yield json.dumps({"chunk": chunk}) + "\n"
            except Exception as e:
                yield json.dumps({"chunk": {"type": "error", "content": str(e)}}) + "\n"
            finally:
                # 释放锁
                worker_state.set_idle()
                WORKER_LOCK.release()
                print(f"[Node-{node_config.port}] 🔓 解锁: 任务结束，恢复空闲")

        return StreamingResponse(generate(), media_type="application/x-ndjson")
            
    except Exception as e:
        # 如果在获取锁或设置状态时出错，清理
        if WORKER_LOCK.locked() and worker_state.current_session_id == request.session_id:
             WORKER_LOCK.release()
             worker_state.set_idle()
        print(f"[Node-{node_config.port}] ❌ 执行异常: {e}")
        return {"error": str(e)}

# @app.post("/api/cancel")
# async def cancel_endpoint(req: CancelRequest):
#     """
#     [新架构] 接收取消指令，通过 SessionManager 定位会话并发送中断信号
#     """
#     global session_manager
    
#     if session_manager is None:
#         return {"status": "error", "message": "SessionManager not initialized"}
    
#     # 获取会话（不创建）
#     # [Fix] 支持 app_name="*"，以解决 Leader 和 Worker 之间 app_name 可能不一致的问题
#     session = session_manager.find_session(req.app_name, req.user_id, req.session_id)
    
#     # [Restored] 自动容错：如果精确查找失败且没用通配符，尝试全名空间搜索
#     if session is None and req.app_name != "*":
#         print(f"⚠️ [API] 精确查找失败 ({req.app_name})，尝试全局搜索...")
#         session = session_manager.find_session("*", req.user_id, req.session_id)
    
#     if session is None:
#         print(f"🛑 [API] 无法找到会话 -> {req.app_name}/{req.user_id}/{req.session_id}")
#         return {"status": "error", "message": "Session not found"}
    
#     # 向会话的队列发送中断信号
#     await session.queue.put("CANCEL")
#     print(f"🛑 [API] 收到 Cancel 信号 -> {req.app_name}/{req.user_id}/{req.session_id}")
#     return {"status": "success"}

@app.post("/api/cancel")
async def cancel_endpoint(req: CancelRequest):
    """
    [新架构] 接收取消指令，通过 SessionManager 定位会话并发送中断信号。
    [优化] 如果指定的 app_name 未找到会话，尝试在所有 app_name 中查找匹配的 session_id。
    """
    global session_manager
    
    if session_manager is None:
        return {"status": "error", "message": "SessionManager not initialized"}
    
    # 1. 尝试使用提供的参数精确查找
    session = session_manager.get(req.app_name, req.user_id, req.session_id)
    
    # 2. [新增] 容错逻辑：如果没找到，尝试忽略 app_name 全局搜索
    # 场景：Swarm Worker 任务的 app_name 是 'swarm_from_8000'，但前端可能传了 'dynamic_expert'
    if session is None:
        print(f"⚠️ [API] 精确查找失败 -> {req.app_name}/{req.user_id}/{req.session_id}，尝试全局搜索...")
        
        # 遍历所有 app_name 下的该 user_id
        # session_manager.sessions 结构: {app_name: {user_id: {session_id: session}}}
        # 注意：需要访问 session_manager 的内部结构，这违反了封装但为了修复 bug 必须这样做
        # 或者 session_manager 应该提供 find_session_by_id 接口。这里直接遍历。
        
        found_app_name = None
        for (a_name, u_id, s_id), sess in session_manager._sessions.items():
            if u_id == req.user_id and s_id == req.session_id:
                session = sess
                found_app_name = a_name
                break
        
        if session:
            print(f"✅ [API] 全局搜索成功！在 '{found_app_name}' 下找到会话")
        else:
            print(f"🛑 [API] 全局搜索也未找到会话 -> {req.session_id}")
            return {"status": "error", "message": "Session not found"}
    else:
        print(f"✅ [API] 精确查找成功 -> {req.app_name}")
    
    # 向会话的队列发送中断信号
    await session.queue.put("CANCEL")
    print(f"🛑 [API] 收到 Cancel 信号 -> {req.session_id} (Target App: {session.app_name if hasattr(session, 'app_name') else 'Found'})")
    return {"status": "success"}

class StopWorkerRequest(BaseModel):
    worker_port: int
    worker_session_id: str
    app_name: str
    user_id: str

@app.post("/api/stop_worker")
async def stop_remote_worker(request: StopWorkerRequest):
    """
    [New] Manually stop a specific remote worker
    """
    print(f"[API] Request to stop worker {request.worker_port} (Session: {request.worker_session_id})")
    
    # 1. Look up worker URL from DB
    worker_url = None
    try:
        with sqlite3.connect(REGISTRY_DB, timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM nodes WHERE port = ?", (request.worker_port,))
            row = cursor.fetchone()
            if row:
                worker_url = row[0]
    except Exception as e:
        return {"status": "error", "message": f"DB Lookup Failed: {str(e)}"}

    if not worker_url:
        return {"status": "error", "message": f"Worker {request.worker_port} not found in registry"}

    # 2. Call the worker's /api/cancel endpoint
    import httpx
    async with httpx.AsyncClient() as client:
        try:
            # The worker expects a CancelRequest with app_name, user_id, session_id
            # Note: The worker's session_id is specific to that task (sub-session)
            
            # Define CLUSTER_APP_NAME locally or use hardcoded value
            CLUSTER_APP_NAME = "adk_universal_swarm"
            
            payload = {
                "app_name": CLUSTER_APP_NAME, # Should match what dispatch_task uses
                "user_id": f"Agent_Node_{node_config.port}", # Should match dispatch_task caller_id
                "session_id": request.worker_session_id
            }
            # Actually, dispatch_task uses:
            # app_name=CLUSTER_APP_NAME ("adk_universal_swarm")
            # user_id=f"Agent_Node_{CURRENT_NODE_PORT}"
            # session_id=use_session_id
            
            # Since the worker validates (app_name, user_id, session_id) tuple for the session,
            # we must match EXACTLY what dispatch_task sent.
            # However, the user calling this API is the *human via browser*.
            # The provided request.app_name/user_id are the HUMAN's.
            # But the worker is working for the AGENT (Leader).
            
            # LUCKILY, `dispatch_task` in tools.py uses:
            # "app_name": CLUSTER_APP_NAME
            # "user_id": caller_id  (Agent_Node_X)
            # "session_id": use_session_id
            
            # The frontend calls /api/stop_worker with:
            # worker_session_id (which IS use_session_id from the init event)
            
            # So here we must reconstruct the credentials the Leader used to talk to the Worker.
            # We know CLUSTER_APP_NAME is "adk_universal_swarm" (defined in tools.py, but not imported here?)
            # Wait, CLUSTER_APP_NAME is in existing code? No.
            # But the worker code (main_web_start_steering.py) runs on the worker too.
            # It just checks if session matches.
            
            # Let's verify what dispatch_task sends.
            # tools.py: 
            # CLUSTER_APP_NAME = "adk_universal_swarm"
            # user_id = f"Agent_Node_{CURRENT_NODE_PORT}"
            
            # So in this /api/stop_worker (running on Leader), we need to emulate that.
            # We need to access node_config.port to construct user_id.
            
            # Correction: This file (main_web_start_steering.py) doesn't have CLUSTER_APP_NAME defined.
            # It is defined in tools.py.
            # I should define it here or hardcode it to match.
            
            swarm_app_name = "adk_universal_swarm"  # #swarm_app_name = "*"
            leader_user_id = f"Agent_Node_{node_config.port}"
            
            print(f" -> Sending Cancel to {worker_url} for {swarm_app_name}/{leader_user_id}/{request.worker_session_id}")

            resp = await client.post(
                f"{worker_url}/api/cancel",
                json={
                    "app_name": swarm_app_name,
                    "user_id": leader_user_id,
                    "session_id": request.worker_session_id
                },
                timeout=5.0
            )
            
            if resp.status_code == 200:
                print(" -> Success")
                return {"status": "success"}
            else:
                print(f" -> Failed: {resp.text}")
                return {"status": "error", "message": f"Worker responded {resp.status_code}: {resp.text}"}
                
        except Exception as e:
            print(f" -> Exception: {e}")
            return {"status": "error", "message": str(e)}

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
    """删除会话，支持自动查找 app_name"""
    
    # 尝试直接删除
    try:
        # Check if session exists first to decide if we need fallback
        session = await session_service.get_session(app_name, user_id, session_id)
        
        target_app_name = app_name
        
        # Fallback logic if not found default way
        if not session:
             print(f"⚠️ [API] 删除会话：精确查找失败 -> {app_name}/{user_id}/{session_id}，尝试全局搜索...")
             
             # Use the newly fixed wildcard search
             all_sessions_resp = await session_service.list_sessions(
                 app_name="*", 
                 user_id=user_id
             )
             
             for s in all_sessions_resp.sessions:
                 if s.id == session_id:
                     target_app_name = s.app_name
                     print(f"✅ [API] 全局搜索成功！在 '{target_app_name}' 下找到会话")
                     # Found it, we can proceed to delete
                     break
        
        await session_service.delete_session(
            app_name=target_app_name,
            user_id=user_id,
            session_id=session_id
        )
        return {"status": "success"}
    except Exception as e:
        print(f"❌ [API] 删除会话失败: {e}")
        return {"status": "error", "message": str(e)}

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

    # [新增] 容错逻辑：如果没找到，尝试忽略 app_name 全局搜索
    # [新增] 容错逻辑：如果没找到，尝试忽略 app_name 全局搜索
    if not session:
         print(f"⚠️ [API] 历史查找：精确查找失败 -> {app_name}/{user_id}/{session_id}，尝试全局搜索...")
         
         # Use wildcard search
         all_sessions_resp = await session_service.list_sessions(
             app_name="*", 
             user_id=user_id
         )
         
         target_app_name = None
         for s in all_sessions_resp.sessions:
             if s.id == session_id:
                 target_app_name = s.app_name
                 print(f"✅ [API] 全局搜索成功！在 '{target_app_name}' 找到会话")
                 break
         
         if target_app_name:
             session = await session_service.get_session(
                app_name=target_app_name,
                user_id=user_id,
                session_id=session_id
            )
    
    if not session:
        return {"messages": []}
    
    messages = []
    for event_idx, event in enumerate(session.events):
        if hasattr(event, 'content') and event.content:
            role = 'unknown'
            if hasattr(event.content, 'role'):
                role = event.content.role
            elif hasattr(event, 'author'):
                role = event.author
            
            # 提取文本内容
            text_content = ""
            blocks = []
            
            # [调试日志] 输出 event 的详细信息
            print(f"\n[历史消息调试] Event {event_idx} - Role: {role}")
            print(f"[历史消息调试] Event {event_idx} - Content 类型: {type(event.content)}")
            
            if hasattr(event.content, 'parts'):
                print(f"[历史消息调试] Event {event_idx} - Parts 数量: {len(event.content.parts)}")
                for part_idx, part in enumerate(event.content.parts):
                    print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 类型: {type(part)}")
                    
                    # 检查 text
                    if hasattr(part, 'text') and part.text:
                        print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 有 text (长度:{len(part.text)})")
                        # 检查是否是思考过程
                        if getattr(part, 'thought', False):
                            blocks.append({"type": "thought", "content": part.text})
                        else:
                            blocks.append({"type": "text", "content": part.text})
                            text_content += part.text
                    
                    # 检查 function_call
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 有 function_call: {fc.name}")
                        blocks.append({
                            "type": "tool_call",
                            "content": f"{fc.name} 输入参数: {fc.args}",
                            "tool_name": fc.name,
                            "tool_args": fc.args
                        })
                    
                    # 检查 function_response
                    if hasattr(part, 'function_response'):
                        print(f"[历史消息调试] Event {event_idx} Part {part_idx} - hasattr(function_response): True")
                        print(f"[历史消息调试] Event {event_idx} Part {part_idx} - function_response value: {part.function_response}")
                        if part.function_response:
                            fr = part.function_response
                            print(f"[历史消息调试] Event {event_idx} Part {part_idx} - function_response name: {fr.name}")
                            
                            # [Fix] Add 'tool_result_clean' field for frontend parsing, separate from raw 'content'
                            result_clean = None
                            result_display = fr.response
                            
                            if isinstance(fr.response, dict) and 'result' in fr.response:
                                result_clean = fr.response['result']
                                result_display = result_clean # Use clean string for display too!
                            
                            blocks.append({
                                "type": "tool_result",
                                "content": str(result_display), # Send string so script.js can marked.parse() it
                                "tool_result_clean": str(result_clean) if result_clean else None
                            })
                        else:
                            print(f"[历史消息调试] Event {event_idx} Part {part_idx} - function_response 是 None")
                    else:
                        print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 没有 function_response 属性")
            
            print(f"[历史消息调试] Event {event_idx} - 最终 blocks 数量: {len(blocks)}")
            for block_idx, block in enumerate(blocks):
                print(f"[历史消息调试] Event {event_idx} Block {block_idx}: type={block['type']}")
            
            # 合并连续的相同类型的 blocks（特别是 thought 和 text）
            merged_blocks = []
            for block in blocks:
                # 如果 merged_blocks 为空，或者当前 block 类型与上一个不同，直接添加
                if not merged_blocks or merged_blocks[-1]['type'] != block['type']:
                    merged_blocks.append(block)
                else:
                    # 如果类型相同，合并 content（只合并 thought 和 text）
                    if block['type'] in ['thought', 'text']:
                        merged_blocks[-1]['content'] += block['content']
                    else:
                        # tool_call 和 tool_result 不合并，直接添加
                        merged_blocks.append(block)
            
            print(f"[历史消息调试] Event {event_idx} - 合并后 blocks 数量: {len(merged_blocks)}")
            
            # [关键修复] 如果消息只包含 tool_result，则强制 role 为 'model'
            # 原因：Google ADK 中 function_response 的 role 是 'user'，但从 UI 角度看
            # tool_result 应该和 tool_call 一样在左侧对齐（都是系统操作）
            only_tool_results = all(block['type'] == 'tool_result' for block in merged_blocks) if merged_blocks else False
            if only_tool_results and role == 'user':
                print(f"[历史消息调试] Event {event_idx} - 检测到只包含 tool_result，将 role 从 'user' 改为 'model'")
                role = 'model'
            
            if role == 'user' or role == 'model':
                messages.append({
                    "role": role,
                    "blocks": merged_blocks,  # 使用合并后的 blocks
                    "text": text_content  # 兼容性字段
                })
    
    return {"messages": messages}

# ==========================================
# [新增] Swarm 上下文同步相关 API
# ==========================================

@app.post("/api/sessions/{session_id}/metadata")
async def update_session_metadata(
    session_id: str,
    request: Request
):
    """
    【任务血缘记录】接收来自 Leader 的元数据注入
    在 Worker 节点的 session.state 中记录 leader_port, original_user_id 等信息
    """
    data = await request.json()
    app_name = data.get("app_name", DEFAULT_APP_NAME)
    user_id = data.get("user_id", DEFAULT_USER_ID)
    metadata = data.get("metadata", {})
    
    try:
        # 获取或创建 session
        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
        
        if not session:
            # 如果 session 不存在，创建一个新的
            session = await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
        
        # 更新 state，保留原有数据并合并新元数据
        current_state = session.state if session.state else {}
        current_state.update(metadata)
        
        # 保存更新后的 state
        session.state = current_state
        await session_service.save_session(session)
        
        print(f"[Swarm Metadata] ✅ Session {session_id} 元数据已更新: {metadata}")
        return {"status": "success", "message": "Metadata updated"}
        
    except Exception as e:
        print(f"[Swarm Metadata] ❌ 更新失败: {e}")
        return {"status": "error", "message": str(e)}, 500


@app.get("/api/context/leader_summary")
async def get_leader_summary(
    app_name: str = DEFAULT_APP_NAME,
    user_id: str = DEFAULT_USER_ID,
    limit: int = 1
):
    """
    【跨节点上下文查询】支持 app_name="*" 进行全名空间搜索
    """
    try:
        # 调试日志
        print(f"[Leader Summary API] 收到请求: app_name={app_name}, user_id={user_id}")
        
        # 1. 查询最近的会话 (这里 app_name 可能是 "*")
        sessions_response = await session_service.list_sessions(app_name=app_name, user_id=user_id)
        sessions = sessions_response.sessions if sessions_response else []
        
        if not sessions or len(sessions) == 0:
            print(f"[Leader Summary API] 未找到会话")
            return {"error": "No sessions found"}
        
        # 取最新的 session
        if limit == 1:
            latest_session_meta = sessions[0]
            
            # === [关键修改开始] ===
            # 因为 list_sessions 可能用了 "*" 查出来的，
            # 我们必须用查出来的真实 app_name 去调用 get_session 加载详情
            real_app_name = latest_session_meta.app_name
            real_session_id = latest_session_meta.id
            
            print(f"[Leader Summary API] 锁定最新会话: {real_app_name} / {real_session_id}")
            
            latest_session = await session_service.get_session(
                app_name=real_app_name, # <--- 使用真实的 app_name
                user_id=user_id,
                session_id=real_session_id
            )
            # === [关键修改结束] ===
            
            if not latest_session:
                latest_session = latest_session_meta
            
            # 提取最近的对话消息 (保持原样)
            recent_messages = []
            if latest_session.events:
                for evt in latest_session.events[:]:
                    if hasattr(evt, 'content') and evt.content:
                        role = evt.content.role if hasattr(evt.content, 'role') else 'unknown'
                        text = ""
                        if hasattr(evt.content, 'parts'):
                            for part in evt.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    text += part.text
                        if text:
                            recent_messages.append({
                                "role": role,
                                "text": text[:]
                            })
            
            summary_lines = []
            for msg in recent_messages:
                prefix = "👤 用户" if msg["role"] == "user" else "🤖 助手"
                summary_lines.append(f"{prefix}: {msg['text']}")
            
            result = {
                "title": latest_session.state.get('title', 'Untitled') if latest_session.state else 'Untitled',
                "session_id": latest_session.id,
                "app_name": latest_session.app_name, # 返回真实的 app_name 供调试
                "recent_summary": " ".join(summary_lines),
                "total_messages": len(latest_session.events) if latest_session.events else 0
            }
            return result
        else:
            # (处理多个会话的逻辑保持原样，如果有的话)
            return {"sessions": [{"id": s.id} for s in sessions[:limit]]}
            
    except Exception as e:
        print(f"[Swarm Context API] ❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

#暂时没用到
@app.get("/health")
async def health_check():
    """轻量级健康检查接口"""
    if WORKER_LOCK.locked():
        return {"status": "busy", "task": worker_state.current_task_summary}
    return {"status": "ok", "port": node_config.port}

@app.on_event("startup")
async def startup_event():
    init_registry_db()
    await create_agent()
    register_self()
    asyncio.create_task(heartbeat_daemon())
    print(f"[Node-{node_config.port}] 🚀 服务已完全启动 (已加入 Swarm, Heartbeat ON)")

@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

@app.on_event("shutdown")
async def shutdown_event():
    deregister_self()

def start_web_server(port: int):
    print(f"Starting web server at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    
    node_config.port = args.port
    
    # 【核心】注入环境变量，解耦工具
    os.environ["ADK_CURRENT_PORT"] = str(args.port)
    
    print(f"=== 🚀 启动通用全能智能体节点 ===")
    print(f"🏠 端口: {node_config.port}")
    print(f"💾 隔离数据库: adk_sessions_port_{node_config.port}.db")
    start_web_server(node_config.port)
