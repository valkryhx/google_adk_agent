import httpx
import json
import uuid
import os
import random
import sqlite3
import asyncio
import time
from typing import List, Optional

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
                                f"{final_report[:20000]}..."
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
    target_ports = None,         # [改名] 明确表示“我要去问这些端口”
    _session_service = None,
    _app_info = None
) -> str:
    """
    【User-Centric 任务同步】基于用户身份，查询指定节点上的最新任务状态。
    不再需要指定 Leader Port，只要 User ID 一致即可查到。
    
    Args:
        reason (str): 同步原因。
        target_ports (int | List[int]): 你要查询的目标节点端口列表。
    """
    try:
        # 1. 获取当前用户身份 (这是唯一的通行证)
        # 优先使用透传的 original_user_id (Worker模式)，如果没有则用当前的 (Leader/User模式)
        current_user_id = _app_info.get("user_id", "unknown")
        
        # 尝试从 Session State 获取更准确的 original_user_id (如果存在)
        # 这依然有必要，因为 Worker 自身的 user_id 可能被设为了 "Agent_Node_X"
        try:
            current_session = await _session_service.get_session(
                app_name=_app_info.get("app_name", ""),
                user_id=_app_info.get("user_id", ""),
                session_id=_app_info.get("session_id", "")
            )
            if current_session and current_session.state:
                current_user_id = current_session.state.get('original_user_id', current_user_id)
        except:
            pass # 容错，拿不到就用默认的

        # 2. 确定目标端口
        targets = []
        if target_ports:
            # ✅ 新增：更稳健的类型兼容，因为 LLM 有时会把 list 传成 string "[8000]"
            if isinstance(target_ports, str):
                try:
                    import json
                    parsed = json.loads(target_ports)
                    if isinstance(parsed, list): targets = parsed
                    elif isinstance(parsed, int): targets = [parsed]
                    else: targets = [int(p.strip()) for p in target_ports.split(',')]
                except:
                    # 最后的尝试：当做单个数字
                    try: targets = [int(target_ports)]
                    except: pass
            elif isinstance(target_ports, list): targets = target_ports
            elif isinstance(target_ports, int): targets = [target_ports]
        else:
            return "❌ 请指定 target_ports (你要查询的节点端口)。"

        print(f"[Swarm Sync] 🆔 身份: {current_user_id}, 🎯 目标: {targets}")

        # 3. 单节点查询逻辑
        async def _sync_single_node(port):
            try:
                target_url = f"http://localhost:{port}"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # === [核心逻辑] 直接使用通配符 "*" ===
                    # 含义：我是 User A，把我在你这儿不管什么名义下的最新任务给我
                    response = await client.get(
                        f"{target_url}/api/context/leader_summary",
                        params={
                            "app_name": "*",  # <--- 通配符魔法
                            "user_id": current_user_id,
                            "limit": 1
                        }
                    )
                    
                    if response.status_code != 200:
                        return {"port": port, "error": f"HTTP {response.status_code}"}
                    
                    data = response.json()
                    if "error" in data: return {"port": port, "error": data['error']}
                    return {"port": port, "success": True, "data": data}

            except Exception as e:
                return {"port": port, "error": str(e)}

        # 4. 并发执行
        results = await asyncio.gather(*[_sync_single_node(p) for p in targets])
        
        # 5. 格式化输出
        summary_parts = [
            "【Swarm 任务上下文同步报告】",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"👤 用户身份: {current_user_id}",
            f"🎯 目标节点: {targets}",
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
                summary_parts.append(f"✅ 节点 (Port {port}): {data.get('title', 'Untitled')}")
                # 摘要截取前 300 字符
                summary_text = data.get('recent_summary', '无')
                summary_parts.append(f"   摘要: {summary_text[:]}..." if len(summary_text) > 300 else f"   摘要: {summary_text}")
                summary_parts.append("")
        
        summary_parts.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        summary_parts.append(f"同步成功率: {success_count}/{len(targets)}")
        
        return "\n".join(summary_parts)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 系统异常: {e}"


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
    
    # [新增] sync_task_context 工具
    stc = functools.partial(
        sync_task_context,
        _session_service=session_service,
        _app_info=app_info
    )
    stc.__name__ = "sync_task_context"
    stc.__doc__ = sync_task_context.__doc__
    functools.update_wrapper(stc, sync_task_context)

    return [dt, dbt, stc]  # 返回3个工具
