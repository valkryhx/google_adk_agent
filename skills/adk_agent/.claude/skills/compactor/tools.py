"""
Compactor Skill - 智能上下文压缩器

采用 Rolling Summary 策略 + 原生状态查询：
- 对话轮数：从 session.events 获取
- 工具数量：从 agent.tools 获取
- 不依赖外部追踪器
"""

from typing import List, Optional


async def _smart_compact(
    summary: str,
    agent_instance: object,
    session_service: object,
    app_name: str,
    user_id: str,
    session_id: str,
    unload_tools: bool = True
) -> str:
    """
    智能压缩上下文：清空历史并保留摘要
    
    Args:
        summary: 对当前对话的总结（必须包含任务目标、进展、结论等）
        agent_instance: Agent 实例
        session_service: 会话服务实例
        app_name: 应用名称
        user_id: 用户 ID
        session_id: 会话 ID
        unload_tools: 是否卸载临时工具
        
    Returns:
        执行结果消息
    """
    results = []
    
    # 1. 记录摘要
    print("[INFO] 已接收上下文摘要")
    results.append("[INFO] 已接收上下文摘要")

    # 2. 获取当前状态（使用原生 API）
    message_count = 0
    session = None
    
    print(f"[DEBUG] 尝试获取 Session: app={app_name}, user={user_id}, id={session_id}")
    
    try:
        if hasattr(session_service, 'get_session'):
            session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
            
            if session is None:
                print(f"[WARN] get_session 返回 None")
                if hasattr(session_service, 'sessions'):
                    print(f"[DEBUG] 当前所有 Session: {session_service.sessions.keys()}")
                    if app_name in session_service.sessions:
                        print(f"[DEBUG] App {app_name} 下的用户: {session_service.sessions[app_name].keys()}")
            
            if session and hasattr(session, 'events') and session.events:
                message_count = len(session.events)
                msg = f"[INFO] 压缩前对话包含 {message_count} 条消息"
                print(msg)
                results.append(msg)
    except Exception as e:
        msg = f"[WARN] 获取会话历史时出错: {e}"
        print(msg)
        results.append(msg)

    # 3. 执行压缩（原地截断）
    try:
        if session and hasattr(session, 'events'):
            events = session.events
            if not events:
                msg = "[INFO] 会话为空，无需压缩"
                print(msg)
                results.append(msg)
            else:
                # 寻找保留点：保留 System 消息和最近一轮交互
                msg = f"[DEBUG] 截断前事件总数: {len(events)}"
                print(msg)
                results.append(msg)
                
                # 1. 收集 System 消息
                kept_events = []
                for evt in events:
                    # [Fix] Event.role is nested in content
                    role = 'unknown'
                    if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
                        role = evt.content.role
                        
                    if role == 'system':
                        kept_events.append(evt)
                    else:
                        break 
                
                # 2. 寻找当前的 smart_compact 调用（Model 消息）
                # 我们必须保留它，以便 Runner 能将 Output 追加到正确位置
                current_tool_call_idx = -1
                print(f"[DEBUG] 开始倒序查找 smart_compact 调用, 总事件数: {len(events)}")
                for i in range(len(events) - 1, -1, -1):
                    evt = events[i]
                    
                    # [Fix] Event 对象没有直接的 role 属性，它在 content 中
                    role = 'unknown'
                    if hasattr(evt, 'content') and evt.content:
                        if hasattr(evt.content, 'role'):
                            role = evt.content.role
                    
                    print(f"[DEBUG] Checking Event[{i}]: Type={type(evt).__name__}, Role={repr(role)}")
                    
                    if role == 'model':
                        # 检查是否调用了 smart_compact
                        is_target_call = False
                        if hasattr(evt, 'content') and hasattr(evt.content, 'parts'):
                            for part_idx, part in enumerate(evt.content.parts):
                                if hasattr(part, 'function_call') and part.function_call:
                                    fc_name = part.function_call.name
                                    print(f"[DEBUG] Event[{i}] Role={role} Part[{part_idx}] FunctionCall: '{fc_name}'")
                                    if 'smart_compact' in fc_name:
                                        print(f"[DEBUG] Found match at Event[{i}]")
                                        is_target_call = True
                                        break
                                else:
                                    print(f"[DEBUG] Event[{i}] Role={role} Part[{part_idx}] No FunctionCall")
                                    pass
                        if is_target_call:
                            current_tool_call_idx = i
                            break
                    else:
                        print(f"[DEBUG] Skipping Event[{i}] Role={role} (Not 'model')")
                        pass

                # 3. 构建精简历史 (Hard Reset)
                # 目标结构: System + User(Placeholder) + Model(Call smart_compact)
                if current_tool_call_idx != -1:
                    import copy
                    
                    # 构造占位符 User 消息
                    # 我们克隆第一个 System 消息（通常存在）作为模板，以确保对象类型正确
                    placeholder_user_evt = None
                    
                    # [Fix] 如果没有 System 消息，尝试使用第一个事件作为模板
                    template_source = kept_events[0] if kept_events else (events[0] if events else None)
                    
                    if template_source:
                        try:
                            placeholder_user_evt = copy.deepcopy(template_source)
                            
                            # [Fix] 设置 role 到 content.role
                            if hasattr(placeholder_user_evt, 'content') and placeholder_user_evt.content:
                                placeholder_user_evt.content.role = 'user'
                            
                            # 尝试修改内容为简单的文本
                            if hasattr(placeholder_user_evt, 'content') and hasattr(placeholder_user_evt.content, 'parts'):
                                # 清空原有 parts
                                placeholder_user_evt.content.parts = []
                                # 我们无法直接创建 Part 对象（未导入），所以尝试复用原有的 Part 对象（如果有）
                                # 或者更简单：如果无法创建 Part，就让它保持空？不，空的 User 消息可能非法。
                                # 让我们尝试复用 events[current_tool_call_idx] 中的 Part 结构
                                template_evt = events[current_tool_call_idx]
                                if template_evt.content.parts:
                                    # 克隆一个 Part
                                    new_part = copy.deepcopy(template_evt.content.parts[0])
                                    # 清除 function_call/response
                                    if hasattr(new_part, 'function_call'): new_part.function_call = None
                                    if hasattr(new_part, 'function_response'): new_part.function_response = None
                                    # 设置文本
                                    if hasattr(new_part, 'text'): 
                                        new_part.text = "[System] Context cleared. Resuming with summary."
                                    
                                    placeholder_user_evt.content.parts = [new_part]
                        except Exception as e:
                            print(f"[WARN] 构造占位消息失败: {e}")
                            placeholder_user_evt = None

                    if placeholder_user_evt:
                        new_events = kept_events + [placeholder_user_evt] + events[current_tool_call_idx:]
                        
                        # [Fix] In-place update to ensure persistence if Runner holds reference
                        if hasattr(session.events, 'clear') and hasattr(session.events, 'extend'):
                            session.events.clear()
                            session.events.extend(new_events)
                        else:
                            # Fallback for lists that don't support clear/extend (unlikely for standard lists)
                            session.events[:] = new_events
                        
                        # [Critical Fix] InMemorySessionService returns a deepcopy, so we MUST update the internal storage
                        try:
                            from google.adk.sessions import InMemorySessionService
                            if isinstance(session_service, InMemorySessionService):
                                if (app_name in session_service.sessions and 
                                    user_id in session_service.sessions[app_name] and 
                                    session_id in session_service.sessions[app_name][user_id]):
                                    
                                    stored_session = session_service.sessions[app_name][user_id][session_id]
                                    # Update events
                                    if hasattr(stored_session.events, 'clear') and hasattr(stored_session.events, 'extend'):
                                        stored_session.events.clear()
                                        stored_session.events.extend(new_events)
                                    else:
                                        stored_session.events[:] = new_events
                                    print("[系统] 已强制同步会话状态到存储 (smart_compact)")
                        except Exception as e:
                            print(f"[警告] 强制同步会话失败: {e}")
                        
                        removed_count = message_count - len(new_events)
                        msg1 = f"[OK] 已重置历史 (Hard Reset)，移除 {removed_count} 条消息"
                        msg2 = f"[DEBUG] 最终结构: System({len(kept_events)}) -> User(Placeholder) -> Model(CurrentCall)"
                        print(msg1)
                        print(msg2)
                        print(f'压缩后events数量 (Local): {len(session.events)}')
                        
                        # Verify storage update
                        if 'stored_session' in locals() and stored_session:
                            print(f'压缩后events数量 (Storage): {len(stored_session.events)}')
                        results.append(msg1)
                        results.append(msg2)
                    else:
                        msg = "[WARN] 无法构造占位 User 消息，放弃截断"
                        print(msg)
                        results.append(msg)
                else:
                    msg = "[WARN] 未找到当前 Tool Call，无法安全截断"
                    print(msg)
                    results.append(msg)
                    
                    # DEBUG: 打印最后几个事件的结构以供分析
                    if events:
                        print("[DEBUG] 事件结构采样 (Last 10):")
                        for j in range(max(0, len(events)-10), len(events)):
                            e = events[j]
                            print(f"  Event[{j}]: Type={type(e)}")
                            if hasattr(e, '__dict__'):
                                print(f"    Vars: {vars(e)}")
                            else:
                                print(f"    Str: {str(e)}")
                            if hasattr(e, 'role'):
                                print(f"    Role: {e.role}")
        else:
             msg = "[WARN] 无法访问会话事件列表"
             print(msg)
             results.append(msg)

    except Exception as e:
        import traceback
        msg1 = f"[WARN] 压缩会话时出错: {e}"
        msg2 = f"[DEBUG] {traceback.format_exc()}"
        print(msg1)
        print(msg2)
        results.append(msg1)
        results.append(msg2)

    # 4. 卸载动态工具
    if unload_tools:
        try:
            import sys
            
            # 尝试获取 main 模块中的 agent 实例
            target_agent = None
            
            # 1. 尝试从传入参数获取
            if agent_instance and hasattr(agent_instance, 'tools'):
                target_agent = agent_instance
                # print("[DEBUG] 使用传入的 agent_instance") 
                results.append("[DEBUG] 使用传入的 agent_instance")
            
            # 2. 如果参数无效，尝试从 sys.modules 获取
            if not target_agent:
                main_module = sys.modules.get('__main__')
                if main_module and hasattr(main_module, 'my_agent'):
                    target_agent = main_module.my_agent
                    # print("[DEBUG] 从 __main__ 模块获取 my_agent")
                    results.append("[DEBUG] 从 __main__ 模块获取 my_agent")
                
                if not target_agent:
                    # 尝试完整包名
                    adk_main = sys.modules.get('skills.adk_agent.main')
                    if adk_main and hasattr(adk_main, 'my_agent'):
                        target_agent = adk_main.my_agent
                        # print("[DEBUG] 从 skills.adk_agent.main 模块获取 my_agent")
                        results.append("[DEBUG] 从 skills.adk_agent.main 模块获取 my_agent")

            if target_agent and hasattr(target_agent, 'tools'):
                original_count = len(target_agent.tools)
                msg = f"[DEBUG] 当前工具数量: {original_count}"
                print(msg)
                results.append(msg)
                
                # 保留前两个工具:skill_load 和 bash
                if original_count > 2:
                    target_agent.tools = target_agent.tools[:2]  # 保留 skill_load 和 bash
                    new_count = len(target_agent.tools)
                    msg = f"[OK] 已卸载 {original_count - 2} 个临时工具,剩余 {new_count} 个"
                    print(msg)
                    results.append(msg)
                else:
                    msg = "[INFO] 没有需要卸载的临时工具"
                    print(msg)
                    results.append(msg)
            else:
                msg = "[WARN] 无法获取有效的 Agent 实例，工具卸载失败"
                print(msg)
                results.append(msg)
                
        except Exception as e:
            import traceback
            msg1 = f"[WARN] 卸载工具时出错: {e}"
            msg2 = f"[DEBUG] 堆栈: {traceback.format_exc()}"
            print(msg1)
            print(msg2)
            results.append(msg1)
            results.append(msg2)

    results.append("\n[状态] Agent 已重置为轻量化状态")
    results.append("--------------------------------------------------")
    results.append("请将以下摘要作为新对话的上下文：")
    results.append(summary)
    results.append("--------------------------------------------------")

    return "\n".join(results)


async def _get_compression_status(
    agent_instance: object,
    session_service: object,
    app_name: str,
    user_id: str,
    session_id: str
) -> str:
    """
    获取当前压缩状态和建议（使用原生 session 和 agent 状态）

    Args:
        agent_instance: Agent 实例
        session_service: 会话服务实例
        app_name: 应用名称
        user_id: 用户 ID
        session_id: 会话 ID

    Returns:
        状态报告
    """
    result = ["[压缩状态分析]"]

    # 1. 从 session 获取对话轮数
    turn_count = 0
    try:
        if hasattr(session_service, 'get_session'):
            session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
            if session and hasattr(session, 'events') and session.events:
                turn_count = len(session.events)
    except Exception:
        pass
    
    result.append(f"   对话消息数: {turn_count}")
    
    # 2. 从 agent 获取工具数量
    tool_count = 0
    if hasattr(agent_instance, 'tools'):
        tool_count = len(agent_instance.tools)
    result.append(f"   已加载工具数: {tool_count}")

    # 3. 判断是否需要压缩
    result.append("\n[建议]")
    
    should_compact = turn_count > 100 or tool_count > 50
    
    if should_compact:
        result.append("   [!] 建议立即执行压缩")
        if turn_count > 100:
            result.append(f"   - 对话消息数 ({turn_count}) 超过阈值 (100)")
        if tool_count > 50:
            result.append(f"   - 工具数量 ({tool_count}) 超过阈值 (50)")
    elif tool_count > 25 or turn_count > 50:
        result.append("   - 状态正常，可考虑稍后压缩")
    else:
        result.append("   - 状态良好，暂无需压缩")

    return "\n".join(result)


# 工具函数字典
COMPACTOR_TOOLS = {
    "smart_compact": _smart_compact,
    "get_compression_status": _get_compression_status,
}


from functools import partial

def get_tools(agent_instance: object = None, session_service: object = None, app_info: dict = None) -> List:
    """
    返回所有压缩器工具函数列表（自动绑定上下文）
    
    Args:
        agent_instance: Agent 实例
        session_service: 会话服务实例
        app_info: 应用信息字典 (app_name, user_id, session_id)
    """
    tools = []
    
    # 需要上下文的工具
    if agent_instance and session_service and app_info:
        # 1. 包装 smart_compact，隐藏系统参数
        async def run_smart_compact(summary: str) -> str:
            """
            智能压缩上下文：清空历史并保留摘要。
            当对话过长或任务阶段性完成时调用此工具。
            
            Args:
                summary: 对当前对话的总结（必须包含任务目标、进展、结论等）
            """
            return await _smart_compact(
                summary=summary,
                agent_instance=agent_instance,
                session_service=session_service,
                app_name=app_info.get('app_name'),
                user_id=app_info.get('user_id'),
                session_id=app_info.get('session_id')
            )
        
        # 显式设置名称，确保 deduplication 正常工作
        run_smart_compact.__name__ = "smart_compact"
        tools.append(run_smart_compact)
        
        # 2. 包装 get_compression_status
        async def run_get_compression_status() -> str:
            """
            获取当前压缩状态建议
            """
            return await _get_compression_status(
                agent_instance=agent_instance,
                session_service=session_service,
                app_name=app_info.get('app_name'),
                user_id=app_info.get('user_id'),
                session_id=app_info.get('session_id')
            )
            
        run_get_compression_status.__name__ = "get_compression_status"
        tools.append(run_get_compression_status)
        
    return tools
