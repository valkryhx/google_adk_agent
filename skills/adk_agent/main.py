"""
ADK Dynamic Skills Agent - 主入口 (增强版)

核心特性：
1. 两阶段懒加载：初始化只加载 name+description，按需加载完整 Instructions
2. 动态工具挂载：运行时挂载和卸载工具函数
3. 增强的系统提示词：ReAct 推理、错误恢复、多轮对话
4. 结构化日志：详细的执行跟踪

启动
python -m skills.adk_agent.main -i
"""

import asyncio
import os
import sys

# 将当前目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.manager import SkillManager
from core.executor import execute_python_code, execute_context_compact
from core.logger import AgentLogger, logger
from config import AgentConfig, build_system_prompt
from google.genai import types

# 全局实例
my_agent = None
compactor_agent = None
session_service = None
sm = None
config = AgentConfig()

# 会话标识常量 (app_name + user_id + session_id 唯一确定一个会话)
DEFAULT_APP_NAME = "dynamic_expert"
DEFAULT_USER_ID = "user_001"
DEFAULT_SESSION_ID = "session_001"


def setup_env():
    """准备测试环境"""
    # 验证配置
    errors = config.validate()
    if errors:
        for err in errors:
            logger.warn(err)
    
    # 创建测试数据
    try:
        import pandas as pd
        pd.DataFrame({
            'date': ['2025-01-01', '2025-01-02', '2025-01-03'],
            'sales_val': [100, 150, 120]
        }).to_csv('data.csv', index=False)
        logger.info("测试数据文件 data.csv 已创建")
    except ImportError:
        logger.debug("pandas 未安装，跳过测试数据创建")


async def skill_load(skill_id: str) -> str:
    """
    动态网关：按需加载 Instructions 并物理挂载工具
    
    这是 Agent 唯一初始拥有的工具。当 Agent 需要某个技能时，
    会调用此函数来加载完整的 Instructions 并挂载对应的工具。
    
    Args:
        skill_id: 技能标识符，如 "data_analyst", "codebase_search"
        
    Returns:
        技能的完整 Instructions 内容，包含执行指令和示例
    """
    global my_agent, session_service, sm
    
    print(f"[系统] 激活技能: {skill_id}")
    logger.info(f"激活技能: {skill_id}")

    # 验证技能是否存在
    if not sm.skill_exists(skill_id):
        available = sm.list_skills()
        return f"[ERROR] 技能 '{skill_id}' 不存在。可用技能: {available}"



    # 动态加载技能的工具模块
    tools_loaded = _load_skill_tools(skill_id)
    if tools_loaded:
        logger.skill_loaded(skill_id, tools_loaded)

    # 返回完整的 Instructions
    sop = sm.load_full_sop(skill_id)
    return f"""[OK] 技能 '{skill_id}' 已加载，以下是执行指令：

{sop}

---
[注意] 请严格按照上述 Instructions 执行任务。如有工具使用问题，请查看工具的 docstring。
"""


def _load_skill_tools(skill_id: str):
    """从技能目录加载 tools.py 并挂载工具"""
    global my_agent
    
    import importlib.util
    
    tools_path = os.path.join(config.skills_path, skill_id, "tools.py")
    
    if not os.path.exists(tools_path):
        # 如果没有 tools.py，回退到通用执行器
        if skill_id == "data_analyst" and execute_python_code not in my_agent.tools:
            my_agent.tools.append(execute_python_code)
            return [execute_python_code]
        return []
    
    try:
        # 动态加载模块
        spec = importlib.util.spec_from_file_location(f"skill_{skill_id}", tools_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 获取工具函数
        if hasattr(module, 'get_tools'):
            # 尝试注入上下文依赖
            try:
                app_info = {
                    "app_name": DEFAULT_APP_NAME,
                    "user_id": DEFAULT_USER_ID,
                    "session_id": DEFAULT_SESSION_ID
                }
                tools = module.get_tools(my_agent, session_service, app_info)
            except TypeError:
                # 如果不支持依赖注入，则无参调用
                tools = module.get_tools()
        elif hasattr(module, 'TOOLS'):
            tools = list(module.TOOLS.values())
        else:
            # 查找所有可调用对象（排除内置函数）
            tools = [
                getattr(module, name) for name in dir(module)
                if callable(getattr(module, name)) 
                and not name.startswith('_')
                and hasattr(getattr(module, name), '__module__')
            ]
        
        # 挂载工具
        loaded = []
        existing_tool_names = {t.__name__ for t in my_agent.tools if hasattr(t, '__name__')}
        existing_tool_strs = {str(t) for t in my_agent.tools if not hasattr(t, '__name__')}
        
        for tool in tools:
            tool_name = tool.__name__ if hasattr(tool, '__name__') else str(tool)
            tool_str = str(tool)
            
            # 支持函数类型工具（callable）和对象类型工具（如 McpToolset）
            # ADK 支持将对象作为工具，对象类型工具通过类型检查识别
            is_new_tool = False
            if hasattr(tool, '__name__'):
                is_new_tool = tool_name not in existing_tool_names
            else:
                is_new_tool = tool_str not in existing_tool_strs
            
            if is_new_tool:
                # 对于函数类型工具，需要是 callable
                # 对于对象类型工具（如 McpToolset），ADK 也支持，不需要是 callable
                # 检查是否为 ADK 工具对象类型（通过检查类型名称或模块路径）
                is_tool_object = False
                try:
                    tool_type = type(tool)
                    type_name = tool_type.__name__
                    module_name = getattr(tool_type, '__module__', '')
                    # 检查是否为 ADK 工具对象（如 McpToolset）
                    is_tool_object = 'google.adk.tools' in module_name or 'Toolset' in type_name
                except:
                    pass
                
                if callable(tool) or is_tool_object:
                    my_agent.tools.append(tool)
                    loaded.append(tool)
                    if hasattr(tool, '__name__'):
                        existing_tool_names.add(tool_name)
                    else:
                        existing_tool_strs.add(tool_str)
        
        return loaded
    except Exception as e:
        logger.error(f"加载工具模块失败: {skill_id}", error=str(e))
        return []


def create_agent(custom_config: AgentConfig = None):
    """创建并返回 Agent 实例"""
    global my_agent, compactor_agent, session_service, sm, config
    
    if custom_config:
        config = custom_config
    
    try:
        from google.adk.agents import LlmAgent, RunConfig
        from google.adk.agents.run_config import StreamingMode
        from google.adk.sessions import InMemorySessionService
        from google.adk.models.lite_llm import LiteLlm
    except ImportError:
        logger.error("请先安装 google-adk: pip install google-adk litellm")
        sys.exit(1)

    # 初始化技能管理器
    sm = SkillManager(base_path=config.skills_path)
    session_service = InMemorySessionService()

    # 获取技能清单
    skill_manifests = sm.get_discovery_manifests()
    print(f"[系统] 发现 {len(sm.list_skills())} 个技能")
    logger.info(f"发现 {len(sm.list_skills())} 个技能")
    
    if config.verbose:
        print("\n[技能列表] 已发现的技能:")
        print(skill_manifests)

    # 构建增强的系统提示词
    system_prompt = build_system_prompt(config, skill_manifests)

    # 创建 LiteLLM 模型实例 (DashScope 阿里云通义千问)
    # 使用 openai/ 前缀表示 OpenAI 兼容的 API
    llm_model = LiteLlm(
        model=config.model,  # 例如: "openai/qwen3-32b"
        api_key=config.api_key,
        api_base=config.api_base,
        extra_body=config.extra_body,  # 关闭 thinking
    )
    
    # 定义工具错误处理回调
    def handle_tool_error(tool, args, tool_context, error):
        """处理工具执行错误，返回友好的错误信息，避免中断对话"""
        error_msg = f"Tool execution failed: {str(error)}"
        logger.error(f"工具 {tool.name} 执行出错", error=str(error))
        return {"error": error_msg, "status": "failed"}

    # 创建 LlmAgent (注意：使用 LlmAgent 而非 Agent)
    # 创建 AutoCompactAgent (Sub-Agent)
    from auto_compact_agent import AutoCompactAgent
    compactor_agent = AutoCompactAgent(config)

    # 创建主 Agent
    my_agent = LlmAgent(
        name=config.name,
        model=llm_model,
        instruction=system_prompt,
        tools=[skill_load],
        sub_agents=[compactor_agent], # Register sub-agent
        on_tool_error_callback=handle_tool_error,
        #不读取历史信息 专注于本次对话
        #include_contents='none' ,
    )
    
    print(f"[系统] Agent '{config.name}' 已创建 (model={config.model})")
    logger.info(f"Agent '{config.name}' 已创建", model=config.model)

    return my_agent


async def run_agent(task: str):
    """运行 Agent 处理任务"""
    try:
        from google.adk.runners import Runner
        from google.adk.agents import RunConfig
        from google.adk.agents.run_config import StreamingMode
    except ImportError:
        logger.error("请先安装 google-adk")
        return

    global my_agent, compactor_agent, session_service
    
    if my_agent is None:
        create_agent()

    # 创建 Runner (注意需要 app_name)
    runner = Runner(agent=my_agent, app_name=DEFAULT_APP_NAME, session_service=session_service)

    # 确保 session 存在
    try:
        session = await session_service.get_session(
            app_name=DEFAULT_APP_NAME,
            user_id=DEFAULT_USER_ID,
            session_id=DEFAULT_SESSION_ID
        )
        if session is None:
            session = await session_service.create_session(
                app_name=DEFAULT_APP_NAME,
                user_id=DEFAULT_USER_ID,
                session_id=DEFAULT_SESSION_ID
            )
        turn_count = len(session.events) if session and hasattr(session, 'events') and session.events else 0
        tool_count = len(my_agent.tools) if my_agent.tools else 0
        
        # 阈值检查与自动截断
        # 假设每轮对话约产生 4 个 event (User + Model + ToolCall + ToolOutput)
        WARN_TURNS = 20   # 软阈值 (~10轮对话)：提醒用户/Agent 执行压缩
        MAX_TURNS = 20    # 硬阈值 (~20轮对话)：强制截断，最后防线
        #KEEP_TURNS = 60   # 截断后保留 (~15轮对话)
        
        # 软阈值：提醒压缩
        if turn_count > WARN_TURNS and turn_count <= MAX_TURNS:
            print(f"\n[提醒] event个数 ({turn_count}) 超过软阈值 {WARN_TURNS}，建议执行 smart_compact 压缩上下文")
        
        # 在执行新回复前先检查是否需要自动压缩并按需执行
        # 硬阈值：强制截断 (System-Level Auto-Compaction)
        if turn_count > MAX_TURNS:
            print(f"\n[警告] event个数 ({turn_count}) 超过硬阈值 {MAX_TURNS}，正在执行自动压缩...")
            
            try:
                # 1. 格式化历史记录
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
                if compactor_agent:
                    print("[系统] 正在调用 AutoCompactAgent 生成摘要...")
                    summary = await compactor_agent.compact_history(history_text)
                    print(f"[系统] 摘要生成成功: {summary}")
                else:
                    print("[错误] compactor_agent 未初始化")

                # 3. 执行截断 (复用 smart_compact 逻辑)
                # 需要导入 _smart_compact，由于路径问题，这里直接使用 inline 逻辑或尝试导入
                # 为了保持一致性，我们使用 tools.py 中的 _smart_compact
                # 注意：需要处理导入路径
                try:
                    # 尝试动态导入以适应不同运行环境
                    import importlib
                    # 假设 tools.py 在 skills.adk_agent.claude.skills.compactor 包下
                    # 但由于目录结构复杂 (.claude)，直接导入可能困难。
                    # 既然我们已经在 main.py 中，我们可以直接操作 session.events
                    
                    # --- Inline Smart Compact Logic (Reused) ---
                    print(f"[系统] 执行 Hard Reset，保留摘要...")
                    
                    # 3.1 收集 System 消息
                    system_events = []
                    for evt in session.events:
                        role = 'unknown'
                        if hasattr(evt, 'content') and evt.content and hasattr(evt.content, 'role'):
                            role = evt.content.role
                        if role == 'system':
                            system_events.append(evt)
                        else:
                            break
                    
                    # 3.2 构造占位符 User 消息 (包含摘要)
                    import copy
                    placeholder_user_evt = None
                    if session.events:
                        # 克隆第一个事件作为模板
                        template_evt = session.events[0]
                        placeholder_user_evt = copy.deepcopy(template_evt)
                        
                        # 设置为 User 角色
                        if hasattr(placeholder_user_evt, 'content'):
                            placeholder_user_evt.content.role = 'user'
                            # 设置摘要内容
                            # from google.genai import types (Already imported globally)
                            placeholder_user_evt.content.parts = [types.Part(text=f"[System] Context cleared. Summary of previous conversation:\n{summary}")]
                    
                    if placeholder_user_evt:
                        # 3.3 重组事件: System + Placeholder
                        # 注意：这里我们不保留 "Current Tool Call"，因为这是在 run_agent 循环外部发生的
                        # 这是一个 "Between Turns" 的截断，所以不需要保留正在进行的 Tool Call
                        new_events = system_events + [placeholder_user_evt]
                        
                        # 无效的修复，无法真正有效改动events内容，原因是deepcopy ，有效修复见Line380
                        # [Fix] In-place update to ensure persistence if Runner holds reference
                        if hasattr(session.events, 'clear') and hasattr(session.events, 'extend'):
                            session.events.clear()
                            session.events.extend(new_events)
                        else:
                            # Fallback for lists that don't support clear/extend
                            session.events[:] = new_events
                        
                        new_count = len(session.events)
                        
                        # Calculate total text length
                        new_text_len = 0
                        for evt in session.events:
                            if hasattr(evt, 'content') and hasattr(evt.content, 'parts'):
                                for part in evt.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        new_text_len += len(part.text)
                        
                        print(f"[OK] 自动压缩完成。当前事件数: {new_count}, 文本长度: {new_text_len}")
                        
                        # 有效的修复 解决了session中events内容的改动
                        # [Critical Fix] InMemorySessionService returns a deepcopy, so we MUST update the internal storage
                        from google.adk.sessions import InMemorySessionService
                        if isinstance(session_service, InMemorySessionService):
                            try:
                                if (DEFAULT_APP_NAME in session_service.sessions and 
                                    DEFAULT_USER_ID in session_service.sessions[DEFAULT_APP_NAME] and 
                                    DEFAULT_SESSION_ID in session_service.sessions[DEFAULT_APP_NAME][DEFAULT_USER_ID]):
                                    
                                    stored_session = session_service.sessions[DEFAULT_APP_NAME][DEFAULT_USER_ID][DEFAULT_SESSION_ID]
                                    # Update events
                                    if hasattr(stored_session.events, 'clear') and hasattr(stored_session.events, 'extend'):
                                        stored_session.events.clear()
                                        stored_session.events.extend(new_events)
                                    else:
                                        stored_session.events[:] = new_events
                                    print("[系统] 已强制同步会话状态到存储")
                            except Exception as e:
                                print(f"[警告] 强制同步会话失败: {e}")
                            
                        turn_count = new_count # 更新计数
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
                
        if tool_count > 12:
            print(f"\n[提醒] 已加载工具较多 ({tool_count})，建议卸载不常用的 skill")
    except Exception:
        # 首次运行时 session 可能不存在，创建一个新的
        session = await session_service.create_session(
            app_name=DEFAULT_APP_NAME,
            user_id=DEFAULT_USER_ID,
            session_id=DEFAULT_SESSION_ID
        )
    
    # 软阈值：提醒压缩 (注入到 Prompt 中)
    if turn_count > WARN_TURNS and turn_count <= MAX_TURNS:
        print(f"\n[提醒] event个数 ({turn_count}) 超过软阈值 {WARN_TURNS}，已注入压缩指令")
        task += "\n\n[System Note] Context is getting long (events > 40). Please call 'smart_compact' tool to summarize history and free up space."

    logger.task_start(task)
    print(f"\n[任务] {task}")
    print("-" * 60)

    # 定义用户输入 (使用 types.Content 格式)
    user_query = types.Content(role='user', parts=[types.Part(text=task)])
    
    # 配置流式输出
    run_config = RunConfig(
        streaming_mode=StreamingMode.SSE,
    )
    full_final_result_list = []  #传入到_process_event的full_final_result_list 用于拼接
    try:
        async for event in runner.run_async(
            user_id=DEFAULT_USER_ID,
            session_id=DEFAULT_SESSION_ID,
            new_message=user_query,
            run_config=run_config
        ):
            _process_event(event, full_final_result_list)
    except Exception as e:
        logger.error(f"执行出错: {e}")
        print(f"\n[ERROR] 执行出错: {e}")

    #
    print(f'[拼接所得到的full_final_result]\n{"".join(full_final_result_list)}')
    
    ## [可选] 在 runner 完成处理所有事件之后检查会话事件event。
    #  能看出手动压缩和自动压缩的效果 就是events数量减少了
    updated_session = await session_service.get_session(app_name=DEFAULT_APP_NAME, user_id=DEFAULT_USER_ID, session_id=DEFAULT_SESSION_ID)
    #print(f"\nAgent 运行后的事件：{updated_session.events}")   
    print("\n\n***打印session events***\n===Session History Start===")
    for event in updated_session.events:
        if event.content and event.content.parts:
            print(f"<{event.author}>: {event.content.parts}")
            print('=='*10 + '\n')
    print("===Session History End===")

    ## [可选] 在 runner 完成处理所有事件之后检查会话状态state。
    print(f"\nAgent 运行后的状态 注意output_key是智能体定义设置的,用户agent之间的传参：{updated_session.state}") 


def _process_event(event, full_final_result_list):
    # 定义full_final_result 参考 simple_agent.py 的Line236 ，该full_final_result由选择性拼接获取
    # full_final_result_list 传入一个[] 可以变 所以收集了所需的text 之后在 调用_process_event的循环外拼接得到 full_final_result
    """处理 Agent 事件 凡是streaming标记的消息都可以作为流式输出响应"""
    if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts'):
        for part in event.content.parts:
            # 处理思考内容
            # 修复重复输出：只有非最终响应才输出思考过程
            if not event.is_final_response() and hasattr(part, 'text') and part.text:
                text = part.text
                logger.thought(text)
                print(f"[streaming] {text}")
                full_final_result_list.append(text)
            
            # 处理工具调用
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                logger.tool_call(fc.name, dict(fc.args) if hasattr(fc, 'args') else {})
                fc_tool_call_msg= f"[streaming_工具调用] {fc.name} 输入参数: {fc.args}"
                print(fc_tool_call_msg)
                full_final_result_list.append(fc_tool_call_msg)

            # 处理工具调用结果 
            if hasattr(part, 'function_response') and part.function_response:
                fr = part.function_response
                # logger.tool_output(fr.name, fr.response) 
                fc_tool_response_msg= f"[streaming_工具调用结果] {fr.name} -> {fr.response}"
                print(fc_tool_response_msg)
                full_final_result_list.append(fc_tool_response_msg)

    # 最终响应 这个响应中能看到本次会话使用的token 
    # prompt_token_count=6203,total_token_count=6467
    # 也能看出来手动压缩和自动压缩后的 token减少的效果
    # 这个用于传递给其他agent
    if hasattr(event, 'is_final_response') and event.is_final_response():
        if event.content and event.content.parts:
            print('\n*************')
            print(f'\n[event中根据is_final_response获取完整响应]\n{event}')
            final_text = event.content.parts[0].text
            logger.task_complete(final_text)
            print(f"\n{'='*60}")
            print(f"[event中根据is_final_response获取完整响应text]\n{final_text}")
    
    


async def interactive_mode():
    """交互式模式"""
    print("\n" + "=" * 60)
    print("ADK 动态技能智能体 - 交互模式")
    print("=" * 60)
    print("命令:")
    print("  skills    - 查看可用技能")
    print("  tools     - 查看已加载的工具")
    print("  reset     - 重置 Agent 状态")
    print("  verbose   - 切换详细输出")
    print("  quit/exit - 退出")
    print("-" * 60)

    create_agent()

    while True:
        try:
            user_input = input("\n你: ").strip()
            
            if not user_input:
                continue
            
            # 处理命令
            cmd = user_input.lower()
            if cmd in ['quit', 'exit', 'q']:
                print("再见!")
                break
            if cmd == 'skills':
                print("\n[技能列表] 可用技能:")
                print(sm.get_discovery_manifests())
                continue
            if cmd == 'tools':
                print("\n[工具列表] 已加载工具:")
                for t in my_agent.tools:
                    name = t.__name__ if hasattr(t, '__name__') else str(t)
                    doc = (t.__doc__ or "").split('\n')[0]
                    print(f"  - {name}: {doc}")
                continue
            if cmd == 'reset':
                await skill_load("compactor")
                print("[OK] 已重置")
                continue
            if cmd == 'verbose':
                config.verbose = not config.verbose
                print(f"详细输出: {'开启' if config.verbose else '关闭'}")
                continue

            await run_agent(user_input)
            
        except KeyboardInterrupt:
            print("\n再见!")
            break
        except Exception as e:
            logger.error(str(e))
            print(f"[ERROR] 错误: {e}")


async def main():
    """主函数"""
    setup_env()
    
    # 默认任务演示
    demo_task = "分析 data.csv 里的 sales_val 平均值"
    await run_agent(demo_task)


if __name__ == "__main__":
    # 检查命令行参数
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ["-i", "--interactive"]:
            asyncio.run(interactive_mode())
        elif arg in ["-h", "--help"]:
            print("""
ADK Dynamic Skills Agent

用法:
  python main.py                    # 运行演示任务
  python main.py -i                 # 交互模式
  python main.py "你的任务描述"     # 执行指定任务

环境变量:
  GOOGLE_API_KEY                    # Google AI API Key
            """)
        else:
            task = " ".join(sys.argv[1:])
            asyncio.run(run_agent(task))
    else:
        asyncio.run(main())
