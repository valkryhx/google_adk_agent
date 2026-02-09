import httpx
import json
import uuid
import os
import random
import sqlite3
import asyncio
from typing import List, Optional

# ==========================================
# 配置与常量
# ==========================================
# ==========================================
# 配置与常量
# ==========================================
REGISTRY_DB = "sqlite_db/swarm_registry.db"
CLUSTER_APP_NAME = "adk_universal_swarm"

# 【关键】从环境变量获取当前节点端口，实现自我认知
# 如果未设置（如本地测试），默认为 0
CURRENT_NODE_PORT = int(os.environ.get("ADK_CURRENT_PORT", 0))

# ==========================================
# 辅助函数：服务发现与健康管理
# ==========================================

def _get_active_workers() -> List[dict]:
    """
    从 SQLite 注册表中获取活跃的 Worker 节点。
    会自动排除当前节点自己（避免自己给自己派活导致死循环）。
    """
    if not os.path.exists(REGISTRY_DB):
        return []
    
    try:
        # 使用 timeout 防止数据库锁竞争
        with sqlite3.connect(REGISTRY_DB, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT port, url FROM nodes WHERE status='active'")
            rows = cursor.fetchall()
            
            workers = []
            for row in rows:
                # 【自我排除逻辑】
                if CURRENT_NODE_PORT and int(row['port']) == CURRENT_NODE_PORT:
                    continue 
                workers.append({"port": row['port'], "url": row['url']})
            return workers
    except Exception as e:
        print(f"[Swarm Discovery Error] {e}")
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
    _original_user_id: str = "unknown"  # 新增：传递原始人类用户 ID
) -> str:
    print(f"[DEBUG] dispatch_task called. reporter type: {type(_status_reporter)}")
    print(f"[DEBUG] dispatch_task called with reporters={_status_reporter}")
    """
    【集群指挥官核心工具】将任务分发给 Swarm 集群中的其他智能体。
    
    本工具支持自动负载均衡、状态保持（多轮对话）以及紧急抢占。
    Leader 应当只关注“派活”和“收结果”，具体的执行过程由 Worker 在其独立进程中完成。

    Args:
        task_instruction (str): 给 Worker 的具体任务指令。请清晰、明确。
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
        return (
            f"【系统警告】集群中没有发现其他活跃节点（当前节点 Port {CURRENT_NODE_PORT} 是唯一的幸存者）。\n"
            f"请不要再尝试分派任务。\n"
            f"👉 立即使用你自己的本地工具（如 bash, file_editor,skill_load）亲自执行此任务,记住 你也是可动态能力加持的强大智能体。"
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
    
    full_message = f"【背景】\n{context_info}\n\n【任务】\n{task_instruction}{system_instruction_injection}"
    
    # 处理紧急抢占标记
    if priority.upper() == "URGENT":
        full_message = "[URGENT_INTERRUPT] " + full_message
        print(f"[Swarm] 发送紧急打断指令 -> Target Candidates: {[c['port'] for c in candidates]}")
    
    caller_id = f"Agent_Node_{CURRENT_NODE_PORT}"
    use_session_id = sub_session_id or f"sub_{uuid.uuid4().hex[:8]}"

    # Reporting Helper
    def report(event_type, data):
        if _status_reporter:
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

        for attempt in range(max_retries + 1):
            try:
                # [Optimized] Use separate timeouts for connect and read
                # Connect: 3s (fast fail if node down)
                # Read: 30s (shorter timeout to trigger retry earlier as requested)
                timeout_config = httpx.Timeout(180.0, connect=3.0)
                
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

                            # 【过程屏蔽】只收集文本内容，忽略中间的 tool_calls
                            final_report = ""
                            async for line in response.aiter_lines():
                                if not line: continue
                                try:
                                    data = json.loads(line)
                                    chunk = data.get("chunk", {})
                                    if chunk.get("type") == "text":
                                        content = chunk.get("content", "")
                                        final_report += content
                                        
                                        # [Report] 实时流 (Chunk)
                                        # 只有当有内容时才汇报
                                        if content:
                                            report('chunk', {
                                                "worker_port": worker_port,
                                                "content": content
                                            })
                                except: continue
                            
                            # 成功！返回结构化报告
                            print(f"[Swarm] ✅ Worker {worker_port} 任务完成。")
                            
                            # [新增] 任务血缘记录：向 Worker 注入元数据
                            try:
                                import time
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
                                print(f"[Swarm] 📝 已注入任务血缘元数据到 Worker {worker_port}")
                            except Exception as e:
                                print(f"[Swarm] ⚠️ 元数据注入失败: {e}")
                            
                            # [Report] 任务完成 (Finish)
                            report('finish', {"worker_port": worker_port, "status": "success"})
                            
                            return (
                                f"✅ [SWARM SUCCESS]\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🤖 执行节点: Worker Agent (Port {worker_port})\n"
                                f"🆔 会话 ID : {use_session_id}\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"📄 执行结果摘要:\n"
                                f"{final_report[:20000]}..."
                                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            )
                        
                        # === 场景 C: 其他错误 ===
                        last_error = f"HTTP {response.status_code}"
            
            except (httpx.ConnectError, httpx.TimeoutException, ConnectionRefusedError) as e:
                print(f"[Swarm] ⚠️ 连接 Worker {worker_port} 失败 (Attempt {attempt+1}/{max_retries+1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(1) # 重试前等待
                    continue
                else:
                    # 只有在多次重试失败后，才考虑是否标记为离线（暂时注释掉自动移除，避免误杀）
                    # _remove_dead_node(worker_port) 
                    last_error = str(e)
            except Exception as e:
                print(f"[Swarm] 未知错误: {e}")
                last_error = str(e)
                break 

    # 5. 所有候选人都试过了，还是失败
    msg = f"【调度失败】无法将任务分派给任何 Worker。Last Error: {last_error}"
    report('fail', {"worker_port": 0, "error": msg}) # Port 0 means system/scheduler fail
    return msg

# ==========================================
# [新增] 跨节点上下文同步工具
# ==========================================
async def sync_leader_context(
    reason: str = "",
    leader_port = None,  # 新增：可以是 int（单个）或 list[int]（多个）
    _session_service = None,
    _app_info = None
) -> str:
    """
    【Swarm 上下文同步工具】从一个或多个节点获取任务背景信息
    
    Args:
        reason: 同步原因说明（推荐填写，便于日志追踪）
        leader_port: (可选) Leader 端口号
            - int: 单个端口，如 8000
            - list[int]: 多个端口，如 [8000, 8001]
            - None: 自动检测
        
    使用场景：
    1. Worker 节点需要获取 Leader 分派的原始任务背景
    2. 汇总多个节点的上下文（如多个并行任务的结果）
    3. 跨节点上下文共享
    
    示例：
        # 自动检测 Leader
        sync_leader_context(reason="需要汇总三家公司的数据")
        
        # 同步单个 Leader
        sync_leader_context(reason="同步8000的任务", leader_port=8000)
        
        # 同步多个节点
        sync_leader_context(
            reason="汇总8000(Leader)和8001(Worker)的状态",
            leader_port=[8000, 8001]
        )
    """
    try:
        # 1. 获取当前 session
        current_session = await _session_service.get_session(
            app_name=_app_info.get("app_name", ""),
            user_id=_app_info.get("user_id", ""),
            session_id=_app_info.get("session_id", "")
        )
        
        
        # 2. 确定要同步的端口列表
        original_user_id = _app_info.get("user_id", "unknown")
        current_app_name = _app_info.get("app_name", "")
        ports_to_sync = []
        
        # 处理 leader_port 参数（可以是 int、list 或 None）
        if leader_port:
            if isinstance(leader_port, list):
                ports_to_sync = leader_port
                print(f"[Swarm Sync] ✓ 使用手动指定的多个端口: {ports_to_sync}")
            elif isinstance(leader_port, int):
                ports_to_sync = [leader_port]
                print(f"[Swarm Sync] ✓ 使用手动指定的端口: {leader_port}")
            else:
                return f"❌ leader_port 参数类型错误: {type(leader_port)}，应该是 int 或 list[int]"
            
            # 尝试从会话 state 获取 original_user_id
            if current_session.state and 'original_user_id' in current_session.state:
                original_user_id = current_session.state['original_user_id']
        
        # 自动检测单个端口（按优先级）
        elif not ports_to_sync:
            detected_port = None
            
            # 优先级1：当前会话的 state 中有 leader_port
            if current_session.state and 'leader_port' in current_session.state:
                detected_port = current_session.state['leader_port']
                original_user_id = current_session.state.get('original_user_id', original_user_id)
                print(f"[Swarm Sync] ✓ 从会话 state 获取 Leader={detected_port}")
            
            # 优先级2：从当前 app_name 直接解析
            elif current_app_name and current_app_name.startswith("swarm_from_"):
                try:
                    detected_port = int(current_app_name.split("_")[-1])
                    print(f"[Swarm Sync] ✓ 从 app_name '{current_app_name}' 解析出 Leader={detected_port}")
                    
                    if current_session.state and 'original_user_id' in current_session.state:
                        original_user_id = current_session.state['original_user_id']
                except (ValueError, IndexError) as e:
                    print(f"[Swarm Sync] ⚠️ 无法从 app_name '{current_app_name}' 解析端口: {e}")
            
            # 优先级3：查找本节点上最近的 Swarm 会话
            if not detected_port:
                print(f"[Swarm Sync] ℹ️ 当前会话不是 Worker 任务，尝试查找最近的 Swarm 任务...")
                
                current_port = CURRENT_NODE_PORT
                possible_leader_ports = [8000, 8001, 8002, 8003, 8004]
                found_swarm_sessions = []
                
                for potential_leader in possible_leader_ports:
                    if potential_leader == current_port:
                        continue
                    
                    try:
                        app_name_to_check = f"swarm_from_{potential_leader}"
                        all_sessions = await _session_service.list_sessions(
                            app_name=app_name_to_check,
                            user_id=original_user_id
                        )
                        
                        if all_sessions and len(all_sessions) > 0:
                            for session in all_sessions:
                                if session.state and 'leader_port' in session.state:
                                    found_swarm_sessions.append({
                                        'session': session,
                                        'leader_port': session.state['leader_port'],
                                        'app_name': app_name_to_check,
                                        'created_at': session.created_at if hasattr(session, 'created_at') else 0
                                    })
                    except Exception as e:
                        continue
                
                if found_swarm_sessions:
                    found_swarm_sessions.sort(key=lambda x: x['created_at'], reverse=True)
                    latest_swarm = found_swarm_sessions[0]
                    
                    detected_port = latest_swarm['leader_port']
                    session = latest_swarm['session']
                    original_user_id = session.state.get('original_user_id', original_user_id)
                    
                    print(f"[Swarm Sync] ✓ 找到最新的 Swarm 会话（app_name={latest_swarm['app_name']}），Leader={detected_port}")
                    
                    if len(found_swarm_sessions) > 1:
                        other_leaders = [str(s['leader_port']) for s in found_swarm_sessions[1:3]]
                        print(f"[Swarm Sync] ⚠️ 检测到多个 Swarm 会话，已选择最新的。其他 Leader: {', '.join(other_leaders)}")
                        print(f"[Swarm Sync] 💡 建议：使用 leader_port=[8000, 8001] 同步多个节点")
            
            if detected_port:
                ports_to_sync = [detected_port]
            else:
                return """ℹ️ 未找到 Leader 节点信息

提示：
1. 当前会话不是从 Leader 分派的 Worker 任务
2. 本节点上也没有找到最近的 Swarm 任务会话
3. 建议手动指定端口: sync_leader_context(reason="...", leader_port=8000)
"""
        
        print(f"[Swarm Sync] 🔄 开始同步 {len(ports_to_sync)} 个节点的上下文, 原因: {reason}")
        
        # 3. 并发同步多个节点
        async def _sync_single_port(port):
            """同步单个端口的辅助函数"""
            try:
                leader_url = f"http://localhost:{port}"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{leader_url}/api/context/leader_summary",
                        params={
                            "app_name": "dynamic_expert",
                            "user_id": original_user_id,
                            "limit": 1
                        }
                    )
                    
                    if response.status_code != 200:
                        return {"port": port, "error": f"HTTP {response.status_code}"}
                    
                    data = response.json()
                    
                    if "error" in data:
                        return {"port": port, "error": data['error']}
                    
                    if isinstance(data, list):
                        return {"port": port, "error": "API 返回格式错误（list 而非 dict），请重启服务"}
                    
                    if not isinstance(data, dict):
                        return {"port": port, "error": f"数据类型错误: {type(data)}"}
                    
                    return {"port": port, "success": True, "data": data}
            except Exception as e:
                return {"port": port, "error": str(e)}
        
        # 并发执行所有同步
        results = await asyncio.gather(*[_sync_single_port(port) for port in ports_to_sync])
        
        # 4. 格式化结果
        if len(ports_to_sync) == 1:
            # 单端口模式：简洁输出
            res = results[0]
            if "error" in res:
                return f"❌ 连接节点 {res['port']} 失败: {res['error']}"
            
            data = res["data"]
            result = f"""
【Leader 上下文同步成功】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🖥️  Leader 节点: http://localhost:{res['port']}
👤 用户: {original_user_id}
📋 任务标题: {data.get('title', 'Unknown')}

最近对话摘要:
{data.get('recent_summary', '(无摘要)')}

📊 总消息数: {data.get('total_messages', 0)}

已同步完整上下文,你现在可以继续执行指令。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            print(f"[Swarm Sync] ✅ 同步成功,获得 {data.get('total_messages', 0)} 条消息")
            return result.strip()
        else:
            # 多端口模式：汇总输出
            summary_parts = [
                "【多节点上下文同步完成】",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"👤 用户: {original_user_id}",
                f"📡 同步节点数: {len(ports_to_sync)}",
                ""
            ]
            
            success_count = 0
            for res in results:
                port = res['port']
                if "error" in res:
                    summary_parts.append(f"❌ 节点 {port}: {res['error']}")
                else:
                    success_count += 1
                    data = res['data']
                    summary_parts.append(f"✅ 节点 {port}: {data.get('title', 'Untitled')} ({data.get('total_messages', 0)} 条消息)")
                    summary_parts.append(f"   摘要: {data.get('recent_summary', '无')[:100]}...")
                    summary_parts.append("")
            
            summary_parts.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            summary_parts.append(f"成功同步: {success_count}/{len(ports_to_sync)} 个节点")
            
            print(f"[Swarm Sync] ✅ 多节点同步完成: {success_count}/{len(ports_to_sync)}")
            return "\n".join(summary_parts)
    
    except Exception as e:
        print(f"[Swarm Sync] ❌ 同步失败: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ 同步失败: {e}"


async def dispatch_batch_tasks(
    tasks: List[str],
    common_context: Optional[str] = "",
    priority: str = "NORMAL",
    _status_reporter = None,  # [Internal] Injected by get_tools
    _original_user_id: str = "unknown"  # 新增：传递原始人类用户 ID
) -> str:
    """
    【并发加速】同时向集群分发多个并行任务。
    
    使用此工具可以一次性启动多个 Worker 并行工作，极大缩短总耗时。
    适用于：多维度搜索、多文件生成、批量数据处理等互不依赖的任务。
    
    Args:
        tasks (List[str]): 任务指令列表。例如 ["搜索苹果公司财报", "搜索微软公司财报"]。
        common_context (str): 所有任务共享的背景信息。
        priority (str): 优先级 (NORMAL/URGENT)。
    """
    
    if not tasks:
        return "【系统提示】任务列表为空，未执行任何操作。"

    print(f"\n[Swarm Batch] 🚀 正在启动 {len(tasks)} 个并发任务...")
    
    # [优化] 使用 Semaphore 限制最大并发数，防止瞬间请求过多导致本地端口耗尽或数据库锁死
    sem = asyncio.Semaphore(5) 

    async def _run_single_task(index, instruction):
        # 简单的轮询负载均衡：根据 index 偏移选择不同节点（虽然 dispatch_task 内部有随机，这里增加一些确定性分布）
        # 这里直接调用 dispatch_task 即可，它内部会自动找空闲节点
        
        # 给每个任务加个前缀标识
        task_with_id = f"[Batch-Task-{index+1}] {instruction}"
    
        print(f"  -> 启动子任务 {index+1}: {instruction[:20]}...")
        
        # [Call] 务必传递 _status_reporter
        result = await dispatch_task(
            task_instruction=task_with_id,
            context_info=common_context,
            target_port=None, 
            sub_session_id=None,
            priority=priority,
            _status_reporter=_status_reporter,
            _original_user_id=_original_user_id  # 传递原始用户 ID
        )
        return f"--- 任务 {index+1} 结果 ---\n{result}\n"

    # 核心：asyncio.gather 并发执行
    # 这会导致所有 HTTP 请求几乎同时发出
    results = await asyncio.gather(*[
        _run_single_task(i, task) for i, task in enumerate(tasks)
    ])
    
    # 汇总结果
    final_report = f"【批量任务执行报告】\n共执行 {len(tasks)} 个并发任务。\n" + "\n".join(results)
    
    print(f"[Swarm Batch] ✅ {len(tasks)} 个任务全部完成。")
    return final_report

def get_tools(agent, session_service, app_info, status_reporter=None):
    """
    Factory function to create tools with injected dependencies.
    Accepted status_reporter to enable real-time side-channel streaming.
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
    # 如果 inspect.signature 是基于原函数的，partial 对象通常能保留签名信息，
    # 但为了保险，有些框架可能需要 update_wrapper
    functools.update_wrapper(dt, dispatch_task)
    
    dbt.__name__ = "dispatch_batch_tasks"
    dbt.__doc__ = dispatch_batch_tasks.__doc__
    functools.update_wrapper(dbt, dispatch_batch_tasks)
    
    # [新增] sync_leader_context 工具
    slc = functools.partial(
        sync_leader_context,
        _session_service=session_service,
        _app_info=app_info
    )
    slc.__name__ = "sync_leader_context"
    slc.__doc__ = sync_leader_context.__doc__
    functools.update_wrapper(slc, sync_leader_context)

    return [dt, dbt, slc]  # 返回3个工具
