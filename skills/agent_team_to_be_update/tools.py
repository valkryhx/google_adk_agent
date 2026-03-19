import httpx
import json
import uuid
import os
import random
import sqlite3
import asyncio
import time
import re
from datetime import datetime
from typing import List, Optional, Union

# ==========================================
# 独立的极简文件日志 (解耦，不依赖主控节点代码)
# ==========================================
def _get_skill_logger():
    port = os.environ.get("ADK_CURRENT_PORT", 0)
    log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", f"agent_{port}.log")
    
    def log_print(msg: str):
        # 同时打印到控制台
        print(msg)
        # 尝试追加到日志文件
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            log_line = f"{timestamp} - INFO - {msg}\n"
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception:
            pass
            
    return log_print

skill_log = _get_skill_logger()

# ==========================================
# 配置与常量
# ==========================================
# ==========================================
# 配置与常量
# ==========================================
# 使用基于文件的绝对路径，不依赖CWD
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_DB = os.path.join(_PROJECT_ROOT, "sqlite_db", "swarm_registry.db")
CLUSTER_APP_NAME = "adk_universal_swarm"

# 【关键】从环境变量获取当前节点端口，实现自我认知
# 如果未设置（如本地测试），默认为 0
CURRENT_NODE_PORT = int(os.environ.get("ADK_CURRENT_PORT", 0))

# ==========================================
# 辅助函数：服务发现与健康管理
# ==========================================

def _get_active_workers() -> List[dict]:
    """
    [Dynamic Elasticity] 从 SQLite 注册表中获取活跃的 Worker 节点。
    会自动排除当前节点自己，并过滤掉心跳超时的僵尸节点。
    """
    if not os.path.exists(REGISTRY_DB):
        return []
    
    # [Dynamic Elasticity] 定义超时阈值（15 秒没心跳就认为挂了）
    HEARTBEAT_TIMEOUT = 15.0
    current_time = time.time()
    
    try:
        # 使用 timeout 防止数据库锁竞争
        with sqlite3.connect(REGISTRY_DB, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT port, url, last_seen FROM nodes WHERE status='active'")
            rows = cursor.fetchall()
            
            workers = []
            dead_ports = []
            
            for row in rows:
                # [Dynamic Elasticity] 检查心跳
                last_seen = row['last_seen'] or 0
                if current_time - last_seen > HEARTBEAT_TIMEOUT:
                    dead_ports.append(row['port'])
                    continue

                # 自我排除逻辑
                if CURRENT_NODE_PORT and int(row['port']) == CURRENT_NODE_PORT:
                    continue 
                workers.append({"port": row['port'], "url": row['url']})
            
            # 日志记录僵尸节点
            if dead_ports:
                print(f"[Swarm Discovery] 发现并忽略心跳超时节点: {dead_ports}")
                
            return workers
    except Exception as e:
        print(f"[Swarm Discovery Error] {e}")
        return []

def _get_all_nodes(include_self=True) -> List[dict]:
    """
    获取所有在线节点（含或不含自身），用于广播查询。
    与 _get_active_workers 的区别：不排除自身节点。
    """
    if not os.path.exists(REGISTRY_DB):
        return []
    
    HEARTBEAT_TIMEOUT = 15.0
    current_time = time.time()
    
    try:
        with sqlite3.connect(REGISTRY_DB, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT port, url, last_seen FROM nodes WHERE status='active'")
            rows = cursor.fetchall()
            
            nodes = []
            for row in rows:
                last_seen = row['last_seen'] or 0
                if current_time - last_seen > HEARTBEAT_TIMEOUT:
                    continue
                if not include_self and CURRENT_NODE_PORT and int(row['port']) == CURRENT_NODE_PORT:
                    continue
                nodes.append({"port": row['port'], "url": row['url']})
            return nodes
    except Exception as e:
        print(f"[Swarm Discovery Error] _get_all_nodes: {e}")
        return []

def _remove_dead_node(port: int):
    """
    【自愈机制】惰性清理：当发现节点无法连接时，将其从注册表中移除。
    """
    try:
        print(f"[Swarm Self-Healing] ⚰️ 检测到僵尸节点 (Port {port})，正在移除...")
        with sqlite3.connect(REGISTRY_DB, timeout=5.0) as conn:
            conn.execute("DELETE FROM nodes WHERE port = ?", (port,))
    except Exception as e:
        print(f"[Swarm Cleanup Error] {e}")

# ==========================================
# 核心工具：任务分发
# ==========================================

# Debug: Confirm File Loading
print(f"LOADING remote_worker_connector tools.py from {__file__}")

async def dispatch_task(
    task_instruction: str, 
    context_info: Optional[str] = "",
    target_port: Optional[int] = None,
    sub_session_id: Optional[str] = None,
    priority: str = "NORMAL",
    _status_reporter = None,
    _original_user_id: str = "unknown",  # 传递原始人类用户 ID
    _meeting_context: dict = None  # hold_meeting 透传的轮次/角色信息
) -> str:
    # === [去中心化架构] 该函数已废弃且熔断禁用！ ===
    raise NotImplementedError("dispatch_task is fully disabled. Please use task_create instead.")

    # [防御] LLM 可能把 _status_reporter 当普通参数传入字符串，必须校验
    if not callable(_status_reporter):
        _status_reporter = None
    # [New] 非侵入式打标：通过 status_reporter 发送信号
    if _status_reporter:
        try:
            # 发送特定的元数据更新信号
            import inspect
            res = _status_reporter("update_session_state", {
                "task_type": "swarm_leader",
                "swarm_mode": "single_dispatch"
            })
            if inspect.isawaitable(res):
                await res
            print(f"[Swarm Leader] Sent session tagging signal (Single)")
        except Exception as e:
            print(f"[Swarm Leader] Failed to send tagging signal: {e}")

    """
    【集群指挥官核心工具】将任务分发给 Swarm 集群中的其他智能体。
    
    本工具支持自动负载均衡、状态保持（多轮对话）以及紧急抢占。
    Leader 应当只关注“派活”和“收结果”，具体的执行过程由 Worker 在其独立进程中完成。

    Args:
        task_instruction (str): 给 Worker 的具体任务指令。请清晰、明确。
                                ⚠️ [禁止] 不要用此工具来“询问状态”或“获取进度”！
                                如需获取对方状态，请直接使用 `sync_task_context` 工具。
        context_info (str): 任务背景信息（如之前的代码片段、需求文档摘要）。
        target_port (int, optional): 指定发送给哪个端口的 Worker。
                                     - 如果是新任务，留空 (None)，系统会自动选择空闲节点。
                                     - 如果是多轮对话（如 Review 后的修改），必须传入上次的端口。
        sub_session_id (str, optional): 指定子任务的会话 ID。
                                        - 如果留空，自动生成新会话。
                                        - 如果需要 Worker 记住之前的上下文，必须传入上次返回的 session_id。
        priority (str): 任务优先级，默认 "NORMAL"。
                        - "NORMAL": 如果对方忙，则尝试寻找其他人。
                        - "URGENT": 仅在 target_port 被指定且对方忙碌时有效。将强制打断对方当前任务并插队。
    """
    
    # 1. 获取所有候选人
    active_workers = _get_active_workers()
    
    if not active_workers:
        # [Dynamic Elasticity] 返回带有强烈暗示的指令，触发应急接管
        return (
            f"[SWARM SYSTEM ALERT] 集群全员离线！\n"
            f"紧急协议已触发：你现在是唯一的执行者。\n"
            f"立即停止调度，马上使用你本地的 Tool (bash/file_editor/python/skill_load) 亲自执行此任务！\n"
            f"任务内容回顾：{task_instruction}"
        )

    # 2. 确定候选列表
    candidates = []
    if target_port:
        # 定向分派模式：只找那一个人
        candidates = [w for w in active_workers if int(w['port']) == int(target_port)]
        if not candidates:
            return f"[Error] 指定的目标 Worker (Port {target_port}) 已离线或不存在。请重新规划任务。"
    else:
        # 自动调度模式：打乱列表，实现随机负载均衡
        candidates = active_workers.copy()
        random.shuffle(candidates)

    # 3. 准备基础 Payload
    # 构造 Worker 端的 System Prompt 约束，要求其简洁汇报
    system_instruction_injection = (
        f"\n\n⚠️【重要汇报要求】⚠️\n"
        f"1. 你是 Swarm 集群中的 Worker 节点，正在协助 Leader (Port {CURRENT_NODE_PORT})。\n"
        f"2. 请直接执行任务，不要返回冗长的思考过程。\n"
        f"3. 最终回复必须简洁明了。如果是代码任务，只汇报‘文件已生成于 xxx’，不要打印全量代码。\n"
        f"4. 遇到错误直接汇报错误原因。"
    )
    
    full_message = f"【背景】\n[本次任务的Leader节点: Node {CURRENT_NODE_PORT}]\n{context_info}\n\n【任务】\n{task_instruction}{system_instruction_injection}"
    
    # 处理紧急抢占标记
    if priority.upper() == "URGENT":
        full_message = "[URGENT_INTERRUPT] " + full_message
        print(f"[Swarm] 发送紧急打断指令 -> Target Candidates: {[c['port'] for c in candidates]}")
    
    caller_id = f"Agent_Node_{CURRENT_NODE_PORT}"
    use_session_id = sub_session_id or f"sub_{uuid.uuid4().hex[:8]}"

    # Reporting Helper
    def report(event_type, data):
        if _status_reporter:
            if _meeting_context:
                data = {**data, **_meeting_context}
            _status_reporter(event_type, data)

    # 4. 开始尝试调度（轮询候选人）
    last_error = ""
    
    # 增加重试机制，防止网络抖动导致的误判
    max_retries = 2 # [Optimized] Reduced from 5 to 2 (total 3 attempts)

    for worker in candidates:
        worker_port = worker['port']
        worker_url = worker['url']
        
        # [优化] 增加微小的随机等待，避免 Batch 模式下瞬间请求风暴
        # [Optimized] Reduced sleep time significantly for faster dispatch
        await asyncio.sleep(random.uniform(0.1, 1.0))
        
        print(f"[Swarm Dispatch] 📡 正在连接 Worker {worker_port} (Session: {use_session_id})...")
        
        # [优化] 提前发送 init 事件，让前端立即创建 Worker 卡片
        # 不再等待 HTTP 200 响应，避免慢 LLM 导致卡片延迟出现
        report('init', {
            "worker_port": worker_port, 
            "session_id": use_session_id,
            "task_preview": task_instruction[:50] + "..."
        })

        payload = {
            "message": full_message,
            "app_name": f"swarm_from_{CURRENT_NODE_PORT}",  # 命名空间分离：按来源区分
            "user_id": _original_user_id,  # 保持原始人类用户 ID
            "session_id": use_session_id
        }

        worker_failed_completely = False
        for attempt in range(max_retries + 1):
            try:
                # [Dynamic Elasticity] 使用极短的连接超时实现快速失败 (Fast Fail)
                # Connect: 2.0s (如果连不上，说明挂了)
                # Read: 180.0s (如果连上了，给它时间执行任务)
                timeout_config = httpx.Timeout(180.0, connect=2.0)
                
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    async with client.stream("POST", f"{worker_url}/api/chat", json=payload) as response:
                        
                        # === 场景 A: 对方忙碌 (503) ===
                        if response.status_code == 503:
                            # 如果是指定了 target_port，我们不能换人，必须报错让 Leader 决定
                            if target_port:
                                error_json = await response.json()
                                task_preview = error_json.get('current_task', 'Unknown')
                                msg = f"【调度冲突】目标 Worker ({worker_port}) 正在忙碌: {task_preview}"
                                report('fail', {"worker_port": worker_port, "session_id": use_session_id, "error": msg})
                                return msg
                            else:
                                # 如果是随机分配，那就找下一个人
                                print(f"[Swarm] Worker {worker_port} 正忙，尝试下一个...")
                                report('retry', {"worker_port": worker_port, "session_id": use_session_id, "retry_reason": "Worker busy"})
                                break # 跳出重试，尝试下一个 candidate

                        # === 场景 B: 连接成功 (200) ===
                        if response.status_code == 200:
                            # report('init') 已提前发送，此处无需重复

                            # 【完整收集】收集所有类型的 chunk 内容，确保不遗漏工具执行结果
                            final_report = ""
                            async for line in response.aiter_lines():
                                if not line: continue
                                try:
                                    data = json.loads(line)
                                    chunk = data.get("chunk", {})
                                    chunk_type = chunk.get("type", "")
                                    content = chunk.get("content", "")
                                    
                                    if not content:
                                        continue
                                    
                                    # 根据类型收集内容
                                    if chunk_type == "text":
                                        final_report += content
                                    elif chunk_type == "tool_result":
                                        # 工具执行结果（搜索结果、代码输出等）
                                        final_report += f"\n[Tool Result]\n{content}\n"
                                    elif chunk_type == "tool_call":
                                        # 工具调用记录（简要记录，不占太多篇幅）
                                        tool_name = chunk.get("tool_name", "unknown")
                                        final_report += f"\n[Called: {tool_name}]\n"
                                    elif chunk_type == "thought":
                                        # 思考过程，跳过不收集
                                        pass
                                    elif chunk_type == "error":
                                        # 遇到内部错误 chunk，说明任务执行失败
                                        print(f"[Swarm] Worker {worker_port} 内部异常: {content}")
                                        report('fail', {
                                            "worker_port": worker_port, 
                                            "session_id": use_session_id, 
                                            "error": content
                                        })
                                        return f"【调度失败】Worker {worker_port} 内部异常: {content}"
                                    
                                    # [Report] 实时流 (Chunk) - 所有有内容的 chunk 都汇报
                                    if content and chunk_type in ("text", "tool_result"):
                                        report('chunk', {
                                            "worker_port": worker_port,
                                            "session_id": use_session_id,
                                            "content": content
                                        })
                                except Exception:
                                    continue
                            
                            # 成功！返回结构化报告
                            print(f"[Swarm] Worker {worker_port} 任务完成。")
                            
                            # [新增] 任务血缘记录：向 Worker 注入元数据
                            try:
                                metadata = {
                                    "task_type": "swarm_worker",
                                    "leader_port": CURRENT_NODE_PORT,
                                    "original_user_id": _original_user_id,
                                    "task_instruction": task_instruction[:100],
                                    "assigned_at": time.time()
                                }
                                
                                async with httpx.AsyncClient(timeout=5.0) as meta_client:
                                    await meta_client.post(
                                        f"{worker_url}/api/sessions/{use_session_id}/metadata",
                                        json={
                                            "app_name": f"swarm_from_{CURRENT_NODE_PORT}",
                                            "user_id": _original_user_id,
                                            "metadata": metadata
                                        }
                                    )
                                print(f"[Swarm] 已注入任务血缘元数据到 Worker {worker_port}")
                            except Exception as e:
                                print(f"[Swarm] 元数据注入失败: {e}")
                            
                            # [Report] 任务完成 (Finish)
                            report('finish', {"worker_port": worker_port, "session_id": use_session_id, "status": "success"})
                            
                            return (
                                f"[SWARM SUCCESS]\n"
                                f"\n"
                                f"执行节点: Worker Agent (Port {worker_port})\n"
                                f"会话 ID : {use_session_id}\n"
                                f"\n"
                                f"执行结果摘要:\n"
                                f"{final_report[:20000]}"
                                f"{'...(truncated)' if len(final_report) > 20000 else ''}"
                                f"\n"
                            )
                        
                        # === 场景 C: 其他错误 ===
                        last_error = f"HTTP {response.status_code}"
            
            # [Dynamic Elasticity] 情况一：连接被拒绝 (进程挂了/端口关闭) -> 立即移除，不再重试
            except (httpx.ConnectError, ConnectionRefusedError) as e:
                print(f"[Swarm] Worker {worker_port} 拒绝连接 (进程可能已结束): {e}")
                # 恢复自愈核心: 立即从数据库移除死节点
                _remove_dead_node(worker_port)
                report('fail', {"worker_port": worker_port, "session_id": use_session_id, "error": f"Connection refused"})
                worker_failed_completely = True
                last_error = f"Node {worker_port} Dead"
                break  # 不要再试这个端口了

            # [Dynamic Elasticity] 情况二：超时 (网络卡/负载高) -> 只是重试，不移除
            except httpx.TimeoutException:
                print(f"[Swarm] 连接 Worker {worker_port} 超时 (Attempt {attempt+1}/{max_retries+1})")
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue  # 在同一个节点重试
                else:
                    report('fail', {"worker_port": worker_port, "session_id": use_session_id, "error": "Connection timeout"})
                    worker_failed_completely = True
                    last_error = "Timeout"
                    # 多次超时也不移除，依靠心跳机制被动清理，防止误杀
            
            except Exception as e:
                print(f"[Swarm] 未知错误: {e}")
                report('fail', {"worker_port": worker_port, "session_id": use_session_id, "error": str(e)})
                worker_failed_completely = True
                last_error = str(e)
                break
        
        # 如果这个 Worker 彻底挂了
        if worker_failed_completely:
            if target_port:
                # 指定了目标，无法换人，报错
                return f"【调度失败】目标 Worker {target_port} 无法连接，可能已离线。"
            else:
                print(f"[Swarm] 切换到下一个候选节点...")
                continue

    # 5. 所有候选人都试过了，还是失败
    msg = f"【调度失败】所有 Worker ({len(candidates)}个) 均无法连接或执行失败。Last Error: {last_error}"
    report('fail', {"worker_port": 0, "error": msg})
    # [Dynamic Elasticity] 返回强制接管指令
    return (
        f"{msg}\n"
        f"\n"
        f"[SYSTEM FALLBACK] 自动降级程序启动：外部资源不可用。\n"
        f"你必须依靠自己完成任务。\n"
        f"请立即调用你本地的 bash 或 file_editor 工具开始工作！"
    )

# ==========================================
# [新增] 跨节点上下文同步工具
# ==========================================
async def sync_task_context(
    reason: str = "",
    target_ports = None,         # None=广播所有节点, int/List[int]=定向查询
    session_id: str = None,      # [新增] 精准模式：指定会话ID直接查看详情
    _session_service = None,
    _app_info = None
) -> str:
    """
    [三模式任务同步] 查询集群中的任务状态。

    三种使用模式（自动判断）：
    1. broadcast (广播发现): target_ports=None -> 自动发现所有在线节点，列出你名下的所有任务
    2. targeted (定向查询): target_ports=[8000,8001] -> 只查指定节点上你的任务
    3. precise (精准查看): target_ports=8001, session_id="abc123" -> 按会话ID查看完整对话详情

    Args:
        reason (str): 同步原因（如"查看进度"、"确认子任务完成"）。
        target_ports (int | List[int], optional): 目标节点端口。不传则广播查询所有在线节点。
        session_id (str, optional): 精准查询的会话ID。传入后将获取完整对话历史而非摘要列表。
    """
    try:
        # 1. 获取当前用户身份
        current_user_id = _app_info.get("user_id", "unknown")
        
        # 尝试从 Session State 获取更准确的 original_user_id (Worker模式兼容)
        try:
            current_session = await _session_service.get_session(
                app_name=_app_info.get("app_name", ""),
                user_id=_app_info.get("user_id", ""),
                session_id=_app_info.get("session_id", "")
            )
            if current_session and current_session.state:
                current_user_id = current_session.state.get('original_user_id', current_user_id)
        except Exception:
            pass

        # 2. 确定目标端口
        targets = []
        query_mode = "broadcast"  # 默认广播

        if target_ports:
            # LLM 输入类型兼容处理
            if isinstance(target_ports, str):
                try:
                    parsed = json.loads(target_ports)
                    if isinstance(parsed, list): targets = [int(p) for p in parsed]
                    elif isinstance(parsed, int): targets = [parsed]
                    else: targets = [int(p.strip()) for p in target_ports.split(',')]
                except Exception:
                    try: targets = [int(target_ports)]
                    except Exception: pass
            elif isinstance(target_ports, list): targets = [int(p) for p in target_ports]
            elif isinstance(target_ports, int): targets = [target_ports]
            
            query_mode = "precise" if session_id else "targeted"
        else:
            # 广播模式：从注册表发现所有在线节点
            all_nodes = _get_all_nodes(include_self=True)
            if not all_nodes:
                return "[Sync] 无法发现任何在线节点。请检查集群状态或指定 target_ports。"
            targets = [int(n['port']) for n in all_nodes]

        print(f"[Swarm Sync] 模式: {query_mode}, 身份: {current_user_id}, 目标: {targets}")

        # 3. 单节点查询逻辑
        async def _query_node_sessions(port):
            """轻量级：列出该节点上用户的所有会话"""
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"http://localhost:{port}/api/context/user_sessions",
                        params={"user_id": current_user_id}
                    )
                    if response.status_code != 200:
                        return {"port": port, "error": f"HTTP {response.status_code}"}
                    data = response.json()
                    return {"port": port, "success": True, "sessions": data.get("sessions", []), "count": data.get("count", 0)}
            except Exception as e:
                return {"port": port, "error": str(e)}

        async def _query_node_detail(port, sid):
            """精准模式：按 session_id 获取完整对话"""
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"http://localhost:{port}/api/context/leader_summary",
                        params={
                            "app_name": "*",
                            "user_id": current_user_id,
                            "session_id": sid
                        }
                    )
                    if response.status_code != 200:
                        return {"port": port, "error": f"HTTP {response.status_code}"}
                    data = response.json()
                    if "error" in data:
                        return {"port": port, "error": data['error']}
                    return {"port": port, "success": True, "data": data}
            except Exception as e:
                return {"port": port, "error": str(e)}

        # 4. 执行查询
        if query_mode == "precise":
            # 精准模式：按 session_id 查一台或多台节点
            results = await asyncio.gather(*[_query_node_detail(p, session_id) for p in targets])
            return _format_detail_results(current_user_id, targets, results, session_id)
        else:
            # 广播/定向模式：列出各节点上的会话列表
            results = await asyncio.gather(*[_query_node_sessions(p) for p in targets])
            return _format_discovery_results(current_user_id, targets, results, query_mode)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"[Sync Error] {e}"


def _format_discovery_results(user_id, targets, results, mode):
    """格式化广播/定向模式的发现结果"""
    parts = [
        "[Swarm Task Discovery Report]",
        "=" * 40,
        f"User: {user_id}",
        f"Mode: {'Broadcast (all nodes)' if mode == 'broadcast' else 'Targeted'}",
        f"Nodes queried: {targets}",
        ""
    ]
    
    total_sessions = 0
    online_count = 0
    
    for res in results:
        port = res['port']
        if "error" in res:
            parts.append(f"[X] Node {port}: {res['error']}")
        else:
            online_count += 1
            sessions = res.get('sessions', [])
            count = len(sessions)
            total_sessions += count
            
            if count == 0:
                parts.append(f"[OK] Node {port}: No sessions")
            else:
                parts.append(f"[OK] Node {port}: {count} session(s)")
                for s in sessions:
                    title = s.get('title', 'Untitled')
                    sid = s.get('session_id', '?')
                    task_type = s.get('task_type', '')
                    tag = f" [{task_type}]" if task_type else ""
                    updated = s.get('updated_at', '')
                    parts.append(f"     - [{sid}] {title}{tag}  ({updated})")
        parts.append("")
    
    parts.append("=" * 40)
    parts.append(f"Summary: {online_count}/{len(targets)} nodes responded, {total_sessions} total sessions found")
    
    if total_sessions > 0:
        parts.append("")
        parts.append("Tip: To view details of a specific session, call:")
        parts.append("  sync_task_context(target_ports=<port>, session_id='<session_id>')")
    
    return "\n".join(parts)


def _format_detail_results(user_id, targets, results, session_id):
    """格式化精准模式的详情结果"""
    parts = [
        "[Swarm Task Detail Report]",
        "=" * 40,
        f"User: {user_id}",
        f"Session: {session_id}",
        ""
    ]
    
    for res in results:
        port = res['port']
        if "error" in res:
            parts.append(f"[X] Node {port}: {res['error']}")
        else:
            data = res['data']
            parts.append(f"[OK] Node {port}: {data.get('title', 'Untitled')}")
            parts.append(f"     App: {data.get('app_name', '?')}")
            parts.append(f"     Messages: {data.get('total_messages', 0)}")
            summary_text = data.get('recent_summary', 'None')
            if len(summary_text) > 5000:
                summary_text = "..." + summary_text[-5000:]
            parts.append(f"     Conversation:")
            parts.append(f"     {summary_text}")
        parts.append("")
    
    parts.append("=" * 40)
    return "\n".join(parts)


async def dispatch_batch_tasks(
    tasks: List[str],
    common_context: Optional[str] = "",
    priority: str = "NORMAL",
    return_structured: bool = False,
    _status_reporter = None,
    _original_user_id: str = "unknown",
    _meeting_context: dict = None  # hold_meeting 透传的轮次/角色信息
) -> Union[str, List[dict]]:
    # === [去中心化架构] 该函数已废弃且熔断禁用！ ===
    raise NotImplementedError("dispatch_batch_tasks is fully disabled. Please use task_create instead.")

    """
    【并发加速】同时向集群分发多个并行任务。
    
    使用此工具可以一次性启动多个 Worker 并行工作，极大缩短总耗时。
    适用于：多维度搜索、多文件生成、批量数据处理等互不依赖的任务。
    
    Args:
        tasks (List[str]): 任务指令列表。例如 ["搜索苹果公司财报", "搜索微软公司财报"]。
        common_context (str): 所有任务共享的背景信息。
        priority (str): 优先级 (NORMAL/URGENT)。
        return_structured (bool): 内部参数。True 时返回结构化列表，供 hold_meeting 等上层工具使用。
    """
    
    # [防御] LLM 可能把 _status_reporter 当普通参数传入字符串，必须校验
    if not callable(_status_reporter):
        _status_reporter = None
    # [New] 非侵入式打标：通过 status_reporter 发送信号
    if _status_reporter:
        try:
            import inspect
            res = _status_reporter("update_session_state", {
                "task_type": "swarm_leader",
                "swarm_mode": "batch_dispatch",
                "active_workers": len(tasks)
            })
            if inspect.isawaitable(res):
                await res
            print(f"[Swarm Leader] Sent session tagging signal (Batch)")
        except Exception as e:
            print(f"[Swarm Leader] Failed to send tagging signal: {e}")

    if not tasks:
        return [] if return_structured else "【系统提示】任务列表为空，未执行任何操作。"

    print(f"\n[Swarm Batch] 正在启动 {len(tasks)} 个并发任务...")
    
    # [优化] 使用 Semaphore 限制最大并发数，防止瞬间请求过多导致本地端口耗尽或数据库锁死
    sem = asyncio.Semaphore(5) 

    async def _run_single_task(index, instruction):
        async with sem:
            task_with_id = f"[Batch-Task-{index+1}] {instruction}"
            print(f"  -> 启动子任务 {index+1}: {instruction[:20]}...")
            
            try:
                result = await dispatch_task(
                    task_instruction=task_with_id,
                    context_info=common_context,
                    target_port=None, 
                    sub_session_id=None,
                    priority=priority,
                    _status_reporter=_status_reporter,
                    _original_user_id=_original_user_id,
                    _meeting_context=_meeting_context
                )
                return {"index": index, "result": result, "success": "SWARM SUCCESS" in result}
            except Exception as e:
                error_msg = f"[Exception] {e}"
                print(f"[Swarm Batch] 子任务 {index+1} 异常: {e}")
                return {"index": index, "result": error_msg, "success": False}

    # 核心：asyncio.gather 并发执行
    results = await asyncio.gather(*[
        _run_single_task(i, task) for i, task in enumerate(tasks)
    ])
    
    print(f"[Swarm Batch] {len(tasks)} 个任务全部完成。")

    # [新增] 结构化返回模式
    if return_structured:
        return list(results)
    
    # [默认] 向后兼容：返回拼接字符串
    text_parts = [f"--- 任务 {r['index']+1} 结果 ---\n{r['result']}\n" for r in results]
    return f"【批量任务执行报告】\n共执行 {len(tasks)} 个并发任务。\n" + "\n".join(text_parts)

# ==========================================
# [新增] 群体会议工具
# ==========================================

async def hold_meeting(
    topic: str,
    participant_count: int = 3,
    max_rounds: int = 5,
    _status_reporter = None,
    _original_user_id: str = "unknown"
) -> str:
    """
    【群体会议】组织多个 Worker 围绕一个议题进行多轮讨论，最终形成会议纪要。

    Leader 作为主持人，每轮随机选取 Worker 参会，进行多轮观点碰撞。
    会议以"议题"为中心，每轮参会者可以不同（无状态设计），
    通过"会议纪要"传递历史上下文，任何 Worker 都能中途接入讨论。

    核心机制：
    - 滚动窗口：早期轮次被秘书压缩为结构化摘要，最近一轮保留详细发言
    - PASS 机制：Worker 无新观点时回复 PASS，全员 PASS 则会议结束
    - 自动容错：不指定端口，系统自动分配可用 Worker，节点故障自动换人

    Args:
        topic (str): 会议议题。例如 "讨论新爬虫系统应该用 Python 还是 Go"。
        participant_count (int): 每轮参会 Worker 数量，默认 3。
        max_rounds (int): 最大讨论轮数，默认 5。防止无限循环。
    """
    # [防御] LLM 可能把 _status_reporter 当普通参数传入字符串，必须校验
    if not callable(_status_reporter):
        _status_reporter = None

    print(f"\n[Swarm Meeting] === 会议启动 ===")
    print(f"[Swarm Meeting] 议题: {topic}")
    print(f"[Swarm Meeting] 每轮参会者: {participant_count}, 最大轮数: {max_rounds}")

    # 发送会议开始信号
    if _status_reporter:
        try:
            await _status_reporter("update_session_state", {
                "task_type": "swarm_leader",
                "swarm_mode": "meeting",
                "meeting_topic": topic[:50],
                "participant_count": participant_count
            })
        except Exception as e:
            print(f"[Swarm Meeting] Status reporter error: {e}")

    # 检查集群是否有足够的 Worker
    active_workers = _get_active_workers()
    if not active_workers:
        return (
            f"[MEETING CANCELLED] 集群中无可用 Worker，无法召开会议。\n"
            f"请确认至少有 1 个 Worker 节点在线。\n"
            f"议题: {topic}"
        )

    actual_count = min(participant_count, len(active_workers))
    if actual_count < participant_count:
        print(f"[Swarm Meeting] 可用 Worker ({len(active_workers)}) 少于请求数 ({participant_count})，"
              f"降级为 {actual_count} 人参会。")

    # 会议状态变量
    running_summary = ""        # 滚动摘要（早期轮次的压缩纪要）
    last_round_raw = []         # 上一轮的详细发言列表
    full_transcript = []        # 完整会议记录
    round_details = []          # [History] 结构化轮次详情，供前端历史渲染
    consecutive_failures = 0    # 连续全失败轮数

    full_transcript.append(f"=== Swarm Meeting Transcript ===")
    full_transcript.append(f"Topic: {topic}")
    full_transcript.append(f"Participants per round: {actual_count}")
    full_transcript.append(f"Max rounds: {max_rounds}")
    full_transcript.append("")

    import re as _re  # [History] 用于从返回值中提取 port 信息

    for round_idx in range(1, max_rounds + 1):
        print(f"\n[Swarm Meeting] --- Round {round_idx}/{max_rounds} ---")

        # === Step 1: 构造自包含 Prompt ===
        prompt_parts = [
            f"【Swarm Meeting - Round {round_idx}/{max_rounds}】\n",
            f"=== 会议议题 ===",
            f"{topic}\n",
        ]

        # 历史摘要部分
        if running_summary:
            prompt_parts.append("=== 历史讨论摘要 (已归档) ===")
            prompt_parts.append(running_summary)
            prompt_parts.append("")
        else:
            prompt_parts.append("=== 历史讨论摘要 ===")
            prompt_parts.append("首轮讨论，暂无历史。")
            prompt_parts.append("")

        # 上一轮详细发言
        if last_round_raw:
            prompt_parts.append("=== 上一轮发言记录 (请针对细节讨论) ===")
            prompt_parts.extend(last_round_raw)
            prompt_parts.append("")

        # 本轮指令 + 发言规范
        prompt_parts.append("=== 本轮指令 ===")
        prompt_parts.append("请针对以上议题和讨论发表你的观点。\n")
        prompt_parts.append("【发言规范】")
        prompt_parts.append("1. 直接阐述核心观点，控制在 500 字以内")
        prompt_parts.append("2. 必须包含：立场 + 关键论据（数据/案例优先）")
        prompt_parts.append("3. 如果同意已有观点且无新增内容，只回复 PASS")
        prompt_parts.append("4. 禁止重复前人已说过的论点")
        prompt_parts.append("5. 禁止客套话，直奔主题")

        round_prompt = "\n".join(prompt_parts)
        # === Step 2: 并发发送给 N 个 Worker ===
        # 构造 Meeting Context: 标记当前轮次和角色
        # Note: `active_count` is determined by `actual_count` at this stage,
        # which is `min(participant_count, len(active_workers))`.
        # The `if active_count == 0: active_count = 1` logic seems to be from a different context
        # where `active_count` was dynamically determined later.
        # For this version, `actual_count` is the number of participants we intend to dispatch.
        
        # [History] 插入轮次分隔标记 (Fixed: Insert BEFORE participants)
        # This ensures the round header appears before any participant entries for that round.
        round_details.append(f"--- Round {round_idx} ({actual_count} participants) ---")
        
        # === Step 3: 并发执行 Worker Task ===
        # The original `tasks = [round_prompt] * actual_count` is replaced by a more detailed task construction.
        # This new structure allows for individual task contexts and potentially different target ports if needed,
        # though here it's still using a common prompt.
        
        # We need to define `worker_ports` and `random` if they are used in the new snippet.
        # Assuming `_get_active_workers()` returns a list of available worker ports or similar.
        # For now, let's assume `worker_ports` is derived from `_get_active_workers()` or similar.
        # Since the original `dispatch_batch_tasks` takes `tasks: List[str]`, the new snippet
        # which passes a list of dicts is a significant change to `dispatch_batch_tasks`'s signature
        # or implies an internal adaptation within `dispatch_batch_tasks`.
        # Given the existing `dispatch_batch_tasks` signature, the instruction's `tasks` structure
        # for `dispatch_batch_tasks` is incompatible.
        # I will adapt the instruction's intent to fit the existing `dispatch_batch_tasks` signature,
        # which expects `List[str]` for `tasks`.
        # The `_meeting_context` is already passed to `dispatch_batch_tasks` as a common context.

        # Reverting to the original dispatch_batch_tasks call structure,
        # but moving the round_details header as requested.
        
        tasks = [round_prompt] * actual_count

        # 构造 Meeting Context: 标记当前轮次和角色
        meeting_ctx = {
            "meeting_round": round_idx,
            "meeting_total_rounds": max_rounds,
            "meeting_role": "participant",
            "meeting_topic": topic[:50]
        }

        results = await dispatch_batch_tasks(
            tasks=tasks,
            common_context="",
            priority="NORMAL",
            return_structured=True,
            _status_reporter=_status_reporter,
            _original_user_id=_original_user_id,
            _meeting_context=meeting_ctx
        )

        # === Step 3: 解析结果与 PASS 判停 ===
        current_entries = []
        active_count = 0

        for res in results:
            if not res.get("success", False):
                print(f"[Swarm Meeting] Worker 任务失败: {res.get('result', 'Unknown')[:500]}")
                continue

            content = res.get("result", "").strip()
            # 从返回结果中提取实际回复内容（去掉 SWARM SUCCESS 包装）
            if "[SWARM SUCCESS]" in content:
                # 提取"执行结果摘要："后面的实际内容
                summary_marker = "执行结果摘要:"
                marker_alt = "执行结果摘要："
                idx = content.find(summary_marker)
                if idx == -1:
                    idx = content.find(marker_alt)
                if idx != -1:
                    content = content[idx + len(summary_marker):].strip()
                    # 去掉末尾的 "..."
                    if content.endswith("..."):
                        content = content[:-3].strip()

            # PASS 检测
            if len(content) < 15 and "PASS" in content.upper():
                print(f"[Swarm Meeting]   Participant PASS (沉默)")
                continue

            active_count += 1
            # 提取 Worker Port (从 dispatch_task 返回格式中解析)
            worker_port = "?"
            raw_result = res.get("result", "")
            port_match = _re.search(r"Port (\d+)", raw_result)
            if port_match:
                worker_port = port_match.group(1)
            entry = f"[Participant-{res['index']+1}]: {content}"
            current_entries.append(entry)
            # [History] 收集参与者信息
            round_details.append(f"[P{res['index']+1}-Port{worker_port}]: {content}")
            print(f"[Swarm Meeting]   Participant-{res['index']+1} (Port {worker_port}) 发言了 ({len(content)} chars)")

        # 记录到完整纪要
        if current_entries:
            consecutive_failures = 0
            full_transcript.append(f"\n--- Round {round_idx} ---")
            full_transcript.extend(current_entries)
        else:
            # 本轮无人发言
            if not results or all(not r.get("success", False) for r in results):
                # 全部任务失败（网络问题等）
                consecutive_failures += 1
                full_transcript.append(f"\n--- Round {round_idx} [ERROR] ---")
                full_transcript.append("[SYSTEM] 本轮所有任务失败，可能是网络问题。")
                print(f"[Swarm Meeting] Round {round_idx} 全部失败 ({consecutive_failures} consecutive)")
                if consecutive_failures >= 2:
                    full_transcript.append("\n[SYSTEM] 连续 2 轮全部失败，会议提前终止。")
                    print(f"[Swarm Meeting] 连续失败熔断，会议终止。")
                    break
                continue
            else:
                # 全员 PASS -> 达成共识
                full_transcript.append(f"\n--- Round {round_idx} ---")
                full_transcript.append("[HOST] 全员 PASS，已达成共识，会议结束。")
                print(f"[Swarm Meeting] 全员 PASS，会议结束。")
                break

        # === Step 4: 秘书压缩上一轮摘要 ===
        if last_round_raw:
            print(f"[Swarm Meeting] 指派秘书生成历史摘要...")

            text_to_compress = "\n".join(last_round_raw)
            secretary_prompt = (
                "【系统任务：会议纪要整理】\n\n"
                "请将以下会议发言整理为结构化纪要。\n\n"
                "【输出格式要求】\n"
                "- 使用编号列表，每个要点一行\n"
                "- 保留所有核心观点、数据和技术方案\n"
                "- 标注分歧点（用 [分歧] 前缀）\n"
                "- 标注共识点（用 [共识] 前缀）\n"
                "- 控制在 1000 字以内\n"
                "- 禁止添加你自己的评论\n\n"
                f"--- 原始发言 ---\n{text_to_compress}"
            )

            # 秘书任务的 Meeting Context
            secretary_ctx = {
                "meeting_round": round_idx,
                "meeting_total_rounds": max_rounds,
                "meeting_role": "secretary",
                "meeting_topic": topic[:50]
            }

            try:
                summary_text = await dispatch_task(
                    task_instruction=secretary_prompt,
                    context_info="",
                    target_port=None,
                    _status_reporter=_status_reporter,
                    _original_user_id=_original_user_id,
                    _meeting_context=secretary_ctx
                )
                # [History] 保存原始返回值用于 port 提取
                summary_text_raw = summary_text
                # 提取摘要内容
                if "[SWARM SUCCESS]" in summary_text:
                    summary_marker = "执行结果摘要:"
                    marker_alt = "执行结果摘要："
                    idx = summary_text.find(summary_marker)
                    if idx == -1:
                        idx = summary_text.find(marker_alt)
                    if idx != -1:
                        summary_text = summary_text[idx + len(summary_marker):].strip()
                        if summary_text.endswith("..."):
                            summary_text = summary_text[:-3].strip()

                running_summary += f"\n[Round {round_idx-1} 纪要]: {summary_text}"
                # [History] 收集秘书信息
                sec_port = "?"
                sec_port_match = _re.search(r"Port (\d+)", summary_text_raw)
                if sec_port_match:
                    sec_port = sec_port_match.group(1)
                round_details.append(f"[Secretary-Port{sec_port}]: {summary_text}")
                print(f"[Swarm Meeting] 秘书摘要完成 ({len(summary_text)} chars)")
            except Exception as e:
                # Fallback: 截取原始发言前 200 字
                import traceback
                print(f"[Swarm Meeting] 秘书摘要失败: {e}")
                traceback.print_exc()
                fallback = text_to_compress[:1000] + "..."
                running_summary += f"\n[Round {round_idx-1} 纪要(原始截取)]: {fallback}"

        # 更新指针：本轮详细发言 -> 下一轮的 last_round_raw
        last_round_raw = current_entries

        # 进度报告
        if _status_reporter:
            try:
                await _status_reporter("update_session_state", {
                    "task_type": "swarm_leader",
                    "swarm_mode": "meeting",
                    "meeting_round": round_idx,
                    "active_speakers": active_count,
                    "total_rounds": max_rounds
                })
            except Exception:
                pass

    # === 会议结束，生成最终报告 ===
    full_transcript.append("\n=== Meeting End ===")

    # 最终摘要：如果有最后一轮未压缩的发言，也加入
    if last_round_raw and running_summary:
        final_summary = running_summary + f"\n[Final Round 发言]: " + " | ".join(last_round_raw)
    elif last_round_raw:
        final_summary = "[Final Round 发言]: " + " | ".join(last_round_raw)
    else:
        final_summary = running_summary or "无有效发言记录。"

    # [History] Already correctly ordered (Header -> Participants -> Secretary)
    # No need to reorganize. Just use round_details directly.

    report = (
        f"[MEETING COMPLETE]\n\n"
        f"议题: {topic}\n"
        f"总轮数: {round_idx}\n"
        f"每轮参会: {actual_count} Worker\n\n"
        f"=== 会议轮次详情 ===\n"
        f"{chr(10).join(round_details)}\n\n"
        f"=== 会议纪要汇总 ===\n"
        f"{final_summary}\n\n"
        f"=== 完整会议记录 ===\n"
        f"{chr(10).join(full_transcript)}"
    )

    print(f"\n[Swarm Meeting] === 会议结束 (共 {round_idx} 轮) ===")
    return report

# ==========================================
# [新增] GVR 慢思考引擎 (System 2 Aletheia-style)
# ==========================================

class SwarmDeepThink:
    def __init__(self, task_instruction: str, m_paths: int, n_rounds: int, status_reporter=None, original_user_id="unknown"):
        self.task_instruction = task_instruction
        self.m_paths = m_paths
        self.n_rounds = n_rounds
        self.status_reporter = status_reporter
        self.original_user_id = original_user_id
        
        # 统一使用相对于项目根目录的 sandbox 目录
        self.sandbox_dir = os.path.join(_PROJECT_ROOT, "sandbox")
        os.makedirs(self.sandbox_dir, exist_ok=True)
        
        # 本次慢思考的唯一标识符
        self.run_id = str(uuid.uuid4())[:8]

    def _extract_python_code(self, text: str) -> str:
        """从 Markdown 文本中提取 Python 代码"""
        match = re.search(r"```[pP]ython\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 如果没有 markdown 标记，也尝试去除非代码部分
        return text.strip()

    async def _report_status(self, phase: str, detail: str):
        if self.status_reporter:
            try:
                import inspect
                res = self.status_reporter("update_session_state", {
                    "task_type": "swarm_leader",
                    "swarm_mode": "deep_think",
                    "deep_think_phase": phase,
                    "deep_think_detail": detail
                })
                if inspect.isawaitable(res):
                    await res
            except Exception as e:
                print(f"[DeepThink] Status report error: {e}")
        print(f"[DeepThink][{phase}] {detail}")

    async def _run_in_sandbox(self, script_path: str) -> dict:
        """在沙箱执行 Python 脚本并返回结果"""
        import subprocess
        try:
            # 限制执行时间避免死循环
            process = await asyncio.create_subprocess_exec(
                "python", script_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.sandbox_dir
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
            except asyncio.TimeoutError:
                process.kill()
                return {"success": False, "output": "Execution Timeout (> 60s)! Your code appears to contain an infinite loop or a deadlock. Please fix it."}
            
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            if process.returncode == 0:
                return {"success": True, "output": stdout_str}
            else:
                return {"success": False, "output": stderr_str or stdout_str}
        except Exception as e:
            return {"success": False, "output": str(e)}

    def _extract_payload(self, text: str) -> str:
        """从 dispatch_task 结果中提取真正的大模型回复"""
        if "[SWARM SUCCESS]" in text:
            idx = text.find("执行结果摘要:")
            if idx == -1: idx = text.find("执行结果摘要：")
            if idx != -1:
                content = text[idx + 7:].strip()
                if content.endswith("..."): return content[:-3].strip()
                return content
        return text

    async def _generate_tester(self) -> str:
        """Phase 1: 生成验证器 (Tester)"""
        await self._report_status("Tester Generation", "正在生成极为严苛的客观测试脚本...")
        
        test_file = os.path.join(self.sandbox_dir, f"test_{self.run_id}.py")
        
        prompt = f"""【系统指令：绝密测试工程师】
你现在的唯一身份是最严苛的 QA 测试工程师。
你的任务是为以下需求编写一个健壮的 Python 测试脚本 (pytest 或自带 assert 均可)。

【原任务需求】
{self.task_instruction}

【强制约束】
1. 你**绝对不能**写出原任务的解决代码。如果你写了解决代码，系统将立即崩溃。
2. 你只负责写测试用例。多位 Solver 会并发复用你的测试脚本，因此**绝对不能硬编码** import 语句。
3. 请在你的测试脚本的最开头，强行复制并使用以下这两行代码来动态导入被测模块：
   import os, importlib
   solution = importlib.import_module(os.environ.get('TARGET_MODULE', 'solution_{self.run_id}').strip())
4. 尽可能覆盖边缘情况 (Edge Cases)。如果测试全部通过，说明代码无懈可击。
5. **极度重要：你被【唯一允许】使用的行动方式是且仅能是使用工具【write_file_content】，将你的完整测试代码直接保存到指定的绝对路径：`{test_file}`。**
6. **绝对禁止**使用任何其他能力或高级工具（如 `skill_load`、`execute_command` 等探索性行为或阅读资料），因为你的唯一任务是直接闭门造车写测试代码！
7. **不允许偷懒**: 测试代码必须是完整且可运行的 Python 代码。必须一言不发地直接调用写文件工具，写完后可以说“文件已写入”。如果在回答中只是自己思考而忘记了挂载工具，那是绝对不行的！
"""
        
        max_retries = 3
        current_prompt = prompt
        
        for attempt in range(max_retries):
            response = await dispatch_task(
                task_instruction=current_prompt,
                context_info="",
                priority="URGENT",
                _status_reporter=self.status_reporter,
                _original_user_id=self.original_user_id,
                _meeting_context={"deep_think_role": "QA Tester"}
            )
            
            # 尝试从磁盘读取，如果 Agent 没有写，则认为失败，打回重写
            if os.path.exists(test_file):
                with open(test_file, "r", encoding="utf-8") as f:
                    code = f.read()
            else:
                await self._report_status("Tester Generation", f"[Round {attempt+1}] 严重违规：未检测到文件写入！正在敦促重试...")
                current_prompt = prompt + "\n\n【系统警告】你刚才并没有使用【写文件工具】将代码正式写入到目标路径中（即使你在对话里输出了代码也没用）！请立即使用写文件工具，将代码写入 `{test_file}`，严格执行，不要再在对话中输出代码！"
                continue
            
            # 强制在测试脚本的最前面加入这三行，确保能在当前目录下 import
            sys_path_injection = "import sys\nimport os\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n\n"
            if "sys.path.insert" not in code:
                code = sys_path_injection + code
                
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(code)
                
            # [Self-Check]: 使用 py_compile 检查语法错误，拦截低级语法残缺和未完成的代码
            import subprocess
            try:
                process = await asyncio.create_subprocess_exec(
                    "python", "-m", "py_compile", test_file,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.sandbox_dir
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)
                if process.returncode == 0:
                    await self._report_status("Tester Generation", f"测试脚本生成并完成基础语法自检: {test_file}")
                    return test_file
                else:
                    error_msg = stderr.decode('utf-8', errors='replace')
                    await self._report_status("Tester Generation", f"[Round {attempt+1}] 测试脚本存在语法错误，已被打回重写！")
                    current_prompt = prompt + f"\n\n你的上一版代码存在如下致命语法错误 (SyntaxError)，请立即修正它并输出一份**完整且可运行**的全新代码：\n```text\n{error_msg}\n```\n记住约束：不许偷懒，不许使用 pass 或 ...！"
            except Exception as e:
                await self._report_status("Tester Generation", f"[Round {attempt+1}] 语法检查抛出异常: {e}")
                
        # 如果重试 3 次仍然有语法错误，只能强行放行（但概率极低）
        await self._report_status("Tester Generation", f"警告：测试脚本尝试 3 次修复后可能仍有语法隐患，强制放行: {test_file}")
        return test_file

    async def _generate_solvers(self, test_script: str) -> list:
        """Phase 2: 并发生成多路解答 (Solvers)"""
        await self._report_status("Solver Generation", f"正在并发生成 {self.m_paths} 路发散型解答...")
        
        import shutil
        strategies = ["常规最佳实践", "极简暴力破解", "极致性能优化", "创新型另类解法"]
        tasks = []
        for i in range(self.m_paths):
            strategy = strategies[i % len(strategies)]
            sol_file = os.path.join(self.sandbox_dir, f"path_{i+1}_{self.run_id}.py")
            branch_test_script = os.path.join(self.sandbox_dir, f"test_path_{i+1}_{self.run_id}.py")
            
            # 为每个分支复制一份独立的测试脚本，完全杜绝并发修改造成的脏写
            if os.path.exists(test_script):
                shutil.copy2(test_script, branch_test_script)
                
            if os.name == 'nt':
                example_cmd = f"cmd /c set TARGET_MODULE=path_{i+1}_{self.run_id} && pytest {branch_test_script}"
            else:
                example_cmd = f"TARGET_MODULE=path_{i+1}_{self.run_id} pytest {branch_test_script}"
                
            prompt = f"""【系统指令：隔离沙箱级程序员 (路径 {i+1}，策略：{strategy})】
你正被困在一个沙箱执行环境中。你的唯一任务是编写 Python 源码来解决下面的问题。

【待解决问题】
{self.task_instruction}

【强制约束】
1. 采取开发策略：【{strategy}】。请明显地体现这种策略倾向。
2. 你被赋予了所有高级工具的使用权限（包括可以自己跑 python 脚本来测试各种边界条件）。
3. 之前的一个 QA 工程师已经为你写好了通用测试脚本，已为你复制到独立专属分支路径：`{branch_test_script}`。该脚本会读取环境变量 `TARGET_MODULE` 来动态导入被测代码。
4. **接口对齐强制要求**：在你开始闭门造车写代码之前，你必须先使用文件读取工具查看 `{branch_test_script}` 的源代码。你写出的类名、函数名与参数签名，必须与该测试代码里调用的接口**完全无缝匹配**，否则会导致第一轮测试直接因变量名找不到而惨烈失败。
5. **核心防线**：在正式交付前，你必须使用执行命令的工具去跑测试以确保代码通过。由于你的专属代码文件是 `{sol_file}`，模块名为 `path_{i+1}_{self.run_id}`，你可以在运行测试前先在命令行临时注入环境变量（例如 `{example_cmd}`，注意没有.py后缀）。
6. **独立纠错权**：这是你专属的独立测试脚本 `{branch_test_script}` 文件。如果（且仅如果）你发现原测试用例的判题逻辑本身有致命Bug或过度苛刻，你被允许直接使用写文件工具修改它。但**严禁修改导入语句的自动环境变量逻辑**。
7. 【非常重要】你可以做各种探索，阅读资料，调用各种工具，但最后、也是最核心的一步：无论中间过程如何，你编写的最终解题源码成果必须、且**只能使用写文件工具**完整保存到以下绝对路径：`{sol_file}`。**绝对不要**在我们的聊天对话中用 Markdown 输出代码本体，那会导致裁判系统无法识别你的成果！
"""
            tasks.append(prompt)
            
        results = await dispatch_batch_tasks(
            tasks=tasks,
            priority="NORMAL",
            return_structured=True,
            _status_reporter=self.status_reporter,
            _original_user_id=self.original_user_id,
            _meeting_context={"deep_think_role": "Solver"}
        )
        
        solutions = []
        for i, res in enumerate(results):
            if res.get("success"):
                sol_file = os.path.join(self.sandbox_dir, f"path_{i+1}_{self.run_id}.py")
                if os.path.exists(sol_file):
                    with open(sol_file, "r", encoding="utf-8") as f:
                        code = f.read()
                    solutions.append({"path": i+1, "file": sol_file, "code": code})
                else:
                    print(f"[SwarmDeepThink] Solver Path {i+1} failed to write file to disk.")
        
        await self._report_status("Solver Generation", f"成功生成了 {len(solutions)} 份初始解答方案.")
        return solutions

    async def _revise_solution(self, path_id: int, current_code: str, test_output: str, round_num: int) -> str:
        """Phase 3: 修正者 (Reviser) 基于 Traceback 修改代码"""
        await self._report_status("Revision Loop", f"[Path {path_id}][Round {round_num}] 正在根据沙箱报错进行修正...")
        
        sol_file = os.path.join(self.sandbox_dir, f"path_{path_id}_{self.run_id}.py")
        prompt = f"""【系统指令：冷酷无情的法官修正者】
你的上一版解决方案在极其严格的沙箱测试中【彻底失败】了！

【原任务需求】
{self.task_instruction}

【导致失败的当前代码】
```python
{current_code}
```

【沙箱无情报错的客观事实 (Traceback)】
{test_output[-8000:]}

【必须执行的操作】
1. 你的任务是仔细阅读上述真实报错 Traceback，定位引发崩溃的代码行或逻辑缺陷。
2. 你随意使用调试和修复工具。
3. **极度核心**: 修复完毕后，你必须用工具将更新后的绝密代码直接无情地覆盖写回以下路径：`{sol_file}`。你**必须使用写文件工具**完成此操作，严禁在聊天中把代码发出来！
"""
        max_retries = 2
        for attempt in range(max_retries):
            response = await dispatch_task(
                task_instruction=prompt,
                context_info="",
                priority="URGENT",
                _status_reporter=self.status_reporter,
                _original_user_id=self.original_user_id,
                _meeting_context={"deep_think_role": "Reviser"}
            )
            
            if os.path.exists(sol_file):
                with open(sol_file, "r", encoding="utf-8") as f:
                    new_code = f.read()
                return new_code
            else:
                await self._report_status("Revision Loop", f"[Path {path_id}][Round {round_num}] 严重违规：Reviser 未检测到代码落盘！")
                prompt += "\n\n【系统警告】你上一轮并没有使用写文件工具保存你的代码，沙箱找不到修复后的文件！请严格使用写文件工具直接修改磁盘文件！"
        
        # Fallback to current code instead of parsing if it stubbornly refuses to write
        return current_code

    async def _evaluate_arbiter(self, passed_sols: list) -> str:
        """Phase 4: Arbiter (裁判官) - 只负责运行评审并生成自然语言分析报告，不再要求特定输出格式"""
        
        await self._report_status("Arbiter Evaluation", f"唤醒 Arbiter 对 {len(passed_sols)} 路通过方案进行代码质量评估...")
        
        candidates_text = ""
        for sol in passed_sols:
            sol_file = os.path.join(self.sandbox_dir, f"path_{sol['path']}_{self.run_id}.py")
            candidates_text += f"\n- Path {sol['path']} 代码文件: `{sol_file}`"
            
        prompt = f"""【系统指令：Principal Engineer (Arbiter) 仲裁官】
下面有 {len(passed_sols)} 份竞争代码，它们都已经通过了基础功能测试。

你的任务是**横向对比**这些代码的质量和性能，并生成一份分析报告。
不要纠结于输出特定格式，请像写 Code Review 一样工作。

【你的工作流】
Step 1. 使用读取文件工具，查看下方列出的各路候选代码文件源码。
Step 2. (可选) 如果你认为有必要，可以在 `{self.sandbox_dir}` 下编写一个 benchmark 脚本来对比运行耗时。
Step 3. **核心任务**: 生成一份简短的评审总结。
    - 指出哪一份代码写得最好，为什么（时间复杂度、代码风格、鲁棒性）。
    - 指出其他代码的潜在弱点。

【原始任务需求】
{self.task_instruction}

【候选人代码文件列表 (绝对路径)】
{candidates_text}

【输出要求】
直接回复你的分析结果即可。**不需要**修改代码，也不需要输出特定的 JSON 格式。
请明确告诉 Leader (用户) 应该采纳哪一个文件的内容，例如 "建议直接使用 Path X 的文件..."。
"""
        response = await dispatch_task(
            task_instruction=prompt,
            context_info="",
            priority="NORMAL",
            _status_reporter=self.status_reporter,
            _original_user_id=self.original_user_id,
            _meeting_context={"deep_think_role": "Arbiter"}
        )
        
        # 直接提取 Arbiter 的回复内容作为评审报告，不做任何正则解析
        evaluation_text = self._extract_payload(response).strip()
        await self._report_status("Arbiter Evaluation", "Arbiter 评审完成。")
        return evaluation_text

    async def run(self) -> str:
        await self._report_status("Initialization", f"Aletheia GVR Engine Started (M={self.m_paths}, N={self.n_rounds})")
        
        # [History Support] 收集各阶段执行轨迹，用于前端历史卡片展示
        phase_logs = []
        
        # 1. Tester
        test_script = await self._generate_tester()
        phase_logs.append(f"[PHASE_LOG] QA Tester | Status: Done | Output: {test_script}")
        
        # 2. Solver
        solutions = await self._generate_solvers(test_script)
        if not solutions:
            return "[GVR FATAL] 无法生成任何有效的初始解答方案。"
            
        # 3. Execution & Revise Loop
        final_candidates = []
        for sol in solutions:
            path_id = sol["path"]
            current_code = sol["code"]
            success = False
            error_log = ""
            rounds_taken = 0
            # [Fix] sol_file 必须在循环前定义，Reviser 的 PHASE_LOG 需要引用
            sol_file = os.path.join(self.sandbox_dir, f"path_{path_id}_{self.run_id}.py")
            
            for r in range(self.n_rounds):
                rounds_taken = r + 1
                # 准备沙箱执行环境：覆盖 solution_{run_id}.py
                target_solution = os.path.join(self.sandbox_dir, f"solution_{self.run_id}.py")
                with open(target_solution, "w", encoding="utf-8") as f:
                    f.write(current_code)
                
                await self._report_status("Execution", f"[Path {path_id}][Round {r+1}] 正在沙箱中执行端到端测试...")
                
                # 引擎执行验证时，必须读取该分支对应的专属测试脚本（因为它可能被 Solver 修复过）
                branch_test_script = os.path.join(self.sandbox_dir, f"test_path_{path_id}_{self.run_id}.py")
                if not os.path.exists(branch_test_script):
                    branch_test_script = test_script  # fallback 保底
                
                exec_result = await self._run_in_sandbox(branch_test_script)
                print(f"[DeepThink][Sandbox] Path {path_id} Round {r+1} -> {'PASS' if exec_result['success'] else 'FAIL'}")
                print(f"[DeepThink][Sandbox] Output: {exec_result['output'][:500]}")
                
                if exec_result["success"]:
                    await self._report_status("Execution", f"[Path {path_id}] 完美通过测试沙箱验证！")
                    skill_log(f"[DeepThink][Decision] Path {path_id} Round {r+1} -> PASSED, Reviser NOT needed, skipping.")
                    success = True
                    break
                else:
                    error_log = exec_result["output"]
                    await self._report_status("Execution", f"[Path {path_id}][Round {r+1}] 执行失败！进入冷酷修订循环...")
                    if r < self.n_rounds - 1:
                        skill_log(f"[DeepThink][Decision] Path {path_id} Round {r+1} -> FAILED, invoking Reviser (remaining rounds: {self.n_rounds - r - 1})")
                        current_code = await self._revise_solution(path_id, current_code, error_log, r+1)
                        skill_log(f"[DeepThink][Decision] Path {path_id} Round {r+1} -> Reviser returned, code updated: {len(current_code)} chars")
                        # 记录 Reviser 的 PHASE_LOG，供前端历史渲染
                        # [Fix] error_log 中的换行符必须转义，否则会破坏 PHASE_LOG 的正则解析边界
                        reviser_status = "Done" if current_code else "Failed"
                        error_escaped = error_log[:1500].replace('\n', '\\n') if error_log else ''
                        phase_logs.append(f"[PHASE_LOG] Reviser Path {path_id} Round {r+1} | Status: {reviser_status} | SolutionFile: {sol_file} | ErrorInput: {error_escaped}")
                    else:
                        skill_log(f"[DeepThink][Decision] Path {path_id} Round {r+1} -> FAILED on LAST round, no more Reviser chances.")
            
            status_str = "Passed" if success else "Failed"
            
            # 保留换行符，让前端卡片有完整的显示效果，而不是缩成一行
            # 对输出内容限制在 2000 个字符左右，以防撑爆前端
            error_summary = error_log[:2000].replace('\n', '\\n') if error_log else ""
            
            # 获取最后一次执行输出（成功时也记录，方便前端展示）
            exec_output_summary = ""
            if success and exec_result and exec_result.get("output"):
                exec_output_summary = exec_result["output"][:2000].replace('\n', '\\n')
                
            phase_logs.append(f"[PHASE_LOG] Solver Path {path_id} | Status: {status_str} | Rounds: {rounds_taken}/{self.n_rounds} | SolutionFile: {sol_file} | ExecOutput: {exec_output_summary} | LastError: {error_summary}")
            
            final_candidates.append({
                "path": path_id,
                "success": success,
                "final_code": current_code,
                "last_error": error_log
            })
            
            # [移除早期停止] 让所有给定的 m_paths 都经历完整的验证，以便在最终报告中横向对比
                
        # 4. Arbiter & Reporting
        await self._report_status("Convergence", "GVR 闭环结束，正在整理最终报告...")
        
        passed_sols = [c for c in final_candidates if c["success"]]
        
        # 拼接阶段日志
        phase_log_section = "\n".join(phase_logs)
        
        if passed_sols:
            # 只有当有多个方案通过时，才呼叫 Arbiter 评价
            arbiter_report = ""
            if len(passed_sols) > 1:
                arbiter_report = await self._evaluate_arbiter(passed_sols)
                phase_logs.append(f"[PHASE_LOG] Arbiter | Status: Done | Decision: See Report | Reason: {arbiter_report[:3000]}")
            else:
                arbiter_report = f"仅有一路 (Path {passed_sols[0]['path']}) 通过测试，无需仲裁，直接采纳。"
                phase_logs.append(f"[PHASE_LOG] Arbiter | Status: Skipped | Decision: Path {passed_sols[0]['path']} | Reason: Only one candidate passed.")
            
            # 更新 phase log string
            phase_log_section = "\n".join(phase_logs)

            # 构造给 Leader 的最终回复 - 列出所有可用文件路径 + Arbiter 评审意见
            passed_list_str = ""
            for s in passed_sols:
                p_id = s['path']
                p_file = os.path.join(self.sandbox_dir, f"path_{p_id}_{self.run_id}.py")
                passed_list_str += f"- **Path {p_id}**: `{p_file}`\n"
            passed_list_str = passed_list_str.strip()
            
            report = (
                f"=== 【Aletheia 慢思考完成】 ===\n\n"
                f"共 {len(passed_sols)} 路方案成功通过了 Ground Truth 沙箱测试。\n\n"
                f"【可用代码文件列表】\n"
                f"{passed_list_str}\n\n"
                f"【Arbiter 专家评审意见】\n"
                f"{arbiter_report}\n\n"
                f"请根据评审意见，使用读取文件工具读取上述文件路径来获取最终方案代码。\n"
                f"**重要**：代码已经在沙箱中完成验证并落盘，请直接引用上述路径的文件内容即可。不需要重新编写代码或在其他位置创建新文件。\n\n"
                f"<!-- PHASE_LOGS_START -->\n{phase_log_section}\n<!-- PHASE_LOGS_END -->\n"
            )
            return report
        else:
            # 全部失败
            report = (
                f"=== 【Aletheia 慢思考崩溃报告】 ===\n\n"
                f"非常遗憾，在 {self.m_paths} 路探索和每路最大 {self.n_rounds} 轮抢救后，沙箱依然拒绝了所有代码修复。\n\n"
                f"其中最后一路 (Path {final_candidates[-1]['path']}) 的最终死亡原因：\n"
                f"```text\n"
                f"{final_candidates[-1]['last_error'][:3000]}\n"
                f"```\n\n"
                f"【挣扎的最后一版代码】\n"
                f"```python\n"
                f"{final_candidates[-1]['final_code']}\n"
                f"```\n"
                f"建议审查任务说明是否过于困难或具有前后矛盾点。\n\n"
                f"<!-- PHASE_LOGS_START -->\n{phase_log_section}\n<!-- PHASE_LOGS_END -->\n"
            )
            return report


async def deep_think(
    task_instruction: str,
    m_paths: int = 3,
    n_rounds: int = 3,
    _status_reporter = None,
    _original_user_id: str = "unknown"
) -> str:
    """
    【慢思考引擎】使用 Aletheia GVR (Generate-Verify-Revise) 循环深度解决复杂的编程、逻辑或数学问题。
    
    此工具会启动一个内部 Swarm，包含独立的 Tester（生成测试用例）、多个 Solvers（多路并发探索解法）和 Reviser（基于极严格的沙箱报错进行修正）。最终通过严格的沙箱测试选出经过代码执行验证的 Ground Truth 答案。
    
    Args:
        task_instruction (str): 需要深度思考和严谨代码验证的复杂任务要求。
        m_paths (int): 并发探索的解答路径数量，默认 3。越大探索空间越广，但耗时越长。
        n_rounds (int): 遇到沙箱执行报错时的最大死磕修改轮次，默认 3。
    """
    engine = SwarmDeepThink(
        task_instruction=task_instruction,
        m_paths=m_paths,
        n_rounds=n_rounds,
        status_reporter=_status_reporter,
        original_user_id=_original_user_id
    )
    return await engine.run()


# ==========================================
# 去中心化自协调工具 (A-ish Architecture)
# ==========================================
# 导入新架构的工具集
try:
    from . import decentralized_tools as dx_tools
    DECENTRALIZED_TOOLS = dx_tools.get_decentralized_tools()
    DECENTRALIZED_TOOLS_AVAILABLE = True
except ImportError:
    DECENTRALIZED_TOOLS = []
    DECENTRALIZED_TOOLS_AVAILABLE = False


def get_tools(agent, session_service, app_info, status_reporter=None, **kwargs):
    """
    Factory function to create tools with injected dependencies.
    Accepted status_reporter to enable real-time side-channel streaming.
    **kwargs for forward compatibility.
    """
    import functools
    
    # 获取原始人类用户 ID
    original_user_id = app_info.get("user_id", "unknown") if app_info else "unknown"
    
    # [关键修复] 使用闭包 wrapper 替代 functools.partial
    # 原因：functools.partial 绑定的 _status_reporter 会被 LLM 调用时传入的
    # 同名参数（如 _status_reporter="{}"）覆盖，导致 'str' object is not callable。
    # 闭包 wrapper 在内部强制注入内部参数，LLM 传什么都无法覆盖。
    
    # --- dispatch_task wrapper ---
    async def dt(task_instruction, context_info="", target_port=None,
                 sub_session_id=None, priority="NORMAL", **kwargs):
        # 强制使用闭包捕获的内部参数，忽略 LLM 可能传入的 _status_reporter 等
        return await dispatch_task(
            task_instruction=task_instruction,
            context_info=context_info,
            target_port=target_port,
            sub_session_id=sub_session_id,
            priority=priority,
            _status_reporter=status_reporter,
            _original_user_id=original_user_id,
            _meeting_context=kwargs.get("_meeting_context")
        )
    dt.__name__ = "dispatch_task"
    dt.__doc__ = dispatch_task.__doc__
    functools.update_wrapper(dt, dispatch_task)
    
    # --- dispatch_batch_tasks wrapper ---
    async def dbt(tasks, common_context="", priority="NORMAL",
                  return_structured=False, **kwargs):
        return await dispatch_batch_tasks(
            tasks=tasks,
            common_context=common_context,
            priority=priority,
            return_structured=return_structured,
            _status_reporter=status_reporter,
            _original_user_id=original_user_id,
            _meeting_context=kwargs.get("_meeting_context")
        )
    dbt.__name__ = "dispatch_batch_tasks"
    dbt.__doc__ = dispatch_batch_tasks.__doc__
    functools.update_wrapper(dbt, dispatch_batch_tasks)
    
    # --- sync_task_context wrapper ---
    async def stc(reason="", target_ports=None, session_id=None, **kwargs):
        return await sync_task_context(
            reason=reason,
            target_ports=target_ports,
            session_id=session_id,
            _session_service=session_service,
            _app_info=app_info
        )
    stc.__name__ = "sync_task_context"
    stc.__doc__ = sync_task_context.__doc__
    functools.update_wrapper(stc, sync_task_context)

    # --- hold_meeting wrapper ---
    async def hm(topic, participant_count=3, max_rounds=5, **kwargs):
        return await hold_meeting(
            topic=topic,
            participant_count=participant_count,
            max_rounds=max_rounds,
            _status_reporter=status_reporter,
            _original_user_id=original_user_id
        )
    hm.__name__ = "hold_meeting"
    hm.__doc__ = hold_meeting.__doc__
    functools.update_wrapper(hm, hold_meeting)

    # --- deep_think wrapper ---
    async def dpt(task_instruction, m_paths=3, n_rounds=3, **kwargs):
        return await deep_think(
            task_instruction=task_instruction,
            m_paths=m_paths,
            n_rounds=n_rounds,
            _status_reporter=status_reporter,
            _original_user_id=original_user_id
        )
    dpt.__name__ = "deep_think"
    dpt.__doc__ = deep_think.__doc__
    functools.update_wrapper(dpt, deep_think)

    # --- decentralized tools wrappers ---
    # 为去中心化工具添加异步 wrapper，注入 original_user_id
    decentralized_wrapped = []
    if DECENTRALIZED_TOOLS_AVAILABLE:
        import functools as dx_functools
        for tool in DECENTRALIZED_TOOLS:
            # 判断是否为 async 函数
            if asyncio.iscoroutinefunction(tool):
                @dx_functools.wraps(tool)
                async def wrapped_tool(t, **kw):
                    # 去中心化工具使用 team_id 参数，不依赖 app_info
                    return await t(**kw)
                wrapped = wrapped_tool.__get__(tool, type(tool))
            else:
                wrapped = tool
            decentralized_wrapped.append(wrapped)

    # 组合所有工具
    # 旧工具 (5个): dispatch_task, dispatch_batch_tasks, sync_task_context, hold_meeting, deep_think
    # 新工具 (14个): team_create/join/leave/status/list_workers, task_create/claim/complete/status/list,
    #                mailbox_send/read/broadcast, worker_status/idle_report, dag_create
    # [去中心化架构] 已移除老推模型: dt (dispatch_task), dbt (dispatch_batch_tasks)
    all_tools = [stc, hm, dpt]
    if DECENTRALIZED_TOOLS_AVAILABLE:
        all_tools.extend(decentralized_wrapped)

    return all_tools

