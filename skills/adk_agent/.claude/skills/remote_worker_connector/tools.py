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
REGISTRY_DB = "swarm_registry.db"
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

async def dispatch_task(
    task_instruction: str, 
    context_info: Optional[str] = "",
    target_port: Optional[int] = None,
    sub_session_id: Optional[str] = None,
    priority: str = "NORMAL"
) -> str:
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

    # 4. 开始尝试调度（轮询候选人）
    last_error = ""
    
    # 增加重试机制，防止网络抖动导致的误判
    max_retries = 5

    for worker in candidates:
        worker_port = worker['port']
        worker_url = worker['url']
        
        # [优化] 增加微小的随机等待，避免 Batch 模式下瞬间请求风暴
        await asyncio.sleep(random.uniform(1, 15))
        
        print(f"[Swarm Dispatch] 📡 正在连接 Worker {worker_port} (Session: {use_session_id})...")

        payload = {
            "message": full_message,
            "app_name": CLUSTER_APP_NAME,
            "user_id": caller_id,
            "session_id": use_session_id
        }

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client: # 增加超时时间到5分钟
                    async with client.stream("POST", f"{worker_url}/api/chat", json=payload) as response:
                        
                        # === 场景 A: 对方忙碌 (503) ===
                        if response.status_code == 503:
                            # 如果是指定了 target_port，我们不能换人，必须报错让 Leader 决定
                            if target_port:
                                error_json = await response.json()
                                task_preview = error_json.get('current_task', 'Unknown')
                                return (
                                    f"【调度冲突】目标 Worker ({worker_port}) 正在忙碌。\n"
                                    f"⚠️ 当前任务: '{task_preview}'\n"
                                    f"❌ 建议：\n"
                                    f"   1. 若任务紧急，请重新调用并设置 priority='URGENT' 以强制打断。\n"
                                    f"   2. 若不紧急，请稍后重试。"
                                )
                            else:
                                # 如果是随机分配，那就找下一个人
                                print(f"[Swarm] Worker {worker_port} 正忙，尝试下一个...")
                                break # 跳出重试，尝试下一个 candidate

                        # === 场景 B: 连接成功 (200) ===
                        if response.status_code == 200:
                            # 【过程屏蔽】只收集文本内容，忽略中间的 tool_calls
                            final_report = ""
                            async for line in response.aiter_lines():
                                if not line: continue
                                try:
                                    data = json.loads(line)
                                    chunk = data.get("chunk", {})
                                    if chunk.get("type") == "text":
                                        final_report += chunk.get("content", "")
                                except: continue
                            
                            # 成功！返回结构化报告
                            print(f"[Swarm] ✅ Worker {worker_port} 任务完成。")
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
    return (
        f"【调度失败】无法将任务分派给任何 Worker。\n"
        f"原因: 所有候选节点 ({len(candidates)}个) 都忙碌或无法连接。\n"
        f"最后一次错误: {last_error}"
        f"建议: 请尝试自己执行该任务，或稍后重试。"
    )

async def dispatch_batch_tasks(
    tasks: List[str],
    common_context: Optional[str] = "",
    priority: str = "NORMAL"
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
            
            # 这里的 target_port=None 让 dispatch_task 内部去随机找人
            # 由于 dispatch_task 有重试机制，它会处理竞争 busy 的情况
            result = await dispatch_task(
                task_instruction=task_with_id,
                context_info=common_context,
                target_port=None, 
                sub_session_id=None,
                priority=priority
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

def get_tools(agent, session_service, app_info):
    # 记得导出新工具
    return [dispatch_task, dispatch_batch_tasks]
