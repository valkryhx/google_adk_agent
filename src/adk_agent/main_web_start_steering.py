"""
ADK Dynamic Skills Agent - 主入口 (多租户并发安全版)

修正点：
1. Session 识别升级：使用 (app_name, user_id, session_id) 三元组。
2. claudecode风格的steering实时文本打断增强：在流式输出循环中增加强制检查。
3. AOP 拦截：使用 before_model/tool callback。

python -m src.adk_agent.main_web_start_steering  [--port 8000]
"""

import asyncio
import os
import sys
import json
import time
import secrets
import sqlite3
import functools
import re
import uuid
from pathlib import Path
from contextvars import ContextVar
from typing import Dict, Tuple, Optional, Any, List
import base64 as b64_module
# 将当前目录添加到路径
#sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 将项目根目录添加到路径 (3层目录向上)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

if sys.platform == "win32":
    import codecs
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

import argparse
from src.adk_agent.core.manager import SkillManager
from src.adk_agent.core.executor import execute_python_code
from src.adk_agent.core.logger import AgentLogger, logger
from src.adk_agent.core.simple_file_logger import default_logger as file_logger
from src.adk_agent.config import AgentConfig, build_system_prompt, yaml_config
from src.adk_agent.stream_dedup import (
    dedupe_textual_event_chunks,
    strip_leaked_think_from_text,
)
import litellm
from litellm import ContextWindowExceededError
from google.genai import types
from fastapi import FastAPI, Response, status, Request, WebSocket, WebSocketDisconnect
import numpy as np
import sherpa_onnx
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import datetime

from google.adk.agents import LlmAgent
from google.adk import Runner
from src.shared.db.custom_table_db_service import FullyCustomDbService
from google.adk.models.lite_llm import LiteLlm
from src.adk_agent.auto_compact_agent import AutoCompactAgent
from src.adk_agent.kairos.activity_log import KairosActivityLog
from src.adk_agent.kairos.api import register_kairos_routes
from src.adk_agent.kairos.dex_bridge import KairosDexBridge
from src.adk_agent.kairos.document_protocol import append_spawned_work_update
from src.adk_agent.kairos.llm_planner import KairosPlanner
from src.adk_agent.kairos.llm_verifier import KairosVerifier
from src.adk_agent.kairos.models import (
    DocumentReadResult,
    StepAttempt,
    dump_kairos_state,
    load_kairos_state,
)
from src.adk_agent.kairos.runtime import KairosRuntime
from src.adk_agent.kairos.workflows import demo_report_pipeline
from skills.dex.tools import _normalize_command_args

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

# ==========================================
# [新增] 本地经验库配置 (OpenViking-Lite 架构)
# ==========================================
# 1. 经验池根目录 (存放分类文件夹)
SHARED_GENE_POOL = os.path.join(_PROJECT_ROOT, "agent_experiences")
# 2. 全局索引文件 (存放 L0 摘要数据，用于极速检索)
EXPERIENCE_INDEX_PATH = os.path.join(SHARED_GENE_POOL, "index_manifest.json")
# 3. 经验提取过程日志目录 (与 agent_experiences 平级)
EXPERIENCE_LOG_DIR = os.path.join(_PROJECT_ROOT, "agent_exp_extract_logs")

# 自动初始化目录
os.makedirs(SHARED_GENE_POOL, exist_ok=True)
os.makedirs(EXPERIENCE_LOG_DIR, exist_ok=True)

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
# [新增] 安全并发写总索引的后台进程函数
# ==========================================
import tempfile
import shutil
from filelock import FileLock
import json

def _sync_safe_update_manifest(lock_path: str, index_path: str, gene_id: str, category: str, gene_data: dict):
    """
    负责加锁、读取、合并与原子写入经验索引的同步阻塞函数 (必须交由子线程执行)
    """
    with FileLock(lock_path, timeout=10):
        manifest = {}
        
        # 1. 抢到锁后安全读取
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
            except Exception as e:
                # 灾难熔断与备份防擦除
                if os.path.getsize(index_path) > 0:
                    backup_path = f"{index_path}.corrupted.bak"
                    shutil.copy2(index_path, backup_path)
                    print(f"[严重警告] L0总索引加载失败: {e} | 已抢救备份旧版本至: {backup_path}")
                # 放行空字典用于重建，但老数据安全在了 .bak 中
                manifest = {}
        
        # 2. 追加最新经验
        manifest[gene_id] = {
            "path": f"{category}/{gene_id}.json",
            "category": category,
            "title": gene_data.get("title", ""),
            "keywords": gene_data.get("keywords", []),
            "error_regex": gene_data.get("trigger_error_regex", "")
        }
        
        # 3. 原子操作 (Atomic Write)
        # 先找同级目录建一个隐式同名或后缀临时文件，保文件不出跨区移动问题
        fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(index_path), text=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            
            # 只有当完整写入 temp 后，再命令 OS 一瞬间做原地替换！
            os.replace(temp_path, index_path) 
        except Exception as e:
            # 写入遇到任何意外，清理临时碎片，绝不玷污原始 index_path
            shutil.rmtree(temp_path, ignore_errors=True) 
            raise e


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
        
        # 获取事件循环以供跨线程调用
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        self._current_session = None # [New] 跟踪当前正在执行任务的 Session 对象
        self._loaded_skills = []  # [Fix] 更改为 list 以严格保持动态技能的物理加载顺序
        self.kairos_runtime = None

        # 创建会话专属的 Agent（内部会创建自己的 compactor）
        self.agent = self._create_agent()

        print(f"[SteeringSession] Created session for {self.key}")

    def _append_debug_log(self, message: str):
        try:
            with open(r"d:\git_codes\google_adk_helloworld_git\tmp\debug_steering.log", "a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception:
            pass

    def _tool_names_snapshot(self):
        if not hasattr(self, 'agent') or not self.agent or not hasattr(self.agent, 'tools'):
            return []
        return [getattr(t, 'name', getattr(t, '__name__', str(t))) for t in self.agent.tools]

    def _restore_dynamic_skills(self):
        if not hasattr(self, '_loaded_skills') or not self._loaded_skills:
            return

        self._append_debug_log(f"[Debug] 🔄 正在恢复动态技能工具 | _loaded_skills: {self._loaded_skills}")
        print(f"[SteeringSession] 正在自动恢复动态技能工具: {self._loaded_skills}")

        for sid in self._loaded_skills:
            before_tools = self._tool_names_snapshot()
            loaded_tools = self._load_skill_tools(sid)
            after_tools = self._tool_names_snapshot()
            new_tools = [name for name in after_tools if name not in before_tools]
            diag = getattr(self, '_last_skill_load_diagnostics', {}).get(sid, {})
            status = diag.get('status', 'unknown')
            log_line = (
                f"[Debug] 🔁 动态技能恢复结果 | session={self.key} skill={sid} status={status} "
                f"new_tools={new_tools} before_count={len(before_tools)} after_count={len(after_tools)} "
                f"force_reload={diag.get('force_reload')} error_type={diag.get('error_type')} error={diag.get('error')}"
            )
            self._append_debug_log(log_line)
            print(log_line)

    def update_llm_config(self, model: str = None, api_key: str = None, api_base: str = None, active_model: str = None):
        """[Dynamic Config] 动态更新会话的 LLM 配置并重启 Agent"""
        try:
            with open(r"d:\git_codes\google_adk_helloworld_git\tmp\debug_steering.log", "a", encoding="utf-8") as f:
                before_tools = [getattr(t, 'name', getattr(t, '__name__', str(t))) for t in self.agent.tools] if hasattr(self, 'agent') and self.agent else []
                f.write(f"\n[Debug] 🚀 update_llm_config 触发 | 会话 Key: {self.key}\n")
                f.write(f"[Debug] 🔄 切换前工具列表 ({len(before_tools)}): {before_tools}\n")
        except Exception: pass
        if active_model: self.config.active_model = active_model
        if model: self.config.model = model
        if api_key: self.config.api_key = api_key
        if api_base: self.config.api_base = api_base
        
        # 重新创建 Agent 以应用新配置
        print(f"[{self.key}] 正在应用新配置: model={self.config.model}, base={self.config.api_base}, active_tag={self.config.active_model}")
        self.agent = self._create_agent()
        try:
            with open(r"d:\git_codes\google_adk_helloworld_git\tmp\debug_steering.log", "a", encoding="utf-8") as f:
                after_tools = [getattr(t, 'name', getattr(t, '__name__', str(t))) for t in self.agent.tools]
                f.write(f"[Debug] ✅ 切换后工具列表 ({len(after_tools)}): {after_tools}\n")
        except Exception: pass

    def report_swarm_event(self, event_type: str, payload: dict):
        """
        供 Tool 调用的回调函数，用于实时汇报 Swarm 状态。
        消息会被放入 stream_queue，最终合并到 HTTP SSE 流中推给前端。
        """
        # [New] 处理内部状态更新信号 (非侵入式打标核心)
        if event_type == "update_session_state" and self._current_session:
            if not self._current_session.state: self._current_session.state = {}
            self._current_session.state.update(payload)
            print(f"[Steering] Session {self.session_id} state updated via signal: {payload}")
            return # 信号已处理，无需推送到 UI

        print(f"[SteeringSession] Reporting Event: {event_type}")
        event = {
            "type": "swarm_event",
            "sub_type": event_type, # init, chunk, finish, fail
            "data": payload
        }
        # 使用 call_soon_threadsafe 确保跨线程调用的安全性
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._safe_put_event, event, event_type)
        else:
            self._safe_put_event(event, event_type)

    def _safe_put_event(self, event, event_type):
        print(f"[SteeringSession] 🎯 safe_put_event executed for: {event_type}")
        try:
            self.stream_queue.put_nowait(event)
        except asyncio.QueueFull:
            print(f"[SteeringSession] ⚠️ stream_queue full, dropping event: {event_type}")

    async def _persist_session_state(self, state: dict):
        if isinstance(self.session_service, FullyCustomDbService):
            return await self.session_service.save_session_state(
                app_name=self.app_name,
                user_id=self.user_id,
                session_id=self.session_id,
                state=state,
            )

        session = await self.session_service.get_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=self.session_id,
        )
        if not session:
            session = await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
                session_id=self.session_id,
            )
        session.state = dict(state or {})
        await self.session_service.save_session(session)
        return session

    async def _save_kairos_state(self, kairos_state):
        session = await self.session_service.get_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=self.session_id,
        )
        current_state = dict(session.state or {}) if session and getattr(session, "state", None) else {}
        current_state["kairos"] = dump_kairos_state(kairos_state)
        persisted_session = await self._persist_session_state(current_state)
        self._current_session = persisted_session

    async def _emit_kairos_event(self, event):
        self.report_swarm_event(
            "kairos_event",
            {"kind": event.kind, "message": event.message, "ts": event.ts, "level": event.level},
        )

    async def _append_kairos_log(self, event):
        project_root = Path(__file__).resolve().parents[2]
        KairosActivityLog(project_root).append_entry(
            user_id=self.user_id,
            app_name=self.app_name,
            session_id=self.session_id,
            kind=event.kind,
            message=event.message,
            ts=event.ts,
        )


    async def create_kairos_follow_up_task(self, description: str, trigger_reason: str, payload: dict | None = None):
        runtime = self.get_or_create_kairos_runtime()
        dex = KairosDexBridge(base_dir=_PROJECT_ROOT, user_id=self.user_id).manager
        task = dex.create_task(description, f"kairos follow-up: {trigger_reason}")
        payload = dict(payload or {})
        if description == "generate final report":
            command = (
                'python -c "import json,os; data={}; files=[\'sales\',\'traffic\',\'quality\']; '
                "[data.setdefault(name, json.load(open(f'demo_outputs/{name}.json', encoding='utf-8'))) for name in files]; "
                "report={'report':'ready','inputs':files,'summary':{'sales':data['sales']['value'],'traffic':data['traffic']['value'],'quality':data['quality']['value']}}; "
                "json.dump(report, open('demo_outputs/report.json','w',encoding='utf-8'), ensure_ascii=False, indent=2); "
                "print('report ready: 3 inputs merged')\""
            )
            dex.start_background_process(task["id"], _normalize_command_args(command))
        elif description == "generate todo delivery report":
            command = (
                "python -c \"from pathlib import Path; import json; root=Path('demo_delivery/todo_app'); "
                "requirements=(root/'requirements.md').read_text(encoding='utf-8'); "
                "design=(root/'design.md').read_text(encoding='utf-8'); "
                "smoke=json.loads((root/'smoke_check.json').read_text(encoding='utf-8')); "
                "report=(root/'delivery_report.md'); "
                "report.write_text('# Todo Delivery Report\\n\\n' + "
                "'Requirements captured: ' + str(bool(requirements.strip())) + '\\n' + "
                "'Design captured: ' + str(bool(design.strip())) + '\\n' + "
                "'Ready: ' + str(smoke.get('ready', False)) + '\\n', encoding='utf-8'); "
                "print('todo delivery report ready')\""
            )
            dex.start_background_process(task["id"], _normalize_command_args(command))
        await runtime.register_dex_task(task["id"], description)
        runtime.state.planned_actions = [
            action
            for action in runtime.state.planned_actions
            if not (
                action.kind in {"create_dex_task", "run_dex_task"}
                and (
                    (
                        action.payload.get("workflow_id") == payload.get("workflow_id")
                        and action.payload.get("description") == description
                    )
                    or (
                        action.payload.get("work_id") == payload.get("work_id")
                        and action.payload.get("step_id") == payload.get("step_id")
                        and action.payload.get("description") == description
                    )
                )
            )
        ]
        if runtime.state.active_workflow:
            target_stage_id = "phase2" if description == "generate final report" else "delivery_report"
            for stage in runtime.state.active_workflow.stages:
                if stage.stage_id == target_stage_id:
                    stage.task_ids = [task["id"]]
                    stage.status = "running"
                    break

        source_doc = payload.get("source_doc")
        if source_doc:
            source_doc_path = Path(_PROJECT_ROOT) / source_doc
            current_step = payload.get("step_id") or payload.get("current_step") or "follow_up"
            work_item = DocumentReadResult(
                work_id=payload.get("work_id") or f"work:{self.session_id}:{task['id']}",
                goal=payload.get("goal") or description,
                status=payload.get("status", "in_progress"),
                current_step=current_step,
                next_actions=list(payload.get("next_actions", [])) or [description],
                blockers=list(payload.get("blockers", [])),
                expected_artifacts=list(payload.get("expected_artifacts", [])) or [source_doc],
                open_questions=list(payload.get("open_questions", [])),
                human_input_required=bool(payload.get("human_input_required", False)),
                source_docs=[source_doc],
            )
            append_spawned_work_update(
                source_doc_path,
                trigger_reason=trigger_reason,
                work_item=work_item,
            )
            runtime.state.document_work_items = [
                item for item in runtime.state.document_work_items if item.work_id != work_item.work_id
            ]
            runtime.state.document_work_items.insert(0, work_item)
            if hasattr(runtime.state, "step_attempts"):
                doc_fingerprint = str(payload.get("doc_fingerprint", ""))
                for attempt in runtime.state.step_attempts:
                    if (
                        attempt.work_id == work_item.work_id
                        and attempt.step_id == current_step
                        and attempt.action_kind == "run_dex_task"
                        and attempt.status == "pending"
                        and attempt.doc_fingerprint == doc_fingerprint
                    ):
                        attempt.status = "started"
                        attempt.result_summary = f"dex task {task['id']} created"
                        break
                else:
                    runtime.state.step_attempts.append(
                        StepAttempt(
                            attempt_id=f"attempt-{work_item.work_id}-{current_step}",
                            work_id=work_item.work_id,
                            step_id=current_step,
                            action_kind="run_dex_task",
                            status="started",
                            doc_fingerprint=doc_fingerprint,
                            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
                            result_summary=f"dex task {task['id']} created",
                        )
                    )
            runtime._continuation_engine.refresh_unfinished_work(runtime.state)
            await runtime._record(
                "brief",
                f"spawned work persisted work_id={work_item.work_id} workflow_id={payload.get('workflow_id', 'document_requirement')} stage_id={work_item.current_step or 'follow_up'} source_doc={source_doc}",
            )
        await self._save_kairos_state(runtime.state)
        await runtime._record(
            "brief",
            f"kairos auto-created dex task {task['id']}: {description} ({trigger_reason})",
        )
        return task

    @staticmethod
    def _build_kairos_tick_prompt(
        reason: str,
        workflow_summary: str,
        unfinished_work_summary: str,
        policy_summary: str,
    ) -> str:
        return (
            "[KAIROS_TICK]\n"
            f"reason={reason}\n"
            "You are in assistant runtime mode for long-running autonomous work.\n"
            f"workflow={workflow_summary}\n"
            f"unfinished work={unfinished_work_summary}\n"
            f"policy={policy_summary}\n"
            "Check unfinished work first.\n"
            "If there is a high-value next action within policy, continue it.\n"
            "If user input is required, produce a concise ask-user brief.\n"
            "If there is useful progress to surface, produce a concise proactive brief.\n"
            "If there is no high-value work right now, sleep immediately.\n"
            "Never emit empty status narration.\n"
        )

    async def run_kairos_turn(self, reason: str):
        """
        执行 KAIROS autonomous turn，但不污染 session.events。

        关键修复：
        - KAIROS tick 是后台自治检查，不应该记录到用户的对话历史中
        - 执行前后保存/恢复 session.events，避免历史膨胀
        - 结果只写入 recent_events 和 activity log
        """
        runtime = self.get_or_create_kairos_runtime()
        workflow = runtime.state.active_workflow
        workflow_summary = "none"
        if workflow:
            workflow_summary = workflow.workflow_id
            if workflow.current_stage:
                workflow_summary = f"{workflow.workflow_id}: {workflow.current_stage}"
        unfinished_work_summary = ", ".join(
            item.get("stage_id", item.get("work_id", "unknown"))
            for item in runtime.state.unfinished_work_items[:3]
        ) or "none"
        policy_summary = (
            f"cooldown={runtime.state.policy.cooldown_seconds} "
            f"max_auto_steps_per_tick={runtime.state.policy.max_auto_steps_per_tick} "
            f"dedupe={runtime.state.policy.dedupe_enabled}"
        )
        synthetic_prompt = self._build_kairos_tick_prompt(
            reason=reason,
            workflow_summary=workflow_summary,
            unfinished_work_summary=unfinished_work_summary,
            policy_summary=policy_summary,
        )

        # 执行 turn，开启沙盒隔离模式，由底层屏蔽向真实数据库写入中间思考事件
        async for _ in self._run_agent_turn(
            synthetic_prompt, images=None, yield_chunks=False,
            is_sandbox_turn=True
        ):
            pass

        return "ok"

    def get_or_create_kairos_runtime(self):
        if self.kairos_runtime is not None:
            return self.kairos_runtime

        raw = {}
        if self._current_session and getattr(self._current_session, "state", None):
            raw = self._current_session.state.get("kairos", {})

        from src.adk_agent.kairos.scheduler import KairosScheduler

        self.kairos_runtime = KairosRuntime(
            state=load_kairos_state(raw),
            save_state=self._save_kairos_state,
            emit_event=self._emit_kairos_event,
            append_log=self._append_kairos_log,
            run_turn=self.run_kairos_turn,
            dex_bridge=KairosDexBridge(base_dir=_PROJECT_ROOT, user_id=self.user_id),
            tick_interval_seconds=15.0,
            is_worker_busy=lambda: WORKER_LOCK.locked(),
            scheduler=KairosScheduler(),
            create_follow_up_task=lambda reason, payload: self.create_kairos_follow_up_task(
                payload.get("description", "generate final report"),
                reason,
                payload,
            ),
        )
        planner_config = getattr(self, "config", None)
        if planner_config is not None:
            self.kairos_runtime._llm_planner = KairosPlanner(
                model=planner_config.model,
                api_key=planner_config.api_key,
                api_base=planner_config.api_base,
                extra_body=planner_config.extra_body,
                timeout_seconds=planner_config.timeout_seconds,
                max_retries=planner_config.max_retries,
            )
            self.kairos_runtime._llm_verifier = KairosVerifier(self.kairos_runtime._llm_planner)
            self.kairos_runtime.state.policy.llm_only_decision_enabled = True
        self.kairos_runtime._path_exists = lambda path: Path(_PROJECT_ROOT, path).exists()
        self.kairos_runtime._continuation_engine._path_exists = self.kairos_runtime._path_exists
        return self.kairos_runtime

    def _create_agent(self) -> LlmAgent:
        """创建会话专属的 LlmAgent 实例"""
        # [Fix] 备份旧 agent 里的运行时动态工具集 (如 McpToolset)，防止重启时丢失
        dynamic_toolsets = []
        if hasattr(self, 'agent') and self.agent:
            try:
                for t in self.agent.tools:
                    if type(t).__name__ == "McpToolset": # 兼容 dynamic-mcp 产生的副作用工具
                        dynamic_toolsets.append(t)
                if dynamic_toolsets:
                    with open(r"d:\git_codes\google_adk_helloworld_git\tmp\debug_steering.log", "a", encoding="utf-8") as f:
                        f.write(f"[Debug] 📦 发现并暂存旧运行时的 McpToolset: {len(dynamic_toolsets)} 个\n")
            except Exception as e:
                print(f"[SteeringSession] ⚠️ 备份旧工具集失败: {e}")

        system_prompt = build_system_prompt(self.config, self.skill_manager.get_discovery_manifests(), user_id=self.user_id)
        
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
            tools=[self.skill_load, self.skill_reload],  # 绑定实例方法
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

        # 🔑 自动加载 search_exp 作为第4个内置核心工具
        try:
            exp_tools = self._load_skill_tools('search_exp')
            print(f"[SteeringSession] 已自动加载 search_exp 工具: {[t.__name__ for t in exp_tools]}")
        except Exception as e:
            print(f"[SteeringSession] ⚠️ 加载 search_exp 失败: {e}")
        
        # [Fix] 恢复之前动态加载的技能
        self._restore_dynamic_skills()

        # [Fix] 恢复运行时动态工具集 (McpToolset 副作用工具)
        if 'dynamic_toolsets' in locals() and dynamic_toolsets:
            print(f"[SteeringSession] 正在自动迁移运行时动态工具集: {len(dynamic_toolsets)} 个")
            try:
                agent.tools.extend(dynamic_toolsets)
                with open(r"d:\git_codes\google_adk_helloworld_git\tmp\debug_steering.log", "a", encoding="utf-8") as f:
                    f.write(f"[Debug] 📦 已成功迁移运行时工具集: {len(dynamic_toolsets)} 个\n")
            except Exception: pass

        return agent
    
    async def skill_load(self, skill_id: str) -> str:
        """动态加载技能工具（实例方法，直接访问 self.agent）"""
        print(f"[{self.key}] 激活技能: {skill_id}")
        if not self.skill_manager.skill_exists(skill_id):
            return f"[ERROR] 技能 '{skill_id}' 不存在。"

        tools = self._load_skill_tools(skill_id)
        skill_tools_file = Path(self.config.skills_path) / skill_id / "tools.py"
        skill_has_tools_file = skill_tools_file.exists()
        already_loaded = hasattr(self, '_loaded_skills') and skill_id in getattr(self, '_loaded_skills', [])
        load_diag = getattr(self, '_last_skill_load_diagnostics', {}).get(skill_id)

        if skill_has_tools_file and not tools and not already_loaded:
            diagnostic_block = ""
            if load_diag and load_diag.get("status") == "error":
                diagnostic_block = (
                    "\nDiagnostic:\n"
                    f"- tool_file: {load_diag.get('tool_file')}\n"
                    f"- error_type: {load_diag.get('error_type')}\n"
                    f"- error: {load_diag.get('error')}\n"
                    f"- force_reload: {load_diag.get('force_reload')}\n"
                    f"- existing_tools: {load_diag.get('existing_names')}\n"
                    f"- loaded_tools: {load_diag.get('loaded_tool_names')}"
                )
            return (
                f"[WARN] 技能 '{skill_id}' 已找到，但工具未成功加载。"
                f"请检查 {skill_tools_file} 是否存在导入错误或 get_tools() 是否返回了空列表。"
                f"{diagnostic_block}\n"
                f"Instructions:\n{self.skill_manager.load_full_sop(skill_id)}"
            )

        return f"""[OK] 技能 '{skill_id}' 已加载。Instructions:\n{self.skill_manager.load_full_sop(skill_id)}"""

    async def skill_reload(self, skill_id: str) -> str:
        """热重载技能工具：卸载旧版本并重新从磁盘加载，用于调试时快速生效。"""
        print(f"[{self.key}] 热重载技能: {skill_id}")
        if not self.skill_manager.skill_exists(skill_id):
            return f"[ERROR] 技能 '{skill_id}' 不存在。"

        tools = self._load_skill_tools(skill_id, force_reload=True)
        if not tools:
            load_diag = getattr(self, '_last_skill_load_diagnostics', {}).get(skill_id)
            diagnostic_block = ""
            if load_diag and load_diag.get("status") == "error":
                diagnostic_block = (
                    "\nDiagnostic:\n"
                    f"- tool_file: {load_diag.get('tool_file')}\n"
                    f"- error_type: {load_diag.get('error_type')}\n"
                    f"- error: {load_diag.get('error')}\n"
                    f"- force_reload: {load_diag.get('force_reload')}\n"
                    f"- existing_tools: {load_diag.get('existing_names')}\n"
                    f"- loaded_tools: {load_diag.get('loaded_tool_names')}"
                )
            return (
                f"[WARN] 技能 '{skill_id}' 热重载完成，但未找到任何工具（请检查 tools.py 是否有语法错误）。"
                f"{diagnostic_block}"
            )
        names = [t.__name__ for t in tools]
        return f"[OK] 技能 '{skill_id}' 热重载成功，已加载工具: {names}\nInstructions:\n{self.skill_manager.load_full_sop(skill_id)}"
    
    def _load_skill_tools(self, skill_id: str, force_reload: bool = False):
        """加载技能工具到当前 agent。force_reload=True 时先卸载旧版本再重新加载。"""
        import importlib.util
        import functools

        # [Security] Verify user_id before binding
        print(f"[{self.key}] Loading tools for {skill_id} with User ID: {self.user_id}")
        if not hasattr(self, '_last_skill_load_diagnostics'):
            self._last_skill_load_diagnostics = {}
        self._last_skill_load_diagnostics[skill_id] = {
            "status": "started",
            "skill_id": skill_id,
            "session_key": self.key,
            "force_reload": force_reload,
            "tool_file": None,
            "error_type": None,
            "error": None,
            "existing_names": [],
            "loaded_tool_names": [],
        }

        # [HotReload] 若强制重载，先移除该 skill 之前注册的工具
        if force_reload and hasattr(self, '_skill_tools_map') and skill_id in self._skill_tools_map:
            old_names = self._skill_tools_map[skill_id]
            self.agent.tools = [t for t in self.agent.tools if getattr(t, '__name__', None) not in old_names]
            del self._skill_tools_map[skill_id]
            print(f"[{self.key}] 🔄 已卸载旧版 {skill_id} 工具: {old_names}")

        tool_files = [
            os.path.join(self.config.skills_path, skill_id, "tools.py")
        ]

        loaded_tools = []
        # 获取当前已加载工具的名称集合
        existing_names = {t.__name__ for t in self.agent.tools if hasattr(t, '__name__')}
        self._last_skill_load_diagnostics[skill_id]["existing_names"] = sorted(existing_names)

        for tool_file in tool_files:
            self._last_skill_load_diagnostics[skill_id]["tool_file"] = tool_file
            if os.path.exists(tool_file):
                try:
                    spec = importlib.util.spec_from_file_location(f"skills.{skill_id}.tools", tool_file)
                    module = importlib.util.module_from_spec(spec)
                    tool_dir = os.path.dirname(tool_file)
                    added_to_sys_path = False
                    if tool_dir not in sys.path:
                        sys.path.insert(0, tool_dir)
                        added_to_sys_path = True
                    try:
                        spec.loader.exec_module(module)
                    finally:
                        if added_to_sys_path:
                            try:
                                sys.path.remove(tool_dir)
                            except ValueError:
                                pass

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
                            # 尝试传入 status_reporter 和 interruption_queue
                            # [Fix] 注入 interruption_queue 以支持工具级中断 (如 bash)
                            tools = module.get_tools(
                                *common_args, 
                                status_reporter=self.report_swarm_event,
                                interruption_queue=self.queue
                            )
                        except TypeError:
                            # 如果报错 (unexpected keyword argument), 尝试只传 status_reporter
                            try:
                                tools = module.get_tools(*common_args, status_reporter=self.report_swarm_event)
                            except TypeError:
                                # 还不行，回退到旧调用
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
                                self._last_skill_load_diagnostics[skill_id]["loaded_tool_names"] = [
                                    getattr(t, '__name__', str(t)) for t in loaded_tools
                                ]
                                # 更新 existing_names 以防止同一次加载中的重复（虽然不太可能）
                                for t in wrapped_tools:
                                    if hasattr(t, '__name__'):
                                        existing_names.add(t.__name__)

                except Exception as e:
                     self._last_skill_load_diagnostics[skill_id].update({
                         "status": "error",
                         "error_type": type(e).__name__,
                         "error": str(e),
                         "existing_names": sorted(existing_names),
                         "loaded_tool_names": [getattr(t, '__name__', str(t)) for t in loaded_tools],
                     })
                     log_line = (
                         f"[{self.key}] Failed to load tools from {tool_file} | "
                         f"skill_id={skill_id} force_reload={force_reload} "
                         f"error_type={type(e).__name__} error={e} existing_names={sorted(existing_names)} "
                         f"loaded_tools={[getattr(t, '__name__', str(t)) for t in loaded_tools]}"
                     )
                     print(log_line)
                     try:
                         with open(r"d:\git_codes\google_adk_helloworld_git\tmp\debug_steering.log", "a", encoding="utf-8") as f:
                             f.write(log_line + "\n")
                     except Exception:
                         pass
        
        # [Fix] 记录成功加载的技能，排除内置的核心技能
        if loaded_tools and skill_id not in ('bash', 'search_exp'):
            if not hasattr(self, '_loaded_skills'):
                self._loaded_skills = []
            if skill_id not in self._loaded_skills:
                self._loaded_skills.append(skill_id)

        # [HotReload] 记录该 skill 对应的工具名，供 force_reload 时卸载使用
        if loaded_tools:
            if not hasattr(self, '_skill_tools_map'):
                self._skill_tools_map = {}
            self._skill_tools_map[skill_id] = {t.__name__ for t in loaded_tools if hasattr(t, '__name__')}

        self._last_skill_load_diagnostics[skill_id].update({
            "status": "loaded" if loaded_tools else (
                "error" if self._last_skill_load_diagnostics[skill_id].get("status") == "error" else "empty"
            ),
            "existing_names": sorted(existing_names),
            "loaded_tool_names": [getattr(t, '__name__', str(t)) for t in loaded_tools],
        })

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

    
    async def _extract_and_publish_experience(self, events_snapshot: list):
        """
        [新增] 经验提取器 (核心引擎)
        功能：分析内存快照 -> 清洗数据 -> 识别试错模式 -> LLM 提炼 -> 分类归档 -> 更新索引
        """
        import re
        import uuid
        import json
        from datetime import datetime

        # ==========================================
        # [日志工具] 将所有过程记录到 md 文件（避免被终端刷掉）
        # ==========================================
        _log_time = datetime.now()
        _log_lines = []

        def _log(msg: str):
            ts = datetime.now().strftime("%H:%M:%S")
            _log_lines.append(f"[{ts}] {msg}")

        def _flush_log(gene_id: str = "no_gene"):
            """将日志 flush 到 markdown 文件"""
            try:
                date_str = _log_time.strftime("%Y-%m-%d-%H%M%S")
                uid = uuid.uuid4().hex[:6]
                log_filename = f"{date_str}_{uid}_{gene_id}.md"
                log_path = os.path.join(EXPERIENCE_LOG_DIR, log_filename)
                with open(log_path, 'w', encoding='utf-8') as lf:
                    lf.write(f"# 经验提取日志 - {_log_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    lf.write("\n".join(_log_lines))
                    lf.write("\n")
            except Exception as le:
                print(f"[反思提取] 日志写入失败: {le}")

        # 1. 基础过滤：交互太短通常没有抓取价值
        if not events_snapshot or len(events_snapshot) < 3:
            return
            
        _log(f"启动后台复盘，分析 {len(events_snapshot)} 条原始轨迹...")
        
        has_env_error = False
        tool_call_history = [] 
        clean_history_text = ""
        
        # ==========================================
        # 2. 数据清洗 (Data Cleaning) - 节省 Token 且聚焦核心
        # ==========================================
        for evt in events_snapshot:
            # 提取角色
            role = "unknown"
            if hasattr(evt, 'content') and hasattr(evt.content, 'role'):
                role = evt.content.role
            elif hasattr(evt, 'author'):
                role = evt.author
            
            if role == 'user': role_tag = "User"
            elif role == 'model': role_tag = "Agent"
            else: role_tag = "Tool/System"

            step_content = ""
            if hasattr(evt, 'content') and hasattr(evt.content, 'parts'):
                for part in evt.content.parts:
                    # [干货] 文本
                    if hasattr(part, 'text') and part.text:
                        step_content += f"  [Text]: {part.text.strip()}\n"
                    # [干货] 工具调用
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        func_args = str(dict(fc.args)) if hasattr(fc, 'args') else str(fc.args)
                        tool_call_history.append({"name": fc.name, "args": func_args})
                        step_content += f"  [Action]: Call {fc.name}({func_args})\n"
                    # [干货] 工具结果 (关键! 用于判断报错)
                    if hasattr(part, 'function_response') and part.function_response:
                        resp = str(part.function_response.response)
                        # 截断过长输出，保留头部报错信息
                        if len(resp) > 4000: resp = resp[:4000] + "...(truncated)"
                        step_content += f"  [Observation]: {resp}\n"
                        
                        # 扫描客观报错特征
                        error_signatures = ["traceback", "error", "exception", "failed", "not found", "denied", "fatal"]
                        if any(sig in resp.lower() for sig in error_signatures):
                            has_env_error = True

            if step_content.strip():
                clean_history_text += f"\n== {role_tag} ==\n{step_content}"

        # ==========================================
        # 3. 启发式判定 (Heuristic Check) - 减少无效 LLM 调用
        # ==========================================
        is_struggling = False
        # 判定 A: 有客观报错
        if has_env_error: 
            is_struggling = True
            _log(f"判定触发: 检测到客观报错特征")
        # 判定 B: 没报错但重复尝试 (Action 重复)
        elif len(tool_call_history) >= 2:
            call_names = [call["name"] for call in tool_call_history]
            if len(call_names) > len(set(call_names)):
                is_struggling = True
                _log(f"判定触发: 检测到工具重复调用 {call_names}")

        if not is_struggling:
            _log("判定：任务顺利完成，无需提取经验，跳过。")
            _flush_log("skipped")
            return

        _log("捕捉到试错/纠偏轨迹，提交 LLM 进行经验蒸馏...")

        # ==========================================
        # 4. LLM 提炼 (Distillation)
        # ==========================================
        system_prompt = """
        你是一个 AI Agent 经验归档员。请分析这段"清洗后的执行日志"。
        判断 Agent 是否在执行中遇到了阻碍（报错或逻辑错误），并通过【重试/修改参数】成功修复了问题？
        
        如果符合，请提取 JSON（不要包含 Markdown 格式）：
        {
            "category": "分类目录名(英文单数), 如 python, git, docker, network, os",
            "title": "简短经验标题 (10-15字)",
            "keywords": ["tag1", "tag2"],
            "problem_context": "客观描述：Agent 想做什么，哪里卡住了",
            "trigger_error_regex": "提取最具代表性的报错片段(Observation)",
            "solution_action": {"commands": ["提取最终成功的 Action 代码/参数"]},
            "reasoning": "推测它为什么一开始不对，后来是怎么改对的？"
        }
        如果不符合（只是顺利完成），仅返回 "NONE"。
        """

        try:
            response = await litellm.acompletion(
                model=self.config.model,
                api_key=self.config.api_key,
                api_base=self.config.api_base,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"【清洗后的轨迹】\n{clean_history_text}"}
                ],
                temperature=0.1
            )
            
            output = response.choices[0].message.content.strip()
            _log(f"LLM 返回结果长度: {len(output)} 字符")

            if "NONE" in output.upper() and len(output) < 10:
                _log("LLM 判定：任务顺利完成，返回 NONE，跳过归档。")
                _flush_log("llm_none")
                return
            
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if not json_match:
                _log("LLM 返回内容无法解析为 JSON，跳过归档。")
                _flush_log("parse_fail")
                return
            gene_data = json.loads(json_match.group())

            # ==========================================
            # 5. 分类归档与索引更新 (OpenViking-Lite 核心)
            # ==========================================
            gene_id = f"gene_{uuid.uuid4().hex[:8]}"
            
            # A. 确定分类目录
            category = gene_data.get("category", "uncategorized").lower()
            category = "".join([c for c in category if c.isalnum() or c=='_']) # 安全过滤
            save_dir = os.path.join(SHARED_GENE_POOL, category)
            os.makedirs(save_dir, exist_ok=True)

            # B. 保存正文 (L2 Detail)
            capsule = {
                "id": gene_id,
                "category": category,
                "timestamp": datetime.now().isoformat(),
                "content": gene_data
            }
            file_path = os.path.join(save_dir, f"{gene_id}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(capsule, f, ensure_ascii=False, indent=2)

            # C. 更新总索引 (L0 Index) - 高级保险丝架构 [异步解耦 + FileLock防覆写 + 原子落盘]
            lock_path = f"{EXPERIENCE_INDEX_PATH}.lock"
            
            # 【优化1：异步解耦】把沉重的阻塞级 I/O 踢到独立线程中运行，保障主体 Event Loop 大量思考并发
            try:
                await asyncio.to_thread(
                    _sync_safe_update_manifest,
                    lock_path,
                    EXPERIENCE_INDEX_PATH,
                    gene_id,
                    category,
                    gene_data
                )
            except Exception as update_err:
                _log(f"经验更新落地最终阶段异常: {update_err}")
                # 这里不抛异常阻断外面，只记录错误
            
            _log(f"经验已归档: [{category}] {file_path}")
            _log(f"  标题: {gene_data.get('title')}")
            _log(f"  关键词: {gene_data.get('keywords', [])}")
            _flush_log(gene_id)

        except Exception as e:
            _log(f"提取过程异常: {e}")
            _flush_log("error")

    async def _run_agent_turn(self, task: str, images: List[str] = None, yield_chunks: bool = True, is_sandbox_turn: bool = False):
        """
        执行共享的 agent turn 主逻辑。

        - `yield_chunks=True`：供前台 `/api/chat` 使用，流式返回 chunk
        - `yield_chunks=False`：供 KAIROS runtime 使用，只复用执行骨架，不向外层返回 chunk
        """
        # [DEBUG] 植入配置快照日志
        print(f"\n[SteeringSession] 🚀 启动任务执行...")
        print(f"  - 逻辑配置 (Tag): {self.config.active_model}")
        print(f"  - 物理模型 (Model): {self.config.model}")
        print(f"  - API 地址 (Base): {self.config.api_base}")
        # 安全打印 Key 长度和前后缀以供调试，不泄露真实内容
        ak = self.config.api_key or ""
        ak_len = len(ak)
        ak_debug = f"{ak[:4]}...{ak[-4:]}" if ak_len > 8 else "****"
        print(f"  - API 密钥 (Key): {ak_debug} (长度: {ak_len})")
        
        # 准备会话上下文
        session_key = (self.app_name, self.user_id, self.session_id)
        was_interrupted = False
        
        # ==========================================
        # [新增] 初始化内存快照列表
        # 完全独立于 session.events，无论后续发生 Compact 还是 Rewind，数据都是安全的
        # ==========================================
        events_snapshot = []
        
        try:
            from google.adk.runners import Runner
            from google.adk.agents import RunConfig
            from google.adk.agents.run_config import StreamingMode
            
            active_session_service = self.session_service

            # ==============================================================
            # [沙盒隔离机制] 
            # 对于不需要落盘的后台任务 (如 KAIROS)，克隆一份状态投入内存进行全封闭运行
            # ==============================================================
            if is_sandbox_turn:
                from google.adk.sessions import InMemorySessionService
                active_session_service = InMemorySessionService()
                real_session = await self.session_service.get_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=self.session_id,
                )
                sandbox_state = dict(real_session.state or {}) if real_session and getattr(real_session, 'state', None) else {}
                await active_session_service.create_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=self.session_id,
                    state=sandbox_state,
                )
                if real_session and hasattr(real_session, 'events') and real_session.events:
                    active_session_service.sessions[self.app_name][self.user_id][self.session_id].events = list(real_session.events)
                print(f"[Sandbox] 🛡️ 已开启内存沙盒，避免后台思考事件污染真实数据库！")

            runner = Runner(agent=self.agent, app_name=self.app_name, session_service=active_session_service)
            
            # 确保 session 存在
            session = await self.session_service.get_session(
                app_name=self.app_name, 
                user_id=self.user_id, 
                session_id=self.session_id
            )
            # [New] 为 Status Reporter 绑定当前会话对象
            self._current_session = session 
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
                # [修复] 新创建的 session 也要绑定到 _current_session
                # 否则 dispatch_batch_tasks 发来的 update_session_state 信号会因为
                # self._current_session is None 而被忽略，导致 task_type 丢失
                self._current_session = session
            
            # === 自动标题生成 ===
            # 使用 rewind 感知的有效事件计数（与 history API 保持一致）
            # 若第一条消息被 rewind，则 effective user event count 为 0，允许重新生成标题
            _title_events = session.events if session and hasattr(session, 'events') else []
            _title_exclude = set()
            for _midx, _mev in enumerate(_title_events):
                _mactions = getattr(_mev, 'actions', None)
                if not _mactions:
                    continue
                _mtarget = getattr(_mactions, 'rewind_before_invocation_id', None)
                if not _mtarget:
                    continue
                for _j in range(_midx):
                    if getattr(_title_events[_j], 'invocation_id', None) == _mtarget:
                        for _k in range(_j, _midx + 1):
                            _title_exclude.add(_k)
                        break
            
            user_event_count = 0
            for _tidx, evt in enumerate(_title_events):
                if _tidx in _title_exclude:
                    continue
                role = 'unknown'
                if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
                    role = evt.content.role
                elif hasattr(evt, 'author'):
                    role = evt.author
                if role == 'user':
                    user_event_count += 1
            
            # [Fix] 不再仅依赖 user_event_count==0，而是检查 state 中是否已有 title
            # 防止中断后标题被 Runner/压缩的 save_session 全量覆盖导致丢失
            existing_title = None
            if hasattr(session, 'state') and session.state:
                existing_title = session.state.get('title')
            
            if not existing_title:
                # 优先使用 session 中第一条 user event 的内容作为标题
                # 防止"继续执行"时 task="继续" 被当作标题
                title_source = task
                if user_event_count > 0 and session and hasattr(session, 'events'):
                    for evt in session.events:
                        if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role') and evt.content.role == 'user':
                            if hasattr(evt.content, 'parts') and evt.content.parts:
                                for p in evt.content.parts:
                                    if hasattr(p, 'text') and p.text and len(p.text) > 5:
                                        title_source = p.text
                                        break
                            break
                title = title_source[:30] + ("..." if len(title_source) > 30 else "")
                if not hasattr(session, 'state') or session.state is None:
                    session.state = {}
                session.state['title'] = title
                if isinstance(self.session_service, FullyCustomDbService):
                    await self.session_service.save_session_state(
                        app_name=self.app_name,
                        user_id=self.user_id,
                        session_id=self.session_id,
                        state=session.state,
                    )
                else:
                    await self.session_service.save_session(session)
                print(f"[系统] 自动生成会话标题: {title}")

            # [Fix] 同样检查 task_type 是否丢失，通过扫描历史 events 恢复
            if hasattr(session, 'state') and session.state:
                existing_task_type = session.state.get('task_type')
            else:
                existing_task_type = None
            
            if not existing_task_type:
                recovered_type = None
                
                # 方式1: 通过 app_name 前缀判断 Worker 身份
                if self.app_name.startswith('swarm_from_'):
                    recovered_type = 'swarm_worker'
                # 方式2: 通过 function_call 判断 Leader 身份
                elif session and hasattr(session, 'events') and session.events:
                    swarm_tool_names = {'dispatch_task', 'dispatch_batch_tasks', 'deep_think', 'hold_meeting'}
                    for evt in session.events:
                        if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'parts'):
                            for part in evt.content.parts:
                                if hasattr(part, 'function_call') and part.function_call:
                                    if part.function_call.name in swarm_tool_names:
                                        recovered_type = 'swarm_leader'
                                        break
                        if recovered_type:
                            break
                
                if recovered_type:
                    if not hasattr(session, 'state') or session.state is None:
                        session.state = {}
                    session.state['task_type'] = recovered_type
                    if isinstance(self.session_service, FullyCustomDbService):
                        await self.session_service.save_session_state(
                            app_name=self.app_name,
                            user_id=self.user_id,
                            session_id=self.session_id,
                            state=session.state,
                        )
                    else:
                        await self.session_service.save_session(session)
                    print(f"[系统] 自动恢复 task_type: {recovered_type}")
            # === 自动压缩逻辑 (从配置读取) ===
            turn_count = len(session.events) if session and hasattr(session, 'events') and session.events else 0
            tool_count = len(self.agent.tools) if self.agent.tools else 0
            
            WARN_TURNS = self.config.warn_turns
            MAX_TURNS = self.config.max_turns
            
            if turn_count > WARN_TURNS and turn_count <= MAX_TURNS:
                print(f"\n[提醒] event个数 ({turn_count}) 超过软阈值 {WARN_TURNS}，建议执行 smart_compact 压缩上下文")
            
            if turn_count > MAX_TURNS:
                print(f"\n[警告] event个数 ({turn_count}) 超过硬阈值 {MAX_TURNS}，正在执行自动压缩...")
                if yield_chunks:
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
            
            # ============ [多模态] 构建 user_query ============
            parts = []
            
            # 处理图片
            if images:
                
                print(f"[Steering] 收到 {len(images)} 张图片输入")
                for i, img_data in enumerate(images):
                    try:
                        # 解析 data:image/png;base64,xxxxx 格式
                        if ',' in img_data:
                            header, b64_str = img_data.split(',', 1)
                            # 提取 MIME type，例如 image/png
                            mime_type = header.split(':')[1].split(';')[0] if ':' in header else 'image/png'
                        else:
                            b64_str = img_data
                            mime_type = 'image/png'
                        
                        image_bytes = b64_module.b64decode(b64_str)
                        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
                        print(f"  [图片{i+1}] {mime_type}, {len(image_bytes)} bytes")
                    except Exception as e:
                        print(f"  [图片{i+1}] 解析失败: {e}")
            
            # 处理文本
            if task:
                parts.append(types.Part(text=task))
            
            # 兜底：防止空请求
            if not parts:
                parts.append(types.Part(text="(empty)"))
            
            user_query = types.Content(role='user', parts=parts)
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
                
                # 创建三个 listener task (添加了 self.queue 的监听)
                pending_runner_get = asyncio.create_task(runner_queue.get())
                pending_stream_get = asyncio.create_task(self.stream_queue.get())
                pending_cancel_get = asyncio.create_task(self.queue.get()) if self.queue else None
                
                # [Deduplication State]
                accumulated_text_by_type = {"text": "", "thought": ""}
                
                while True:
                    # 等待任意一个队列有消息
                    wait_tasks = [pending_runner_get, pending_stream_get]
                    if pending_cancel_get:
                        wait_tasks.append(pending_cancel_get)
                        
                    done, pending = await asyncio.wait(
                        wait_tasks, 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # 0. 处理取消信号
                    if pending_cancel_get and pending_cancel_get in done:
                        cancel_signal = pending_cancel_get.result()
                        # 准备下一次获取，以防信号不是 CANCEL (理论上只有 CANCEL)
                        pending_cancel_get = asyncio.create_task(self.queue.get())
                        
                        if cancel_signal == "CANCEL":
                            print(f"[Node-{node_config.port}] 🛑 收到前端取消信号，强制终止当前任务！")
                            if not pending_runner_get.done(): pending_runner_get.cancel()
                            if not pending_stream_get.done(): pending_stream_get.cancel()
                            driver_task.cancel()
                            raise UserInterruption("Task cancelled by user.")
                            
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
                            
                            # ==========================================
                            # [新增] 实时抓取快照
                            # 只要 Runner 吐出一个 Event，立刻存入本地快照。
                            # 这是"对抗回滚"的关键：即使下一秒用户回滚了，这个 Event 依然在内存里。
                            # ==========================================
                            events_snapshot.append(result)
                            # ==========================================
                            
                            chunks = list(_process_event_stream(result))
                            if yield_chunks:
                                for chunk in dedupe_textual_event_chunks(chunks, accumulated_text_by_type):
                                    yield chunk

                    # 2. 处理 Side-Channel 消息 (Swarm Log, Progress 等)
                    if pending_stream_get in done:
                        event = pending_stream_get.result()

                        # 准备下一次获取
                        pending_stream_get = asyncio.create_task(self.stream_queue.get())

                        if yield_chunks:
                            yield event

                # 清理
                if not pending_runner_get.done(): pending_runner_get.cancel()
                if not pending_stream_get.done(): pending_stream_get.cancel()
                if pending_cancel_get and not pending_cancel_get.done(): pending_cancel_get.cancel()
                # driver_task 应该已经结束了，不过保险起见
                if not driver_task.done(): driver_task.cancel()
        
            except ContextWindowExceededError:
                print(f"!!! [CRITICAL] Context Window Exceeded !!!")
                print(f"!!! [CRITICAL] 触发紧急压缩恢复流程 !!!")
                
                # [Layer 2] 异常兜底：紧急压缩
                session = await self._auto_compact_session(session)
                
                # 必须重新抛出或者想办法重试
                # 这里我们简单提示用户重试，因为完全自动重试整个流式请求比较复杂
                if yield_chunks:
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
                            # [Fix] Role 必须是 'user'，因为这是喂给模型的“输入数据”
                            response_content = types.Content(role='user', parts=response_parts)
                            
                            # [Fix] Author 最好用当前 Agent 的名字
                            current_agent_name = self.config.name if self.config.name else "unknown_agent"
                            response_event = Event(author=current_agent_name, content=response_content)
                            session.events.append(response_event)
                            print(f"[System] 已补全 {len(pending_calls)} 个 FunctionResponse")
                    
                    # 插入中断标记(system 消息)
                    # [Fix] 把 role 改为 'user'，让模型把它当成对话流中的显式指令
                    stop_content = types.Content(
                        role="user", 
                        parts=[types.Part(text="[注意] 用户主动中断了当前对话。")]
                    )
                    # Author 依然可以是 'system'
                    stop_event = Event(author="system", content=stop_content)
                    
                    if session and hasattr(session, 'events'):
                        session.events.append(stop_event)
                        print(f"[System] 已插入中断标记到历史记录")
                except Exception as e:
                    print(f"[Warning] Failed to append interruption history: {e}")

                if yield_chunks:
                    yield {"type": "text", "content": "\n\n[已停止] 任务已取消。"}
                return

        except UserInterruption:
            # 这个块通常不会被到达，因为 run_task 内部有局部处理，但为了双重保险
            if yield_chunks:
                yield {"type": "text", "content": "\n\n[已停止] 任务已取消。"}
            return
            
        except Exception as e:
            # 过滤掉包含中断信息的特定错误字符串
            err_msg = str(e)
            if "User requested to stop operation" in err_msg:
                if yield_chunks:
                    yield {"type": "text", "content": "\n\n[已停止] 任务已取消。"}
            else:
                logger.error(f"执行出错: {e}")
                if yield_chunks:
                    yield f"[ERROR] {err_msg}"
                print(f"\n[ERROR] 执行出错: {e}")
        
        finally:
            # [Fix] 最后强制保存一次，但必须先 Reload 以防止覆盖 Runner 写入的 Events
            if self._current_session:
                try:
                    if is_sandbox_turn:
                        # [沙盒退出]: 仅提取在沙盒运行期间新变化的 Session State 并融合回真实数据库
                        final_sandbox = await active_session_service.get_session(
                            app_name=self.app_name,
                            user_id=self.user_id,
                            session_id=self.session_id,
                        )
                        if final_sandbox and final_sandbox.state:
                            latest_real = await self.session_service.get_session(
                                app_name=self.app_name,
                                user_id=self.user_id,
                                session_id=self.session_id,
                            )
                            merged_state = dict(latest_real.state or {}) if latest_real and getattr(latest_real, 'state', None) else {}
                            merged_state.update(final_sandbox.state)
                            persisted_session = await self._persist_session_state(merged_state)
                            self._current_session = persisted_session
                            print(f"[Sandbox] 🛡️ 沙盒安全销毁，仅保留系统状态变更。")

                    else:
                        # 1. 重新从 DB 加载最新 Session (包含 Runner 写入的 events)
                        latest_session = await self.session_service.get_session(
                            self.app_name, self.user_id, self.session_id
                        )
                        
                        if latest_session:
                            # 2. 将 _current_session 中捕获的 metadata (tags) 合并过去
                            # 重点保留 tool 产生的 state 变更 (如 task_type)
                            if self._current_session.state:
                                if not latest_session.state: latest_session.state = {}
                                latest_session.state.update(self._current_session.state)

                            if isinstance(self.session_service, FullyCustomDbService):
                                await self.session_service.save_session_state(
                                    app_name=self.app_name,
                                    user_id=self.user_id,
                                    session_id=self.session_id,
                                    state=latest_session.state or {},
                                )
                                print(f"[Steering] Merged state-only session {self.session_id} (Events: {len(latest_session.events)})")
                            else:
                                # 3. 保存合并后的 Session
                                await self.session_service.save_session(latest_session)
                                print(f"[Steering] Merged tags and saved session {self.session_id} (Events: {len(latest_session.events)})")
                        else:
                            # Fallback: 如果读不到，就只能存旧的了 (极少见)
                            if isinstance(self.session_service, FullyCustomDbService):
                                await self.session_service.save_session_state(
                                    app_name=self.app_name,
                                    user_id=self.user_id,
                                    session_id=self.session_id,
                                    state=self._current_session.state or {},
                                )
                            else:
                                await self.session_service.save_session(self._current_session)
                            print(f"[Steering] Fallback saved session {self.session_id}")

                except Exception as e:
                    print(f"[Warning] Session state synchronization failed: {e}")
            
            self._current_session = None

            # [沙盒模式修正] 如果是后台自治运行，不触发外部落盘，避免污染磁盘历史
            if not is_sandbox_turn:
                # ==========================================
                # [新增] 1. 触发实时流式记忆落盘 (黑匣子机制)
                # 无视任务是否中断，只要有数据，立刻写进 Markdown 档案
                # 传入的 events_snapshot 是防篡改的独立快照
                # ==========================================
                if task or events_snapshot:
                    # Fire-and-Forget 异步执行，不阻塞主线程退出
                    asyncio.create_task(
                        self._archive_turn_to_memory(task, events_snapshot, images)
                    )

                # ==========================================
                # [已有] 2. 触发后台提取 (使用内存快照，Fire-and-Forget 模式)
                # 只要本轮产生了有效的交互 (>=3条)，就启动后台分析。
                # 传入 events_snapshot 而非 session.events，对抗 Compact/Rewind 影响。
                # ==========================================
                if not was_interrupted and len(events_snapshot) >= 3:
                    asyncio.create_task(
                        self._extract_and_publish_experience(events_snapshot)
                    )
            # ==========================================

            # 打印 Session History（调试用）
            try:
                updated_session = await self.session_service.get_session(
                    app_name=self.app_name, 
                    user_id=self.user_id, 
                    session_id=self.session_id
                )

                file_logger.info("\n\n***打印session events***\n===Session History Start===")
                if updated_session and updated_session.events:
                    for event in updated_session.events:
                        if event.content and event.content.parts:

                            file_logger.info(f"<{event.author}>: {event.content.parts}")
                            file_logger.info('=='*10 + '\n')

                file_logger.info("=" * 60)

                file_logger.info("\n\n***打印session events***\n===Session History End===\n")
            except Exception as e:
                print(f"[Warning] Failed to print session history: {e}")
            
            if was_interrupted:
                print(f"\n🛑 [System] 任务已停止 (Interrupted by User)")

    async def run_task(self, task: str, images: List[str] = None):
        """前台聊天入口：流式转发共享 agent turn 的 chunks。"""
        async for chunk in self._run_agent_turn(task, images=images, yield_chunks=True):
            yield chunk

    async def _archive_turn_to_memory(self, user_task: str, events_snapshot: list, images: list = None):
        """
        [新增] 实时流式落盘 (黑匣子机制) - Swarm 并发安全版
        纯 Append-Only 模式，无视框架上下文压缩，保留最完整的原生记录。
        """
        import os
        import json
        from datetime import datetime
        from filelock import FileLock
        
        try:
            now = datetime.now()
            month_str = now.strftime("%Y-%m")
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            
            # 1. 确定物理路径 (按三元组严格隔离，天然免疫跨角色冲突)
            _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            memory_dir = os.path.join(_PROJECT_ROOT, "memory_archive", self.user_id, month_str)
            os.makedirs(memory_dir, exist_ok=True)
            
            safe_app_name = self.app_name.replace("/", "_").replace("\\", "_")
            filename = f"{date_str}_{safe_app_name}_{self.session_id}.md"
            filepath = os.path.join(memory_dir, filename)
            
            is_new_file = not os.path.exists(filepath)
            
            # 2. 在内存中完成字符串拼接 (极大减少持有锁的时间)
            buffer = []
            
            # --- [A] 如果是新文件，写入 L0 索引头 (YAML) ---
            if is_new_file:
                buffer.append("---\n")
                buffer.append(f"user_id: {self.user_id}\n")
                buffer.append(f"app_name: {self.app_name}\n")
                buffer.append(f"session_id: {self.session_id}\n")
                buffer.append(f"created_at: {now.isoformat()}\n")
                if self._current_session and hasattr(self._current_session, 'state') and self._current_session.state:
                    state = self._current_session.state
                    if 'task_type' in state: buffer.append(f"task_type: {state['task_type']}\n")
                    if 'title' in state: buffer.append(f"title: {state['title']}\n")
                buffer.append("---\n\n")
            
            # --- [B] 写入本轮 User 输入 ---
            buffer.append(f"<user time=\"{time_str}\">\n")
            buffer.append(f"{user_task.strip() if user_task else ''}\n")
            if images:
                buffer.append(f"(attached {len(images)} image(s))\n")
            buffer.append("</user>\n\n")
            
            # --- [C] 遍历快照，写入 Agent 动作 ---
            # [去重策略] 基于诊断数据确定的 ADK 事件结构：
            # - partial=True  -> 流式碎片 -> 跳过
            # - partial=False -> 累加式完整事件 -> 处理
            # - partial=None  -> 工具返回事件 -> 处理
            last_role = None
            in_thought_stream = False
            agent_tag_open = False

            for evt in events_snapshot:
                # 核心去重：跳过所有流式碎片
                if getattr(evt, 'partial', False) is True:
                    continue

                role = getattr(evt, 'author', 'Ciri')
                if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
                    role = evt.content.role

                # 跳过 user 角色（由 B 阶段处理原生输入）
                # 但不能跳过工具返回事件（ADK 中 function_response 的 content.role='user'）
                if role == 'user':
                    has_func_response = False
                    if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'parts'):
                        for _p in evt.content.parts:
                            if hasattr(_p, 'function_response') and _p.function_response:
                                has_func_response = True
                                break
                    if not has_func_response:
                        continue

                # 获取 parts
                evt_parts = []
                if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'parts'):
                    evt_parts = evt.content.parts
                
                if not evt_parts:
                    continue

                # 角色切换时，关闭旧标签、开启新标签
                if role != last_role:
                    if in_thought_stream:
                        buffer.append("\n</thought>\n")
                        in_thought_stream = False
                    if agent_tag_open:
                        buffer.append("</agent>\n\n")
                    agent_role = role if role != 'user' else 'system'
                    buffer.append(f"<agent role=\"{agent_role}\" time=\"{time_str}\">\n")
                    agent_tag_open = True
                    last_role = role

                # 渲染 Parts（thought 流感知合并）
                for part in evt_parts:
                    # 1. 文本 (含 Thought 流合并)
                    if hasattr(part, 'text') and part.text:
                        is_thought = getattr(part, 'thought', False)
                        
                        if is_thought:
                            if not in_thought_stream:
                                buffer.append("<thought>\n")
                                in_thought_stream = True
                            buffer.append(part.text)
                        else:
                            if in_thought_stream:
                                buffer.append("\n</thought>\n")
                                in_thought_stream = False
                            buffer.append(f"{part.text.strip()}\n")
                        
                    # 2. 工具调用 (Function Call)
                    if hasattr(part, 'function_call') and part.function_call:
                        if in_thought_stream:
                            buffer.append("\n</thought>\n")
                            in_thought_stream = False
                        fc = part.function_call
                        tool_name = getattr(fc, 'name', 'unknown')
                        args_dict = dict(fc.args) if hasattr(fc, 'args') else {}
                        buffer.append(f"<tool_call name=\"{tool_name}\">\n")
                        buffer.append(json.dumps(args_dict, indent=2, ensure_ascii=False) + "\n")
                        buffer.append("</tool_call>\n")
                        
                    # 3. 工具结果 (Function Response)
                    if hasattr(part, 'function_response') and part.function_response:
                        if in_thought_stream:
                            buffer.append("\n</thought>\n")
                            in_thought_stream = False
                        fr = part.function_response
                        tool_name = getattr(fr, 'name', 'unknown')
                        resp_val = getattr(fr, 'response', {})
                        if hasattr(resp_val, 'items'):
                            resp_dict = dict(resp_val)
                        else:
                            resp_dict = {"result": str(resp_val)}
                        buffer.append(f"<tool_result name=\"{tool_name}\">\n")
                        buffer.append(json.dumps(resp_dict, indent=2, ensure_ascii=False) + "\n")
                        buffer.append("</tool_result>\n")

            # 关闭残留标签
            if in_thought_stream:
                buffer.append("\n</thought>\n")
            if agent_tag_open:
                buffer.append("</agent>\n\n")


            # 3. 终极并发保护：使用 FileLock 执行极速落盘
            # 锁的文件名与 Markdown 文件强绑定，不影响其他 Session 的并发写入
            lock_path = filepath + ".lock"
            with FileLock(lock_path, timeout=5):
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write("".join(buffer))
            
            # 写入完成后清理 .lock 文件（不影响保护功能，下次写入时会自动重建）
            try:
                os.remove(lock_path)
            except OSError:
                pass
                    
            print(f"[Memory] 实时快照已安全落盘至: {filename}")

            
        except Exception as e:
            print(f"[Memory] 实时流式落盘异常: {e}")
    
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
                                # === [优化] 提取内容摘要，但过滤 Base64 ===
                                fr = part.function_response
                                raw_resp = fr.response
                                
                                # 1. 解包可能存在的 dict 结构
                                if isinstance(raw_resp, dict) and 'result' in raw_resp:
                                    raw_resp = raw_resp['result']
                                
                                clean_text = ""
                                # 2. 处理字符串结果
                                if isinstance(raw_resp, str):
                                    clean_text = raw_resp
                                # 3. 处理多模态列表结果 (List[Dict])
                                elif isinstance(raw_resp, list):
                                    # 只提取 type='text' 的部分，跳过 type='image_url' 等
                                    texts = []
                                    for item in raw_resp:
                                        if isinstance(item, dict) and item.get("type") == "text":
                                            texts.append(item.get("text", ""))
                                    clean_text = " ".join(texts)
                                
                                content += f" [ToolOutput: {fr.name} -> {clean_text}]"
                                # ========================================
                    
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
                        
                    # [Fix] 显式修正 Author
                    if hasattr(placeholder_user_evt, 'author'):
                        placeholder_user_evt.author = "AutoCompactAgent"
                
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

# def _process_event_stream(event):
#     """处理事件单独一个event(注意event.content.parts可能包含多个part，所以event可以理解为流式输出的一段 可能包含多个类别的混合比如 though+text+fc) 而不是整个事件流"""
#     chunks = []

#     # [关键修复] 如果是最终响应事件，通常包含的是完整内容的汇总。
#     # 我们已经在之前的流式事件中处理过这些 parts 了，所以在这里跳过常规处理，
#     # 避免向前端发送重复的内容。
#     is_final = hasattr(event, 'is_final_response') and event.is_final_response()

def _process_event_stream(event, parts_override=None):
    chunks = []
    
    is_final = False
    if hasattr(event, 'is_final_response'):
        is_final = event.is_final_response()

    has_tool = False
    has_thought = False

    # 确定要处理的 parts
    target_parts = parts_override if parts_override is not None else []
    if parts_override is None:
        if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts'):
            target_parts = event.content.parts

    # 1. 预扫描 (使用 target_parts)
    if not is_final and target_parts:
        for part in target_parts:
            # 只要这个 Event 里包含 function_call/response，标记 has_tool
            # ... (logic same) ...
            if hasattr(part, 'function_call') and part.function_call:
                has_tool = True
                #break
            
            # 只要这个 Event 里包含 function_response，也标记 has_tool
            if hasattr(part, 'function_response') and part.function_response:
                has_tool = True

            # 检查思考 (根据您的Log结构，thought是Part的一个属性)
            # 只要这个 Event 里包含任何思考片段，就给整个 Event 发一张“免死金牌”
            if hasattr(part, 'thought') and part.thought:
                has_thought = True

    # 2. 处理 (仅在非最终响应时处理 parts)
    if not is_final and target_parts:
        for part in target_parts:
            # [关键修正] 仅当当前包里有工具，且当前 part 是文本或思考过程时，才跳过。
            # 必须放行 function_call 和 function_response 自身。
            is_text_part = hasattr(part, 'text') and part.text
            is_tool_related = (hasattr(part, 'function_call') and part.function_call) or \
                              (hasattr(part, 'function_response') and part.function_response)
            
            if has_tool and is_text_part and not is_tool_related and not has_thought:
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

async def run_agent(task: str, app_name: str, user_id: str, session_id: str, images: List[str] = None):
    """
    [新架构] 运行 Agent（适配器函数）
    委托给 SessionManager 来获取/创建会话，然后调用 session.run_task()
    """
    global session_manager
    
    if session_manager is None:
        raise RuntimeError("SessionManager 未初始化，请先调用 startup_event 或 create_agent")
    
    # 获取或创建会话
    session = session_manager.get_or_create(app_name, user_id, session_id)
    
    # [DEBUG] 追踪 run_agent 入口
    print(f"\n[run_agent] 📨 收到请求: task='{task[:20]}...' [Session: {session_id}]")
    print(f"  - 当前会话配置引用: model={session.config.model}, base={session.config.api_base}")

    # 委托给会话实例执行任务
    count = 0
    async for chunk in session.run_task(task, images=images):
        count += 1
        yield chunk
    
    print(f"[run_agent] ✅ 任务完成，共发送 {count} 个数据块 [Session: {session_id}]")

# ==========================================
# Web 服务接口
# ==========================================

# ==========================================
# 实时流式 STT 引擎
# ==========================================
stt_engine = None

def init_streaming_stt():
    """初始化流式 Paraformer 模型"""
    global stt_engine
    try:
        print("[STT] 正在加载流式 Paraformer 模型...")
        model_dir = "./model"
        
        if not os.path.exists(os.path.join(model_dir, "encoder.int8.onnx")):
             print(f"[STT] ⚠️ 模型未找到，请检查 {model_dir}")
             return

        stt_engine = sherpa_onnx.OnlineRecognizer.from_paraformer(
            tokens=os.path.join(model_dir, "tokens.txt"),
            encoder=os.path.join(model_dir, "encoder.int8.onnx"),
            decoder=os.path.join(model_dir, "decoder.int8.onnx"),
            num_threads=1,
            sample_rate=16000,
            feature_dim=80,
            enable_endpoint_detection=True, # 开启自动断句检测
            rule1_min_trailing_silence=2.0,
            rule2_min_trailing_silence=1.0,
            rule3_min_utterance_length=float("inf"),
            decoding_method="greedy_search",
            provider="cpu"
        )
        print("[STT] ✅ 流式 STT 引擎就绪")
    except Exception as e:
        print(f"[STT] ❌ 引擎加载失败: {e}")

# ==========================================
# 智能网关 (Smart Gatekeeper) - ASGI 中间件实现
# 使用中间件而非 Depends()，才能正确处理 WebSocket 连接
# ==========================================
from fastapi import HTTPException, status, Request
from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.responses import Response

# 优先从 private_key.yaml 中获取 remote_token
REMOTE_PASSWORD = yaml_config.get("remote_token") or "cosmos"

class SmartGatekeeperMiddleware:
    """
    ASGI 中间件：
    - WebSocket 连接 -> 直接放行（浏览器无法在 WS 握手中发送 Basic Auth）
    - 本地 HTTP 请求（无 cf-ray 头）-> 直接放行
    - 远程 HTTP 请求（含 cf-ray 头）-> 校验 Basic Auth 密码
    """
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        # WebSocket 和 lifespan 事件直接透传，不做认证
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 从 scope headers 中提取 (bytes -> str)
        headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        is_remote = "cf-ray" in headers

        # 本地请求直接放行
        if not is_remote:
            await self.app(scope, receive, send)
            return

        # 远程请求：验证 Basic Auth
        auth = headers.get("authorization", "")
        if auth.startswith("Basic "):
            try:
                decoded = b64_module.b64decode(auth[6:]).decode("utf-8")
                _, _, password = decoded.partition(":")
                if secrets.compare_digest(password.encode(), REMOTE_PASSWORD.encode()):
                    # 密码正确，放行
                    await self.app(scope, receive, send)
                    return
            except Exception:
                pass

        # 未提供凭证或密码错误，返回 401
        response = Response(
            content="Remote access requires password authentication.",
            status_code=401,
            headers={"WWW-Authenticate": "Basic realm=\"Ciri Remote\""},
        )
        await response(scope, receive, send)

app = FastAPI()
app.add_middleware(SmartGatekeeperMiddleware)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
register_kairos_routes(app, lambda: session_manager)

class AgentSettings(BaseModel):
    model: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    config_name: Optional[str] = None # 逻辑配置标签 (如 "DeepSeek-个人")
    session_id: Optional[str] = None

@app.get("/api/settings")
async def get_settings_endpoint():
    try:
        from src.adk_agent.config import yaml_path
        import yaml
        
        # 加载物理文件获取预设列表
        presets = {}
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r', encoding='utf-8') as f:
                disk_config = yaml.safe_load(f) or {}
                # 提取 llm_configs 作为预设
                if "llm_configs" in disk_config:
                    for model_id, details in disk_config["llm_configs"].items():
                        # 对预设中的 API Key 也进行脱敏处理
                        p_api_key = details.get("api_key")
                        p_masked_key = ""
                        if p_api_key:
                            if len(p_api_key) > 8:
                                p_masked_key = p_api_key[:4] + "...." + p_api_key[-4:]
                            else:
                                p_masked_key = "********"
                        
                        # 提取物理模型：优先使用项内的 model 字段，否则使用项名 (model_id)
                        physical_model = details.get("model", model_id)
                        
                        presets[model_id] = {
                            "model": physical_model,  # 真实的物理模型 ID
                            "base": details.get("api_base", ""),
                            "api_key": p_masked_key,   # 返回脱敏后的密钥
                            "label": model_id          # 显示用的标签名 (即项名)
                        }
        
        # 获取当前活跃配置的脱敏 key
        curr_api_key = config.api_key
        masked_key = None
        if curr_api_key:
            if len(curr_api_key) > 8:
                masked_key = curr_api_key[:4] + "...." + curr_api_key[-4:]
            else:
                masked_key = "********"
        
        print(f"[Settings] Generated presets count: {len(presets)}, labels: {list(presets.keys())}")
        print(f"[Settings] Returning active_config: {config.active_model}, physical_model: {config.model}")
                
        return {
            "model": config.model,           # 返回当前活跃的物理模型 ID
            "active_config": config.active_model, # 返回当前活跃的逻辑配置标签
            "api_base": config.api_base,
            "api_key": masked_key,
            "presets": presets # 返回给前端动态渲染
        }
    except Exception as e:
        print(f"[Settings] Fetch settings error: {e}")
        return {"error": str(e)}

@app.get("/api/skills")
async def list_skills_endpoint():
    """返回所有可用技能的 id/name/description 列表，供前端 / 补全使用"""
    skills = []
    if not os.path.exists(config.skills_path):
        return {"skills": []}
    for skill_id in sorted(os.listdir(config.skills_path)):
        skill_dir = os.path.join(config.skills_path, skill_id)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isdir(skill_dir) or not os.path.exists(skill_md):
            continue
        try:
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read()
            parts = content.split("---", 2)
            if len(parts) >= 3:
                import yaml as _yaml
                meta = _yaml.safe_load(parts[1]) or {}
                skills.append({
                    "id": skill_id,
                    "name": meta.get("name", skill_id),
                    "description": meta.get("description", ""),
                })
        except Exception:
            skills.append({"id": skill_id, "name": skill_id, "description": ""})
    return {"skills": skills}


@app.post("/api/settings")
async def update_settings_endpoint(settings: AgentSettings):
    # 1. 更新内存中的全局对象 (AgentConfig 现已支持 Setter 进行热更新)
    # 特别注意：如果提供了 config_name，则模型 active_model 应该设为该名称
    if settings.config_name:
        config.active_model = settings.config_name
        print(f"[Settings] 🚀 已切换活跃配置标签 (Tag): {config.active_model}")
        
    if settings.model: 
        config.model = settings.model
        print(f"[Settings] 🔄 物理模型 ID 已同步: {config.model}")
    
    if settings.api_key:
        # 如果是掩码，日志里特殊标记一下
        is_mask = "*" in settings.api_key
        config.api_key = settings.api_key
        print(f"[Settings] 🔑 收到 API Key 更新 (掩码模式: {is_mask})")

    if settings.api_base:
        config.api_base = settings.api_base
        print(f"[Settings] 🔗 收到 API Base 更新")

    # 2. 持久化到 private_key.yaml (尽量保护注释)
    try:
        from src.adk_agent.config import yaml_path
        import yaml
        
        # 读取原有内容以保留结构和字段顺序
        content = ""
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r', encoding='utf-8') as f:
                content = f.read()
        
        # 解析为字典进行逻辑更新
        current_disk_config = yaml.safe_load(content) or {}
        
        # 准备模型相关的层级结构
        if "llm_configs" not in current_disk_config:
            current_disk_config["llm_configs"] = {}
        
        # 关键修复：优先使用逻辑配置标签
        target_tag = settings.config_name or config.active_model
        
        if target_tag:
            current_disk_config["active_model"] = target_tag
            if target_tag not in current_disk_config["llm_configs"]:
                current_disk_config["llm_configs"][target_tag] = {}
            
            # 更新特定标签下的参数
            if settings.model:
                current_disk_config["llm_configs"][target_tag]["model"] = settings.model.strip()
            if settings.api_key: 
                current_disk_config["llm_configs"][target_tag]["api_key"] = settings.api_key.strip()
            if settings.api_base: 
                current_disk_config["llm_configs"][target_tag]["api_base"] = settings.api_base.strip()
            
            # 写回文件
            with open(yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(current_disk_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            
            print(f"[Settings] ✅ 配置已同步至物理文件: {yaml_path} (Tag: {target_tag})")
        
    except Exception as e:
        print(f"[Settings] ⚠️ 配置文件物理同步失败: {e}")

    print(f"[Settings] 内存配置已即时更新: tag={config.active_model}, physical_model={config.model}")

    # 3. 如果指定了 session_id，则尝试更新内存中的活跃会话实例
    if settings.session_id and session_manager:
        found = False
        for key, session in session_manager._sessions.items():
            try:
                with open(r"d:\git_codes\google_adk_helloworld_git\tmp\debug_steering.log", "a", encoding="utf-8") as f:
                    f.write(f"[Settings_Loop] 检查内存会话 Key: {key} | 对比 settings.session_id: {settings.session_id}\n")
            except Exception: pass
            if key[2] == settings.session_id:
                session.update_llm_config(
                    model=settings.model, 
                    api_key=settings.api_key, 
                    api_base=settings.api_base,
                    active_model=settings.config_name
                )
                found = True
                break
        if not found:
            print(f"[Settings] 会话 {settings.session_id} 未在活动列表中，仅更新了全局配置")
            
    return {"status": "success", "message": "配置已成功保存并同步"}

class ChatRequest(BaseModel):
    message: str
    images: Optional[List[str]] = None  # [多模态] Base64 编码的图片列表
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

class RewindRequest(BaseModel):
    app_name: str = DEFAULT_APP_NAME
    user_id: str = DEFAULT_USER_ID
    invocation_id: str

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

    # 2. 原子化抢锁并执行 (修复 TOCTOU 和幽灵队列排队问题)
    try:
        try:
            # 仅等待极其短暂的时间 (10ms)，充当非阻塞的 trylock
            await asyncio.wait_for(WORKER_LOCK.acquire(), timeout=0.01)
        except asyncio.TimeoutError:
            # 锁被其他并发请求瞬间抢走 (TOCTOU 时间差)
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "error": "Worker is busy",
                "status": "busy",
                "suggestion": "Worker was locked by another request concurrently."
            }
            
        worker_state.set_busy(request.message[:50], request.session_id)
        print(f"[Node-{node_config.port}] 🔒 锁定: 开始执行任务 (Session: {request.session_id})")

        async def generate():
            try:
                # 传入完整的三元组 + 图片
                async for chunk in run_agent(
                    request.message, 
                    request.app_name, 
                    request.user_id, 
                    request.session_id,
                    images=request.images
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
    
    # 2. [强化] 容错逻辑：分层搜索
    # 场景：Swarm Worker 任务的 app_name/user_id 组合可能与前端传过来的不一致
    if session is None:
        print(f"[API] Cancel: exact match failed -> {req.app_name}/{req.user_id}/{req.session_id}")
        
        # 2a. 先尝试只匹配 user_id + session_id (忽略 app_name)
        for (a_name, u_id, s_id), sess in session_manager._sessions.items():
            if u_id == req.user_id and s_id == req.session_id:
                session = sess
                print(f"[API] Cancel: found via user_id+session_id match (app_name was '{a_name}')")
                break
        
        # 2b. 最终兜底：只按 session_id 查找 (session_id 是全局唯一的 UUID)
        if session is None:
            for (a_name, u_id, s_id), sess in session_manager._sessions.items():
                if s_id == req.session_id:
                    session = sess
                    print(f"[API] Cancel: found via session_id-only match (was '{a_name}/{u_id}')")
                    break
        
        if session is None:
            print(f"[API] Cancel: all search strategies failed for session_id={req.session_id}")
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
            # [Critical Fix] dispatch_task 发送给 Worker 的参数是：
            #   app_name = f"swarm_from_{CURRENT_NODE_PORT}"   (Leader 端口)
            #   user_id  = _original_user_id                   (人类用户 ID，如 "dwh")
            #   session_id = use_session_id                    (如 "sub_87207465")
            # 所以 cancel 请求必须用一模一样的参数，Worker 才能找到对应的会话。
            
            swarm_app_name = f"swarm_from_{node_config.port}"  # 与 dispatch_task 一致
            human_user_id = request.user_id                     # 前端传来的真实人类用户 ID
            
            print(f" -> Sending Cancel to {worker_url} for {swarm_app_name}/{human_user_id}/{request.worker_session_id}")

            resp = await client.post(
                f"{worker_url}/api/cancel",
                json={
                    "app_name": swarm_app_name,
                    "user_id": human_user_id,
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
            "app_name": s.app_name,
            "user_id": s.user_id,
            "task_type": s.state.get('task_type') if hasattr(s, 'state') and s.state else None,
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
    
    # [核心修复] 处理 rewind 标记事件
    # runner.rewind_async 不删除 DB 记录，而是追加一个特殊的"回退标记"事件
    # 该事件的 event.actions.rewind_before_invocation_id 不为空
    #
    # 正确逻辑（镜像 ADK contents.py 的 _get_contents 实现）：
    # - 找到所有 rewind 标记的位置（marker_idx）及其目标 invocation_id
    # - 只跳过 [被回退 invocation_id 首次出现位置, marker_idx] 之间的事件
    # - marker 之后的新对话事件必须保留
    events_list = session.events
    
    # 计算需要排除的事件索引集合
    exclude_indices = set()
    for marker_idx, event in enumerate(events_list):
        actions = getattr(event, 'actions', None)
        if not actions:
            continue
        rewind_target = getattr(actions, 'rewind_before_invocation_id', None)
        if not rewind_target:
            continue
        
        # 找到目标 invocation_id 在标记之前最早出现的位置
        target_start_idx = None
        for j in range(marker_idx):
            if getattr(events_list[j], 'invocation_id', None) == rewind_target:
                target_start_idx = j
                break
        
        if target_start_idx is not None:
            # 排除 [target_start_idx, marker_idx] 区间（含标记自身）
            for k in range(target_start_idx, marker_idx + 1):
                exclude_indices.add(k)
            print(f"[历史] rewind 标记检测到，排除事件 {target_start_idx}~{marker_idx} ({rewind_target})")
    
    effective_events = [e for idx, e in enumerate(events_list) if idx not in exclude_indices]
    
    
    messages = []
    for event_idx, event in enumerate(effective_events):
        if hasattr(event, 'content') and event.content:
            role = 'unknown'
            if hasattr(event.content, 'role'):
                role = event.content.role
            elif hasattr(event, 'author'):
                role = event.author
            
            text_content = ""
            blocks = []
            images = []  # [多模态] 存储图片的 Base64 data URL
            
            # [调试日志] 输出 event 的详细信息（通过环境变量控制）
            import os
            DEBUG_HISTORY = os.getenv('DEBUG_HISTORY', 'false').lower() == 'true'

            if DEBUG_HISTORY:
                print(f"\n[历史消息调试] Event {event_idx} - Role: {role}")
                print(f"[历史消息调试] Event {event_idx} - Content 类型: {type(event.content)}")

            if hasattr(event.content, 'parts'):
                if DEBUG_HISTORY:
                    print(f"[历史消息调试] Event {event_idx} - Parts 数量: {len(event.content.parts)}")
                for part_idx, part in enumerate(event.content.parts):
                    if DEBUG_HISTORY:
                        print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 类型: {type(part)}")

                    # 检查 text
                    if hasattr(part, 'text') and part.text:
                        if DEBUG_HISTORY:
                            print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 有 text (长度:{len(part.text)})")
                        # 检查是否是思考过程
                        if getattr(part, 'thought', False):
                            blocks.append({"type": "thought", "content": part.text})
                        else:
                            cleaned_text, had_think_leak = strip_leaked_think_from_text(part.text)
                            if had_think_leak and not cleaned_text:
                                continue
                            blocks.append({"type": "text", "content": cleaned_text})
                            text_content += cleaned_text

                    # [多模态] 检查 inline_data（图片）
                    if hasattr(part, 'inline_data') and part.inline_data:
                        blob = part.inline_data
                        mime_type = getattr(blob, 'mime_type', 'image/png')
                        img_bytes = getattr(blob, 'data', b'')
                        if img_bytes:
                            b64_str = b64_module.b64encode(img_bytes).decode('utf-8')
                            data_url = f"data:{mime_type};base64,{b64_str}"
                            images.append(data_url)
                            if DEBUG_HISTORY:
                                print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 有图片 ({mime_type}, {len(img_bytes)} bytes)")

                    # 检查 function_call
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        if DEBUG_HISTORY:
                            print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 有 function_call: {fc.name}")
                        blocks.append({
                            "type": "tool_call",
                            "content": f"{fc.name} 输入参数: {fc.args}",
                            "tool_name": fc.name,
                            "tool_args": fc.args
                        })

                    # 检查 function_response
                    if hasattr(part, 'function_response'):
                        if DEBUG_HISTORY:
                            print(f"[历史消息调试] Event {event_idx} Part {part_idx} - hasattr(function_response): True")
                            print(f"[历史消息调试] Event {event_idx} Part {part_idx} - function_response value: {part.function_response}")
                        if part.function_response:
                            fr = part.function_response
                            if DEBUG_HISTORY:
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
                        elif DEBUG_HISTORY:
                            print(f"[历史消息调试] Event {event_idx} Part {part_idx} - function_response 是 None")
                    elif DEBUG_HISTORY:
                        print(f"[历史消息调试] Event {event_idx} Part {part_idx} - 没有 function_response 属性")

            if DEBUG_HISTORY:
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
            
            if DEBUG_HISTORY:
                print(f"[历史消息调试] Event {event_idx} - 合并后 blocks 数量: {len(merged_blocks)}")

            # [关键修复] 如果消息只包含 tool_result，则强制 role 为 'model'
            # 原因：Google ADK 中 function_response 的 role 是 'user'，但从 UI 角度看
            # tool_result 应该和 tool_call 一样在左侧对齐（都是系统操作）
            only_tool_results = all(block['type'] == 'tool_result' for block in merged_blocks) if merged_blocks else False
            if only_tool_results and role == 'user':
                if DEBUG_HISTORY:
                    print(f"[历史消息调试] Event {event_idx} - 检测到只包含 tool_result，将 role 从 'user' 改为 'model'")
                role = 'model'
            
            if role == 'user' or role == 'model':
                inv_id = getattr(event, 'invocation_id', None)
                if not inv_id and hasattr(event, 'model_extra') and event.model_extra:
                    inv_id = event.model_extra.get('invocation_id')
                elif getattr(event, '__dict__', None) and 'invocation_id' in event.__dict__:
                    inv_id = event.__dict__['invocation_id']
                    
                msg_data = {
                    "role": role,
                    "blocks": merged_blocks,
                    "text": text_content,
                    # 👇 [新增] 暴露 invocation_id 给前端
                    "invocation_id": inv_id
                }
                # [多模态] 如果有图片，附加到消息中
                if images:
                    msg_data["images"] = images
                messages.append(msg_data)
    
    return {"messages": messages}

@app.post("/api/sessions/{session_id}/rewind")
async def rewind_session_endpoint(session_id: str, req: RewindRequest):
    """
    [新增] 原生轻量级回退 (纯上下文洗脑)
    重置 Agent 的记忆和状态，不处理外部物理文件。
    """
    global session_manager
    if session_manager is None:
        return {"status": "error", "message": "SessionManager not initialized"}
        
    try:
        # 1. 获取当前会话 (支持多租户隔离)
        steering_session = session_manager.get_or_create(req.app_name, req.user_id, session_id)
        
        # 2. 实例化原生 Runner
        runner = Runner(
            agent=steering_session.agent, 
            app_name=req.app_name, 
            session_service=steering_session.session_service
        )
        
        print(f"[Rewind] 准备清除 Session {session_id} 的历史记忆 (目标节点: {req.invocation_id})...")
        
        # 3. 执行原生洗脑（底层会自动计算状态差，并触发 DB 的孤儿级联删除）
        await runner.rewind_async(
            user_id=req.user_id,
            session_id=session_id,
            rewind_before_invocation_id=req.invocation_id
        )
        
        print(f"[Rewind] 记忆清洗完成！Agent 已恢复到该节点前的干净状态。")
        return {"status": "success", "message": "Context rewound successfully."}
        
    except Exception as e:
        print(f"[Rewind] 回退失败: {e}")
        return {"status": "error", "message": str(e)}

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
        if isinstance(session_service, FullyCustomDbService):
            await session_service.save_session_state(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=session.state,
            )
        else:
            await session_service.save_session(session)
        
        print(f"[Swarm Metadata] ✅ Session {session_id} 元数据已更新: {metadata}")
        return {"status": "success", "message": "Metadata updated"}
        
    except Exception as e:
        print(f"[Swarm Metadata] ❌ 更新失败: {e}")
        return {"status": "error", "message": str(e)}, 500


@app.get("/api/context/user_sessions")
async def get_user_sessions(
    user_id: str = DEFAULT_USER_ID
):
    """
    [轻量级] 列出该用户名下的所有会话摘要（不含完整对话历史）。
    用于广播发现模式：从任意节点查看"我在这个节点上有哪些任务"。
    """
    try:
        sessions_response = await session_service.list_sessions(app_name="*", user_id=user_id)
        sessions = sessions_response.sessions if sessions_response else []
        
        if not sessions:
            return {"sessions": [], "count": 0}
        
        result = []
        for s in sessions:
            task_type = None
            title = "Untitled"
            if hasattr(s, 'state') and s.state:
                title = s.state.get('title', 'Untitled')
                task_type = s.state.get('task_type', None)
            
            updated_at = None
            if hasattr(s, '_db_updated_at') and s._db_updated_at:
                updated_at = s._db_updated_at.isoformat()
            
            result.append({
                "session_id": s.id,
                "app_name": s.app_name,
                "title": title,
                "task_type": task_type,
                "updated_at": updated_at
            })
        
        return {"sessions": result, "count": len(result)}
    except Exception as e:
        print(f"[User Sessions API] Error: {e}")
        return {"sessions": [], "count": 0, "error": str(e)}


@app.get("/api/context/leader_summary")
async def get_leader_summary(
    app_name: str = DEFAULT_APP_NAME,
    user_id: str = DEFAULT_USER_ID,
    session_id: str = None,
    limit: int = 1
):
    """
    [跨节点上下文查询] 支持两种模式：
    1. 精准模式: 传入 session_id，直接查询该会话的完整对话
    2. 最新模式: 不传 session_id，查最新会话 (fallback)
    """
    try:
        print(f"[Leader Summary API] 收到请求: app_name={app_name}, user_id={user_id}, session_id={session_id}, limit={limit}")
        
        target_session = None
        
        # === 模式 1: 精准查询 (有 session_id) ===
        if session_id:
            # 如果 app_name 不是通配符，先尝试直接用它查
            if app_name != "*":
                target_session = await session_service.get_session(
                    app_name=app_name, user_id=user_id, session_id=session_id
                )
            
            # 如果直接查失败（或 app_name 是通配符），用 list_sessions 全局扫描
            if not target_session:
                print(f"[Leader Summary API] 精准查找: 全局搜索 session_id={session_id}...")
                all_sessions_resp = await session_service.list_sessions(app_name="*", user_id=user_id)
                for s in (all_sessions_resp.sessions if all_sessions_resp else []):
                    if s.id == session_id:
                        target_session = await session_service.get_session(
                            app_name=s.app_name, user_id=user_id, session_id=session_id
                        )
                        if target_session:
                            print(f"[Leader Summary API] 全局搜索成功! 在 '{s.app_name}' 下找到")
                        break
            
            if not target_session:
                return {"error": f"Session {session_id} not found for user {user_id}"}
        
        # === 模式 2: 最新模式 (无 session_id, fallback) ===
        else:
            sessions_response = await session_service.list_sessions(app_name=app_name, user_id=user_id)
            sessions = sessions_response.sessions if sessions_response else []
            
            if not sessions:
                return {"error": "No sessions found"}
            
            latest_meta = sessions[0]
            real_app_name = latest_meta.app_name
            real_session_id = latest_meta.id
            
            print(f"[Leader Summary API] 锁定最新会话: {real_app_name} / {real_session_id}")
            
            target_session = await session_service.get_session(
                app_name=real_app_name, user_id=user_id, session_id=real_session_id
            )
            if not target_session:
                target_session = latest_meta
        
        # === 统一: 提取对话摘要 ===
        recent_messages = []
        if target_session.events:
            for evt in target_session.events[-100:]:
                if hasattr(evt, 'content') and evt.content:
                    role = evt.content.role if hasattr(evt.content, 'role') else 'unknown'
                    text = ""
                    if hasattr(evt.content, 'parts'):
                        for part in evt.content.parts:
                            if hasattr(part, 'text') and part.text:
                                text += part.text
                    if text:
                        recent_messages.append({"role": role, "text": text})
        
        summary_lines = []
        for msg in recent_messages:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            summary_lines.append(f"{prefix}: {msg['text']}")
        
        result = {
            "title": target_session.state.get('title', 'Untitled') if target_session.state else 'Untitled',
            "session_id": target_session.id,
            "app_name": target_session.app_name,
            "recent_summary": " ".join(summary_lines),
            "total_messages": len(target_session.events) if target_session.events else 0
        }
        return result
            
    except Exception as e:
        print(f"[Swarm Context API] Error: {e}")
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

@app.websocket("/ws/audio")
async def websocket_audio_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[WS] 前端已连接语音流")
    
    global stt_engine
    if not stt_engine:
        await websocket.close(code=1011, reason="STT model not initialized")
        return

    # 为每个连接创建一个独立的识别流
    stream = stt_engine.create_stream()
    last_text = ""

    try:
        while True:
            # 1. 接收前端发来的二进制音频数据 (Float32 格式)
            data = await websocket.receive_bytes()
            
            # 2. 转换数据格式
            samples = np.frombuffer(data, dtype=np.float32)
            
            # 3. 喂给模型
            stream.accept_waveform(16000, samples)
            
            # 4. 解码
            while stt_engine.is_ready(stream):
                stt_engine.decode_stream(stream)
            
            # 5. 获取结果
            text = stt_engine.get_result(stream)
            
            # 6. 如果有新内容，发回前端
            if text != last_text:
                last_text = text
                # 发送 JSON，包含 is_final 标记
                is_endpoint = stt_engine.is_endpoint(stream)
                await websocket.send_json({
                    "text": text,
                    "is_final": is_endpoint
                })
                
                # 如果检测到一句话结束，重置流
                if is_endpoint:
                    stt_engine.reset(stream)
                    last_text = ""

    except WebSocketDisconnect:
        print("[WS] 语音连接断开")
    except Exception as e:
        print(f"[WS] 异常: {e}")

@app.on_event("startup")
async def startup_event():
    init_streaming_stt()
    init_registry_db()
    await create_agent()
    register_self()
    asyncio.create_task(heartbeat_daemon())
    
    # === [去中心化拉模型] 动态加载自领守护后台协程 ===
    asyncio.create_task(init_decentralized_claim_loop())
    
    print(f"[Node-{node_config.port}] 🚀 服务已完全启动 (已加入 Swarm, Heartbeat ON)")

async def init_decentralized_claim_loop():
    """动态加载并开启 SelfClaimLoop 后台守护 (2.2 彻底净化版)"""
    await asyncio.sleep(3) # 留出时间让服务充分启动
    try:
        from skills.agent_team_to_be_update.self_claim_loop import SelfClaimLoop
        
        # 1. 统一协调目录（必须与 _get_coordination_dir(team_id) 保持一致，加上 team_id 子目录）
        _team_id_for_dir = os.environ.get("ADK_TEAM_ID", "swarm_team").strip()
        coord_dir = os.environ.get("ADK_COORDINATION_DIR", "coordination").strip()
        if not os.path.isabs(coord_dir):
            coord_dir = os.path.abspath(coord_dir)
        coord_dir = os.path.join(coord_dir, _team_id_for_dir)
        print(f"[Node-{node_config.port}] 🔍 巡检锚点定向: {coord_dir}")

        # 2. 构造干净、隔离的本地执行器
        async def task_executor(task):
            import traceback
            print(f"[SelfClaimDaemon] ⚔️ 认领工单: {task.id} | {task.name}")
            old_cwd = os.getcwd()
            
            safe_cwd = coord_dir
            try:
                t_files = getattr(task, "writable_files", []) or getattr(task, "expected_artifacts", [])
                if not t_files and hasattr(task, "to_dict"):
                    t_f_dict = task.to_dict()
                    t_files = t_f_dict.get("writable_files", []) or t_f_dict.get("writableFiles", [])
                
                if t_files and isinstance(t_files, list) and len(t_files) > 0 and os.path.isabs(t_files[0]):
                    safe_cwd = os.path.dirname(t_files[0])
            except Exception: pass
            
            print(f"[SelfClaimDaemon] 🛡️ 切入安全隔离 CWD: {safe_cwd}")
            os.makedirs(safe_cwd, exist_ok=True)
            os.chdir(safe_cwd)
            
            try:
                full_text_response = ""
                async for chunk in run_agent(
                    task=task.description,
                    app_name="decentralized",
                    user_id=f"worker_{node_config.port}",
                    session_id=f"task_{task.id[:8]}"
                ):
                    if isinstance(chunk, str): full_text_response += chunk
                    elif isinstance(chunk, dict) and 'content' in chunk: full_text_response += str(chunk['content'])
                return {"status": "success", "response": full_text_response}
            except Exception as e:
                print(f"[SelfClaimDaemon] 执行报错: {e}")
                raise e
            finally:
                os.chdir(old_cwd)
                print(f"[SelfClaimDaemon] 🔄 恢复 CWD: {old_cwd}")

        daemon = SelfClaimLoop(
            agent_id=f"Node-{node_config.port}",
            agent_port=node_config.port, 
            team_id="swarm_team",        
            coordination_dir=coord_dir, 
            task_executor=task_executor
        )
        print(f"[Node-{node_config.port}] 去中心化巡检后台巡常启动 ✅")
        await daemon.run() # 👈 修正为正确的 run() ！！！
    except Exception as e:
        print(f"[Node-{node_config.port}] 去中心化后台挂载异常自愈失败 ❌: {e}")

@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

@app.on_event("shutdown")
async def shutdown_event():
    deregister_self()

# ==========================================
# [新增] 本地图片代理接口 (增强版)
# ==========================================
from urllib.parse import unquote

@app.get("/api/local_image")
async def get_local_image(path: str):
    """
    代理本地图片文件，供前端 Markdown 渲染使用。
    增强功能：支持相对路径自动补全、支持 Windows 路径修正
    """
    # 1. URL 解码 (防止路径中包含 %20 等字符)
    try:
        clean_path = unquote(path)
    except:
        clean_path = path

    # 2. 去除可能存在的引号 (Agent 有时会输出 path="D:/...")
    clean_path = clean_path.strip('"\'')

    # 3. 路径查找策略
    candidate_paths = [
        clean_path,  # 尝试原始路径
        os.path.abspath(clean_path),  # 尝试转为绝对路径 (基于当前 CWD)
        os.path.join(os.getcwd(), clean_path)  # 强制拼接当前目录
    ]

    final_path = None
    for p in candidate_paths:
        if os.path.exists(p) and os.path.isfile(p):
            final_path = p
            break

    # 4. 如果还是找不到，返回 404
    if not final_path:
        print(f"[Image API] ❌ 404 Not Found: {path} (Tried: {candidate_paths})")
        return Response(content="File not found", status_code=404)

    # 5. 安全校验：只允许图片
    valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')
    if not final_path.lower().endswith(valid_extensions):
        return Response(content="Not a valid image file", status_code=400)

    # 6. 返回文件
    print(f"[Image API] ✅ Serving: {final_path}")
    return FileResponse(final_path)

def start_web_server(port: int):
    print(f"Starting web server at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    
    node_config.port = args.port
    
    # [新增] 启动时根据端口配置独立日志文件
    try:
        from src.adk_agent.core.simple_file_logger import default_logger as file_logger
        new_log_path = f"logs/agent_{args.port}.log"
        file_logger.configure(new_log_path)
        print(f"[System] Logger redirected to: {new_log_path}")
    except Exception as e:
        print(f"[System] ⚠️ Failed to redirect logger: {e}")
    
    # 【核心】注入环境变量，解耦工具
    os.environ["ADK_CURRENT_PORT"] = str(args.port)
    
    print(f"=== 🚀 启动通用全能智能体节点 ===")
    print(f"🏠 端口: {node_config.port}")
    print(f"💾 隔离数据库: adk_sessions_port_{node_config.port}.db")
    start_web_server(node_config.port)
