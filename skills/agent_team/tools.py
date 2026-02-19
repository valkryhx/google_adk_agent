import httpx
import json
import uuid
import os
import random
import sqlite3
import asyncio
import time
from typing import List, Optional, Union

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
    print(f"[DEBUG] dispatch_task called. reporter type: {type(_status_reporter)}")
    print(f"[DEBUG] dispatch_task called with reporters={_status_reporter}")
    # [New] 非侵入式打标：通过 status_reporter 发送信号
    if _status_reporter:
        try:
            # 发送特定的元数据更新信号
            await _status_reporter("update_session_state", {
                "task_type": "swarm_leader",
                "swarm_mode": "single_dispatch"
            })
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
        
        # [Report] 尝试连接
        # report('try_connect', {"worker_port": worker_port})

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
                                report('fail', {"worker_port": worker_port, "error": msg})
                                return msg
                            else:
                                # 如果是随机分配，那就找下一个人
                                print(f"[Swarm] Worker {worker_port} 正忙，尝试下一个...")
                                break # 跳出重试，尝试下一个 candidate

                        # === 场景 B: 连接成功 (200) ===
                        if response.status_code == 200:
                            # [Report] 任务开始 (Init)
                            report('init', {
                                "worker_port": worker_port, 
                                "session_id": use_session_id,
                                "task_preview": task_instruction[:50] + "..."
                            })

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
                                    
                                    # [Report] 实时流 (Chunk) - 所有有内容的 chunk 都汇报
                                    if content and chunk_type in ("text", "tool_result"):
                                        report('chunk', {
                                            "worker_port": worker_port,
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
                            report('finish', {"worker_port": worker_port, "status": "success"})
                            
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
                    worker_failed_completely = True
                    last_error = "Timeout"
                    # 多次超时也不移除，依靠心跳机制被动清理，防止误杀
            
            except Exception as e:
                print(f"[Swarm] 未知错误: {e}")
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
    
    # [New] 非侵入式打标：通过 status_reporter 发送信号
    if _status_reporter:
        try:
            await _status_reporter("update_session_state", {
                "task_type": "swarm_leader",
                "swarm_mode": "batch_dispatch",
                "active_workers": len(tasks)
            })
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


def get_tools(agent, session_service, app_info, status_reporter=None, **kwargs):
    """
    Factory function to create tools with injected dependencies.
    Accepted status_reporter to enable real-time side-channel streaming.
    **kwargs for forward compatibility.
    """
    import functools
    
    # 获取原始人类用户 ID
    original_user_id = app_info.get("user_id", "unknown") if app_info else "unknown"
    
    # 使用 partial 注入 status_reporter 和 original_user_id，同时保持其他参数的灵活性
    # 注意：agent 调用时只会传它认识的参数（task_instruction等），
    # _status_reporter 和 _original_user_id 必须作为 keyword argument 预先绑定。
    
    dt = functools.partial(
        dispatch_task, 
        _status_reporter=status_reporter,
        _original_user_id=original_user_id
    )
    dbt = functools.partial(
        dispatch_batch_tasks, 
        _status_reporter=status_reporter,
        _original_user_id=original_user_id
    )
    
    # 恢复原函数的元数据，以便 Agent 能够正确识别工具说明
    dt.__name__ = "dispatch_task"
    dt.__doc__ = dispatch_task.__doc__
    functools.update_wrapper(dt, dispatch_task)
    
    dbt.__name__ = "dispatch_batch_tasks"
    dbt.__doc__ = dispatch_batch_tasks.__doc__
    functools.update_wrapper(dbt, dispatch_batch_tasks)
    
    # sync_task_context 工具
    stc = functools.partial(
        sync_task_context,
        _session_service=session_service,
        _app_info=app_info
    )
    stc.__name__ = "sync_task_context"
    stc.__doc__ = sync_task_context.__doc__
    functools.update_wrapper(stc, sync_task_context)

    # [新增] hold_meeting 工具
    hm = functools.partial(
        hold_meeting,
        _status_reporter=status_reporter,
        _original_user_id=original_user_id
    )
    hm.__name__ = "hold_meeting"
    hm.__doc__ = hold_meeting.__doc__
    functools.update_wrapper(hm, hold_meeting)

    return [dt, dbt, stc, hm]  # 返回 4 个工具

