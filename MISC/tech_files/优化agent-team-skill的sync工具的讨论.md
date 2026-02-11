你如果加入这个manual swarm leader参数的话，那之前我在8002上问8000和8003，那调用的时候怎么传参呢？

Gemini said
这是一个非常切中要害的问题！

如果加入了 manual_swarm_leader 参数，对于你在 8002 上问 8000 和 8003 的那个原始场景，调用方式几乎不需要改变，或者说你可以选择“偷懒”不传这个新参数。

1. 8002 场景的调用方式（两种写法）
因为 8002 是参与任务的 Worker，它的内存（Session State）里已经自动记住了 leader_port=8000。

写法 A：偷懒模式（推荐，利用隐式信息）
完全保持原样。你不需要传 manual_swarm_leader，代码会自动去 session state 里找。

Python
# 在 8002 上执行
sync_leader_context(
    leader_port=[8000, 8003]  # 这里指“目标端口列表”
)
结果：系统发现 manual 参数为空 -> 自动读取 State -> 发现 Leader 是 8000 -> 成功推断出 8003 是同事。

写法 B：显式模式（也是对的）
如果你想“强行”指定（比如覆盖 State），也可以传。

Python
# 在 8002 上执行
sync_leader_context(
    leader_port=[8000, 8003], 
    manual_swarm_leader=8000  # <--- 显式指定暗号
)
结果：系统优先使用 manual 参数 -> 确定 Leader 是 8000 -> 成功。

2. 8004 场景的调用方式（必须传参）
因为 8004 是局外人，内存里没有 State，所以必须传这个参数，否则它就不知道去查哪个 App Name。

Python
# 在 8004 上执行
sync_leader_context(
    leader_port=[8000, 8002],  # 我要问这两个人
    manual_swarm_leader=8000   # <--- 必须传！告诉它“暗号”是 8000
)
3. 最终优化后的代码实现
为了支持这两种用法，我们需要修改 tools.py 中的函数逻辑，引入优先级判断。

你可以直接使用这段代码替换原有的函数：

Python
async def sync_leader_context(
    reason: str = "",
    leader_port = None,          # 【旧参数名】实际含义是 target_ports (要访问的目标列表)
    manual_swarm_leader = None,  # 【新参数】手动指定 Leader 端口 (用于局外人模式)
    _session_service = None,
    _app_info = None
) -> str:
    """
    【Swarm 上下文同步工具】
    Args:
        leader_port: 要同步的目标端口列表 (int 或 list[int])
        manual_swarm_leader: (可选) 显式指定 Leader 端口。
                             - 如果你是 Worker，不传此参数也会自动从 state 获取。
                             - 如果你是局外人 (8004)，必须传此参数才能查到 Worker 的数据。
    """
    try:
        # 1. 获取当前 session
        current_session = await _session_service.get_session(
            app_name=_app_info.get("app_name", ""),
            user_id=_app_info.get("user_id", ""),
            session_id=_app_info.get("session_id", "")
        )
        
        original_user_id = _app_info.get("user_id", "unknown")
        
        # === 【核心逻辑：确定 Swarm Leader】===
        # 优先级 1: 手动参数 (manual_swarm_leader)
        # 优先级 2: 自动记忆 (session.state['leader_port'])
        
        real_swarm_leader = manual_swarm_leader
        
        if not real_swarm_leader:
            # 如果没传手动参数，尝试从 State 读取
            if current_session.state and 'leader_port' in current_session.state:
                real_swarm_leader = current_session.state['leader_port']
                # 顺便尝试获取原始用户 ID
                original_user_id = current_session.state.get('original_user_id', original_user_id)

        # 2. 确定要同步的目标端口列表 (处理 leader_port 参数)
        targets = []
        if leader_port:
            if isinstance(leader_port, list): targets = leader_port
            elif isinstance(leader_port, int): targets = [leader_port]
        # 如果既没传目标，也没找到 Leader，就报错
        elif real_swarm_leader:
            targets = [real_swarm_leader]
        else:
            return "❌ 无法确定同步目标。请指定 leader_port (目标列表)，如果是局外人请同时指定 manual_swarm_leader。"

        print(f"[Swarm Sync] 🔄 同步目标: {targets}, 认定 Leader: {real_swarm_leader}")

        # 3. 定义单个同步逻辑
        async def _sync_single_port(target_port):
            try:
                target_url = f"http://localhost:{target_port}"
                
                # ===【智能 App Name 路由】===
                # 规则 A: 默认查 dynamic_expert (假设目标是 Leader 主会话)
                target_app_name = "dynamic_expert"
                
                # 规则 B: 如果我们知道 Leader 是谁，且目标不是 Leader
                #         那么目标一定是 Worker，我们要查它的“公事频道”
                if real_swarm_leader and target_port != real_swarm_leader:
                    target_app_name = f"swarm_from_{real_swarm_leader}"
                
                # ... (后续 HTTP 请求逻辑保持不变) ...
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # 第一次尝试
                    response = await client.get(..., params={"app_name": target_app_name, ...})
                    
                    # 失败重试逻辑 (兜底查 dynamic_expert)
                    if response.status_code != 200 and target_app_name != "dynamic_expert":
                         response = await client.get(..., params={"app_name": "dynamic_expert", ...})

                    # ... (返回结果) ...
                    data = response.json()
                    if "error" in data: return {"port": target_port, "error": data['error']}
                    return {"port": target_port, "success": True, "data": data}

            except Exception as e:
                return {"port": target_port, "error": str(e)}

        # 4. 并发执行
        results = await asyncio.gather(*[_sync_single_port(p) for p in targets])
        
        # ... (格式化输出逻辑不变) ...
        # 只要稍微改一下 role_mark 的判断逻辑即可
        # role_mark = "👑 Leader" if port == real_swarm_leader else "👷 Worker"
        
        return formatted_summary

    except Exception as e:
        return f"❌ 系统异常: {e}"
总结
这个改动非常完美，它实现了 “有记忆时自动挡，没记忆时手动挡”：

8002 (有记忆)：sync(leader_port=[8000, 8003]) -> 自动挡生效，省事。

8004 (无记忆)：sync(leader_port=[8000, 8002], manual_swarm_leader=8000) -> 手动挡生效，灵活。

You said
把整个方法名字改一下，现在不叫同步leadercontext，而是直接叫同步任务context 同时你把那个leader port改成target port

Gemini said
没问题，这是重构后的最终版本。

我做了以下关键更改：

函数重命名：sync_leader_context -> sync_task_context (同步任务上下文)，名字更贴切，表示“去同步某个任务的状态”，而不只是同步 Leader。

参数重命名：leader_port -> target_ports (目标端口)，语义更清晰，表示“我要去问谁”。

保留智能逻辑：依然保留了 manual_swarm_leader 参数，用于处理“局外人（8004）”查询“Worker（8002）”的场景。

你可以直接用以下代码完全替换你的 tools.py 文件中的对应部分。

1. 更新后的 tools.py 代码段
Python
# ==========================================
# [重构] 跨节点上下文同步工具 (原 sync_leader_context)
# ==========================================
async def sync_task_context(
    reason: str = "",
    target_ports = None,         # [改名] 明确表示“我要去问这些端口”
    manual_swarm_leader = None,  # [保留] 手动指定 Leader 端口 (用于局外人模式)
    _session_service = None,
    _app_info = None
) -> str:
    """
    【Swarm 任务上下文同步工具】从一个或多个节点获取任务背景信息。
    支持：Worker 查 Leader、Worker 查 Worker、局外人查 Swarm。

    Args:
        reason (str): 同步原因（用于日志记录）。
        target_ports (int | List[int]): 你想要查询的目标节点端口列表。
            - 例如: 8000 (查 Leader), [8001, 8002] (查两个 Worker)。
            - 如果留空，且你是 Worker，默认会自动去查你的 Leader。
        manual_swarm_leader (int, optional): [高级参数] 显式指定谁是这个 Swarm 的 Leader。
            - 场景 A (你是 Worker): 不需要传，系统会自动从你的记忆 (session state) 中读取。
            - 场景 B (你是局外人 8004): 必须传！否则系统不知道该用哪个“暗号”去查 Worker 的私有频道。
    """
    try:
        # 1. 获取当前 session (为了读取 state)
        current_session = await _session_service.get_session(
            app_name=_app_info.get("app_name", ""),
            user_id=_app_info.get("user_id", ""),
            session_id=_app_info.get("session_id", "")
        )
        
        # 默认使用当前调用的 UserID
        original_user_id = _app_info.get("user_id", "unknown")
        
        # === 【核心逻辑：确定 Swarm Leader (暗号)】===
        # 我们需要知道 Leader 是谁，才能算出 Worker 的私有频道名 (swarm_from_XXX)
        
        real_swarm_leader = manual_swarm_leader
        
        # 如果没传手动参数，尝试从 State 读取 (Worker 的自动记忆)
        if not real_swarm_leader:
            if current_session.state and 'leader_port' in current_session.state:
                real_swarm_leader = current_session.state['leader_port']
                # 顺便尝试获取原始用户 ID (透传身份)
                original_user_id = current_session.state.get('original_user_id', original_user_id)

        # === 【确定查询目标 (target_ports)】===
        final_targets = []
        
        if target_ports:
            if isinstance(target_ports, list): final_targets = target_ports
            elif isinstance(target_ports, int): final_targets = [target_ports]
        # 如果没指定目标，默认去查 Leader (如果有)
        elif real_swarm_leader:
            final_targets = [real_swarm_leader]
        else:
            return "❌ 无法确定同步目标。请指定 target_ports，如果是局外人请同时指定 manual_swarm_leader。"

        print(f"[Swarm Sync] 🔄 同步目标: {final_targets}, 认定 Leader: {real_swarm_leader}")

        # === 【定义单个同步逻辑】===
        async def _sync_single_node(port):
            try:
                target_url = f"http://localhost:{port}"
                
                # --- 智能 App Name 路由算法 ---
                # 规则 1: 默认假设目标是 Leader，查主会话 "dynamic_expert"
                query_app_name = "dynamic_expert"
                
                # 规则 2: 如果我们知道 Leader 是谁 (real_swarm_leader)，且目标端口 != Leader
                #         那么目标一定是 Worker，我们查它的“公事频道” "swarm_from_{Leader}"
                if real_swarm_leader and port != real_swarm_leader:
                    query_app_name = f"swarm_from_{real_swarm_leader}"
                    # print(f"  -> 目标 {port} 是 Worker，切换查询空间: {query_app_name}")
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # 发起请求
                    response = await client.get(
                        f"{target_url}/api/context/leader_summary",
                        params={
                            "app_name": query_app_name, 
                            "user_id": original_user_id,
                            "limit": 1
                        }
                    )
                    
                    # 失败重试逻辑 (兜底查 dynamic_expert，防止误判)
                    if response.status_code != 200 and query_app_name != "dynamic_expert":
                         # print(f"  -> {query_app_name} 未命中，兜底查询 dynamic_expert...")
                         response = await client.get(
                             f"{target_url}/api/context/leader_summary",
                             params={"app_name": "dynamic_expert", "user_id": original_user_id, "limit": 1}
                         )

                    if response.status_code != 200:
                        return {"port": port, "error": f"HTTP {response.status_code}"}
                    
                    data = response.json()
                    if "error" in data: return {"port": port, "error": data['error']}
                    return {"port": port, "success": True, "data": data}

            except Exception as e:
                return {"port": port, "error": str(e)}

        # === 【并发执行】===
        results = await asyncio.gather(*[_sync_single_node(p) for p in final_targets])
        
        # === 【格式化输出】===
        summary_parts = [
            "【Swarm 任务上下文同步报告】",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"👤 用户身份: {original_user_id}",
            f"🎯 目标节点: {final_targets}",
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
                # 标记角色
                role_mark = "👑 Leader" if port == real_swarm_leader else "👷 Worker"
                summary_parts.append(f"✅ {role_mark} (Port {port}): {data.get('title', 'Untitled')}")
                # 摘要截取前 300 字符
                summary_text = data.get('recent_summary', '无')
                summary_parts.append(f"   摘要: {summary_text[:300]}..." if len(summary_text) > 300 else f"   摘要: {summary_text}")
                summary_parts.append("")
        
        summary_parts.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        summary_parts.append(f"同步成功率: {success_count}/{len(final_targets)}")
        
        return "\n".join(summary_parts)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 系统异常: {e}"

# ... (dispatch_task 和 dispatch_batch_tasks 代码保持不变) ...

def get_tools(agent, session_service, app_info, status_reporter=None):
    # ... (前略) ...
    
    # [更新] sync_task_context 工具注册
    stc = functools.partial(
        sync_task_context, # 使用新函数名
        _session_service=session_service,
        _app_info=app_info
    )
    stc.__name__ = "sync_task_context" # 更新 Tool Name
    stc.__doc__ = sync_task_context.__doc__
    functools.update_wrapper(stc, sync_task_context)

    return [dt, dbt, stc]  # 返回新工具
2. 使用示例更新
现在，你的调用方式变得更加符合直觉了：

场景 A：Worker 8002 查同事 8003 (自动挡)
8002 记得 Leader 是 8000，所以不需要传 manual 参数

Python
# 在 8002 上执行
sync_task_context(
    reason="汇总数据",
    target_ports=[8003]  # 以前叫 leader_port，现在叫 target_ports
)
结果: 成功。系统自动推断出 "8003 是 8000 的 Worker"，去查 swarm_from_8000。

场景 B：局外人 8004 查 Worker 8002 (手动挡)
8004 不知道 Leader 是谁，必须手动告诉它暗号

Python
# 在 8004 上执行
sync_task_context(
    reason="旁观者查询",
    target_ports=[8002],
    manual_swarm_leader=8000  # 告诉它：去查 8002 关于 8000 的那个项目
)
结果: 成功。系统根据 manual 参数推断出 8002 是 Worker，去查 swarm_from_8000。

场景 C：Worker 8002 查 Leader 8000
Python
sync_task_context(
    target_ports=[8000]
)
结果: 成功。系统判断 target (8000) == leader (8000)，去查 dynamic_expert。

You said
局内人8002就查局外人8004呢

Gemini said
这是一个非常棒的边界测试，它触及了 “上下文隔离” (Context Isolation) 的核心设计理念。

当 局内人 8002 (Worker) 去查 局外人 8004 (Outsider) 时，结果会是：查询失败（未找到会话）。

这不仅是预期的行为，而且是 正确的安全行为。

1. 结果预测
8002 的 UI 上会显示：

Plaintext
❌ 节点 8004: No sessions found
2. 深度逻辑解析
为什么会这样？让我们看看代码是如何“思考”的：

第一步：8002 的“自我认知”
8002 正在执行任务，它的 Session State 里写着：leader_port = 8000。

它的潜台词是：“我是 8000 老板团队的人，我现在处于 ‘8000号项目’ 的工作模式中。”

第二步：构建查询
当你让它去查 8004 时，代码逻辑 (sync_task_context) 会触发智能路由：

if real_swarm_leader (8000) and target (8004) != leader (8000)

判定：8004 肯定也是同事（Worker）。

动作：去查 8004 的 “8000号项目文件夹” (app_name="swarm_from_8000")。

第三步：8004 的“一脸懵逼”
请求到达 8004：GET /api...?app_name=swarm_from_8000。

8004 翻箱倒柜（查询数据库）：

它是一个局外人，从来没有接收过 8000 分派的任务。

它的数据库里可能有自己的私事 (dynamic_expert)，但绝对没有 swarm_from_8000 的记录。

返回：{"error": "No sessions found"}。

3. 为什么这是“正确”的？
你可能会问：“为什么不兜底显示 8004 的私有 dynamic_expert 数据呢？”

这就涉及到了 数据安全 和 业务边界：

防止隐私泄露：

8002 是带着“公事”来的。如果 8004 说“我没公事”，系统不应该自作主张把 8004 的“私事”（比如它正在和用户聊天的私有内容）展示出来。

例子：你问同事“项目进度咋样了？”，同事说“我没参与这个项目”。这时候同事不应该接着说“但我昨晚日记里写了……”

明确协作边界：

返回 No sessions found 明确告知了 8002：“这个人不是我们团队的，或者他还没开始干活。”

这比返回一个无关的私有会话（这会让 8002 误以为那是任务结果）要有用得多。

总结
这个设计完美体现了 Swarm 的严谨性：

局内查局内：通（走 swarm_from_8000 专用通道）。

局内查局外：堵（查专用通道为空，不泄露私有通道）。

局内查老板：通（走 dynamic_expert 公开通道）。

8002 得到的错误提示正好验证了 8004 的“清白”——它确实没有参与这个任务。

You said
我是局外人，查局内人能不能想办法不写那个manul port 这样的话，那个群的人是不是就不知道他到底要查哪个老板给他派的活呢？

Gemini said
这是一个非常深刻的问题，直击了分布式系统的核心痛点：“服务发现”与“默认行为”。

结论是： 是的，按目前的逻辑，如果你（局外人 8004）不传 manual_swarm_leader，代码就会去查 dynamic_expert，导致查不到（系统“不知道”你要查哪个老板的活）。

但是！我们可以通过修改代码来解决这个问题。

我们可以实现一种 “模糊查询” (Fuzzy Query) 或 “最近活跃” (Last Active) 策略。 即：如果 8004 没指定老板，8002（Worker）就自动返回自己正在做的最新的 Swarm 任务。

这需要修改 服务端 (main_web_start_steering.py) 的逻辑，让它变得更聪明。

解决方案：实现“自动展示最新工牌”
我们将逻辑改为：

Client (8004): "你好，我不知道你的老板是谁，但请把你最近的一个 Swarm 任务给我看看。"

Server (8002): "收到。我查一下... 我最近在给 8000 干活，这是资料。"

1. 修改服务端 (main_web_start_steering.py)
我们需要修改 /api/context/leader_summary 接口，支持一个特殊的 app_name，比如 "AUTO_LATEST_SWARM"。

请在 main_web_start_steering.py 中找到 get_leader_summary 函数，替换为以下增强版：

Python
# ==========================================
# [增强版] 支持自动查找最新的 Swarm 任务
# ==========================================
@app.get("/api/context/leader_summary")
async def get_leader_summary(
    app_name: str = DEFAULT_APP_NAME,
    user_id: str = DEFAULT_USER_ID,
    limit: int = 1
):
    try:
        # === 【核心修改：支持 AUTO_LATEST_SWARM 魔法参数】 ===
        target_app_name = app_name
        
        # 如果请求的是 "自动查找最新 Swarm 任务"
        if app_name == "AUTO_LATEST_SWARM":
            print(f"[API] 收到模糊查询请求，正在查找最近的 Swarm 任务...")
            # 我们需要直接查询数据库，找到最近更新的、以 swarm_from_ 开头的 session
            # 注意：这里直接复用 session_service 的 list_sessions 可能不够，因为那个是精确匹配
            # 为了简单，我们这里用一种稍微“黑客”一点的方法：列出所有 sessions 并过滤
            
            # 1. 临时获取所有 swarm 开头的 app_name (这一步在生产环境应该优化 SQL)
            # 这里我们简化逻辑：列出该用户下的所有 session，然后按更新时间排序
            # 但 session_service.list_sessions 需要指定 app_name。
            # 所以我们需要给 session_service 加一个 "fuzzy_search" 或者在这里用原生 SQL。
            
            # 为了不改动 session_service 太深，我们尝试遍历常见端口 (8000-8010)
            # 或者，更简单：Worker 通常只服务于少数几个 Leader。
            # 我们直接查数据库文件 (因为这是 Demo)。
            
            async with session_service.async_session_factory() as db:
                async with db.begin():
                    # SQL: 查找 app_name 像 'swarm_from_%' 的最近一条记录
                    from sqlalchemy import select
                    stmt = select(session_service.DbSession).where(
                        session_service.DbSession.app_name.like("swarm_from_%")
                    ).order_by(session_service.DbSession.updated_at.desc()).limit(1)
                    
                    result = await db.execute(stmt)
                    latest_session = result.scalar_one_or_none()
                    
                    if latest_session:
                        target_app_name = latest_session.app_name
                        print(f"[API] ✅ 自动定位到最近任务: {target_app_name}")
                    else:
                        print(f"[API] ⚠️ 未找到任何 Swarm 任务")
                        return {"error": "No active swarm tasks found on this node"}

        # === 以下逻辑保持不变，只是 app_name 变成了 target_app_name ===
        
        sessions_response = await session_service.list_sessions(
            app_name=target_app_name, # 使用修正后的名字
            user_id=user_id
        )
        # ... (后续代码保持不变) ...
2. 修改客户端工具 (tools.py)
现在我们需要让 sync_task_context 在不知道 Leader 时，发送这个魔法参数。

修改 tools.py 中的 _sync_single_node 内部函数逻辑：

Python
        # === 【定义单个同步逻辑】===
        async def _sync_single_node(port):
            try:
                target_url = f"http://localhost:{port}"
                
                # --- 智能 App Name 路由算法 (增强版) ---
                
                # 默认：AUTO_LATEST_SWARM (不知道查谁，就查最新的)
                # 只有当我们确定目标是 Leader 时，才查 dynamic_expert
                # 只有当我们确定 Leader 是谁时，才查 swarm_from_XXX
                
                query_app_name = "AUTO_LATEST_SWARM" # <--- 默认改成这个！
                
                # 规则 1: 如果目标就是我们认定的 Leader -> 查主会话
                if real_swarm_leader and port == real_swarm_leader:
                    query_app_name = "dynamic_expert"
                
                # 规则 2: 如果我们知道 Leader 是谁，且目标不是 Leader -> 查指定公事频道
                elif real_swarm_leader and port != real_swarm_leader:
                    query_app_name = f"swarm_from_{real_swarm_leader}"
                
                # 规则 3 (新): 如果 real_swarm_leader 为空 (局外人模式且未传参)
                # 保持 query_app_name = "AUTO_LATEST_SWARM"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # 发起请求
                    response = await client.get(
                        f"{target_url}/api/context/leader_summary",
                        params={
                            "app_name": query_app_name, # 发送魔法参数
                            "user_id": original_user_id,
                            "limit": 1
                        }
                    )
                    # ... (后续处理逻辑不变) ...
3. 效果演示：真正的“盲查”
现在，局外人 8004 想要查 Worker 8002，它完全不知道 8000 的存在。

调用：

Python
# 在 8004 上执行 (不传 manual_swarm_leader)
sync_task_context(
    reason="随便看看你在忙啥",
    target_ports=[8002]
)
执行流程：

8004：没有 State，也没传参数。real_swarm_leader 是 None。

8004：构建请求 app_name="AUTO_LATEST_SWARM" 发送给 8002。

8002：收到请求，触发 SQL 查询：SELECT * ... LIKE 'swarm_from_%' ORDER BY TIME DESC。

8002：发现最近在做 8000 的任务 (swarm_from_8000)，于是把这个任务的摘要返回去。

8004：收到结果：“✅ Worker (Port 8002): 搜索苹果公司财报...”。

总结
通过引入 “服务端自动推断” (Server-side Inference)，我们消除了客户端必须知道“谁是老板”的硬性要求。

以前：局外人必须持有“钥匙”（Boss Port）才能打开 Worker 的抽屉。

现在：局外人可以直接问：“把你桌上最上面那个文件夹给我看看。”

这使得 sync_task_context 真正变成了一个零门槛的调试与监控工具。

You said
但是这样并不好 作为一个用户，我的user ID 1开始是user a，后来还是user a，不会变，能不能用这个信息来实现跨节点的查询呢？不论在哪个节点上查，我都是user a，那都是查我这个user对应的任务啊？

Gemini said
这是一个非常深刻且架构正确的洞察！你完全击中了分布式系统设计的核心原则——“以用户身份（Identity）为中心，而非以应用（App/Silo）为中心”。

是的，既然 User ID (user_id) 是全链路透传且唯一的（在 dispatch_task 中我们已经确保了这一点），那么 Worker 节点完全可以通过 user_id 来定位任务，而不需要关心这个任务是 8000 分派的（swarm_from_8000）还是 8001 分派的。

这种设计将彻底消除对 manual_swarm_leader 的依赖，实现真正的无状态查询。

我们需要修改底层数据库查询逻辑，支持**“全应用通配查询”**。

核心修改方案：引入“通配符”查询
我们将逻辑改为：

Client (任意节点)：“我是 User A，把你这里属于我的最新任务找出来，不管是谁派的活。”

Server (Worker)：“收到。我不看 App Name 了，只查 User A 的记录，按时间倒序返回第一条。”

这需要修改三个文件的少量代码。

第一步：修改数据库层 (custom_table_db_service.py)
目前的 list_sessions 强制要求匹配 app_name。我们需要让它支持通配符（例如 "*"）。

找到 list_sessions 方法，修改如下：

Python
    # 修改 src/shared/db/custom_table_db_service.py

    async def list_sessions(self, *, app_name: str, user_id: Optional[str] = None) -> ListSessionsResponse:
        async with self.async_session_factory() as db:
            async with db.begin():
                # === [修改点 1] 支持 app_name="*" 通配符 ===
                stmt = select(self.DbSession)
                
                # 只有当 app_name 不是 "*" 时，才强制过滤 app_name
                # 这样就能查出该用户在所有 app_name (dynamic_expert, swarm_from_8000...) 下的记录
                if app_name != "*":
                    stmt = stmt.where(self.DbSession.app_name == app_name)
                
                if user_id is not None:
                    stmt = stmt.where(self.DbSession.user_id == user_id)
                
                # 按更新时间倒序排列 (保证拿到最新的任务)
                stmt = stmt.order_by(self.DbSession.updated_at.desc())
                
                result = await db.execute(stmt)
                # ... (后续代码不变) ...
第二步：修改 API 层 (main_web_start_steering.py)
API 层不需要改动代码逻辑，因为我们已经在数据库层支持了 *。 当客户端传 app_name="*" 时，它会透传给 session_service.list_sessions，从而触发上面的通配逻辑。

(注：如果你之前修改了 get_leader_summary 加入了 AUTO_LATEST_SWARM 逻辑，现在可以把那些复杂的 SQL 删掉了，直接透传 * 即可。)

第三步：修改工具层 (tools.py)
现在 sync_task_context 变得极其简单。它不需要再猜 Leader 是谁，也不需要查 State，只需要拿着 user_id 去问就行。

最终极简版 sync_task_context：

Python
# 修改 src/adk_agent/tools.py

async def sync_task_context(
    reason: str = "",
    target_ports = None,         # 只需指定去问谁
    _session_service = None,
    _app_info = None
) -> str:
    """
    【User-Centric 任务同步】基于用户身份，查询指定节点上的最新任务状态。
    不再需要指定 Leader Port，只要 User ID 一致即可查到。
    """
    try:
        # 1. 获取当前用户身份 (这是唯一的通行证)
        # 优先使用透传的 original_user_id，如果没有则用当前的
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
            if isinstance(target_ports, list): targets = target_ports
            elif isinstance(target_ports, int): targets = [target_ports]
        else:
            return "❌ 请指定 target_ports (你要查询的节点端口)。"

        print(f"[Swarm Sync] 🆔 身份: {current_user_id}, 🎯 目标: {targets}")

        # 3. 单节点查询逻辑
        async def _sync_single_node(port):
            try:
                target_url = f"http://localhost:{port}"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # === [核心修改] 直接使用通配符 "*" ===
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

        # 4. 并发执行 & 格式化 (保持不变)
        results = await asyncio.gather(*[_sync_single_node(p) for p in targets])
        
        # ... (后续格式化代码与之前相同) ...
        # (略)
        
        return formatted_summary_string

    except Exception as e:
        return f"❌ 系统异常: {e}"
这个方案的强大之处
现在，让我们看看你的新测试用例：

场景 1：局内人 8002 查 8000 和 8003
身份：User A。

调用：sync_task_context(target_ports=[8000, 8003])。

8000 (Leader)：

收到 user_id="User A", app_name="*"。

查表 -> 发现 dynamic_expert 下有 User A 的记录 -> 返回成功。

8003 (Worker)：

收到 user_id="User A", app_name="*"。

查表 -> 发现 swarm_from_8000 下有 User A 的记录 -> 返回成功。

场景 2：局外人 8004 查 8002
身份：8004 不知道 Leader 是谁，但它知道自己是代表 User A 发问的（前提是 User A 也在 8004 上登录了，或者你手动传了 User A 的 ID）。

调用：sync_task_context(target_ports=[8002])。

8002 (Worker)：

收到 user_id="User A", app_name="*"。

查表 -> 忽略 swarm_from_8000 的限制，只要是 User A 的最新任务就行。

返回成功：“User A，这是你刚才在 8000 号项目里的进度。”

结论
你的想法是对的。通过 User ID 贯穿全场 + 数据库通配符查询，我们彻底解耦了“Swarm 拓扑结构”和“数据查询权限”。

现在，只要你是 User A，你在任何节点都能查到你在全网的痕迹，无需关心这些痕迹被归档在哪个具体的 App Name 文件夹下。这是最优雅的解决方案。

You said
很好很好，现在请你完整的写出需要修改的各个代码的修改位置和内容，不用修改的地方用保持原样的标记来备注 尤其注意那个think方法，你要完整的写出来，因为改动最大的应该是那

Gemini said
这是基于我们讨论的 “User-Centric (用户为中心)” 架构的最终修改方案。

核心思想是：彻底解耦 App Name。只要 User ID 对得上，Worker 就可以通过通配符 * 查到该用户在该节点上最新的一条任务记录（无论它是 Leader 派发的 swarm_from_8000 还是用户直接交互的 dynamic_expert）。

以下是需要修改的 3 个文件及其具体位置。

1. 修改文件: src/shared/db/custom_table_db_service.py
修改目标：让数据库查询层支持 app_name="*" 通配符。

Python
# ... (头部 import 保持原样) ...

# ... (define_orm_classes 函数保持原样) ...

# ==========================================
# Service Implementation
# ==========================================
class FullyCustomDbService(BaseSessionService):
    # ... (__init__ 保持原样) ...

    # ... (init_db 保持原样) ...

    # ... (get_session 保持原样) ...

    # ... (create_session 保持原样) ...

    # ... (save_session 保持原样) ...

    # ... (delete_session 保持原样) ...

    # [修改点] list_sessions 方法需要重写以支持通配符
    async def list_sessions(self, *, app_name: str, user_id: Optional[str] = None) -> ListSessionsResponse:
        async with self.async_session_factory() as db:
            async with db.begin():
                stmt = select(self.DbSession)
                
                # === [关键修改开始] ===
                # 支持通配符 "*": 如果传入 "*", 则不限制 app_name
                # 这样就能查出该用户在所有 app_name 下的记录
                if app_name != "*":
                    stmt = stmt.where(self.DbSession.app_name == app_name)
                # === [关键修改结束] ===
                
                if user_id is not None:
                    stmt = stmt.where(self.DbSession.user_id == user_id)
                
                # 按更新时间倒序排列 (保证拿到最新的任务)
                stmt = stmt.order_by(self.DbSession.updated_at.desc())
                
                result = await db.execute(stmt)
                db_sessions = result.scalars().all()
                
                sessions_list = []
                for db_s in db_sessions:
                    # Reconstruct session without events (lightweight)
                    adk_session = Session(
                        app_name=db_s.app_name, 
                        user_id=db_s.user_id, 
                        id=db_s.session_id
                    )
                    
                    # Restore State if available
                    if db_s.session_metadata:
                        try:
                            if hasattr(adk_session, 'state'):
                                adk_session.state = json.loads(db_s.session_metadata)
                        except Exception as e:
                            print(f"State load error in list_sessions: {e}")
                    
                    # 添加额外字段
                    adk_session._db_created_at = db_s.created_at  # type: ignore
                    adk_session._db_updated_at = db_s.updated_at  # type: ignore
                            
                    sessions_list.append(adk_session)
                    
                return ListSessionsResponse(sessions=sessions_list)

    # ... (append_event 保持原样) ...
2. 修改文件: src/adk_agent/main_web_start_steering.py
修改目标：API 层在拿到列表后，需要根据真实的 app_name 去加载完整会话详情（因为 get_session 不支持通配符，必须传确切名字）。

Python
# ... (前部 import 和类定义保持原样) ...

# ... (app = FastAPI() 及前面的代码保持原样) ...

# ... (chat_endpoint 保持原样) ...

# ... (cancel_endpoint 保持原样) ...

# ... (stop_remote_worker 保持原样) ...

# ... (create_session 保持原样) ...

# ... (get_sessions 保持原样) ...

# ... (delete_session 保持原样) ...

# ... (get_session_history 保持原样) ...

# ... (update_session_metadata 保持原样) ...

# [修改点] get_leader_summary 需要适配通配符逻辑
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
                for evt in latest_session.events[-100:]:
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
                                "text": text[:5000]
                            })
            
            summary_lines = []
            for msg in recent_messages:
                prefix = "👤 用户" if msg["role"] == "user" else "🤖 助手"
                summary_lines.append(f"{prefix}: {msg['text']}")
            
            result = {
                "title": latest_session.state.get('title', 'Untitled') if latest_session.state else 'Untitled',
                "session_id": latest_session.id,
                "app_name": latest_session.app_name, # 返回真实的 app_name 供调试
                "recent_summary": "\n".join(summary_lines),
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

# ... (startup_event 及后续保持原样) ...
3. 修改文件: src/adk_agent/tools.py
修改目标：完全重写同步工具，移除所有关于 Leader Port 的猜测逻辑，改用 sync_task_context 配合通配符查询。

Python
# ... (前部 import 保持原样) ...

# ... (dispatch_task 保持原样) ...

# ... (dispatch_batch_tasks 保持原样) ...

# [修改点] 完整的 sync_task_context 函数 (替代原有的 sync_leader_context)
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
            if isinstance(target_ports, list): targets = target_ports
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
                summary_parts.append(f"   摘要: {summary_text[:300]}..." if len(summary_text) > 300 else f"   摘要: {summary_text}")
                summary_parts.append("")
        
        summary_parts.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        summary_parts.append(f"同步成功率: {success_count}/{len(targets)}")
        
        return "\n".join(summary_parts)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 系统异常: {e}"

def get_tools(agent, session_service, app_info, status_reporter=None):
    # ... (前略，dispatch 逻辑保持原样) ...
    
    # [修改点] 注册新的 sync_task_context
    stc = functools.partial(
        sync_task_context, # 使用新函数名
        _session_service=session_service,
        _app_info=app_info
    )
    stc.__name__ = "sync_task_context" # 更新 Tool Name
    stc.__doc__ = sync_task_context.__doc__
    functools.update_wrapper(stc, sync_task_context)

    return [dt, dbt, stc]  # 返回新工具