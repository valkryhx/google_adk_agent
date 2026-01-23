from google.adk.models.lite_llm import LiteLlm
from google.adk.agents import LlmAgent,RunConfig
from google.adk.agents.run_config import StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search
from google.genai import types
import nest_asyncio
import asyncio
import datetime
import json
import re
import traceback
from urllib.parse import urlparse
import uuid
from google.adk.events.event import Event
# mcp tool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

# planner
from google.adk.planners import PlanReActPlanner



#=============一些技巧================
# 一些技巧
# output_key 指定agent的输出key 会带入到session.state字典
# 参考 https://adp.xindoo.xyz/chapters/Chapter%208_%20Memory%20Management/ 
# 简单方法：使用 output_key（用于 Agent 文本回复）： 如果您只想将 Agent 的最终文本响应直接保存到状态中，这是最简单的方法。
# 也可以是agents 之间IO传递 的办法 https://www.zhihu.com/question/1895048274970378499/answer/1911211065997492722

# 工具调用信息 event 加入 session的events
# 参考 https://github.com/google/adk-python/discussions/3300

# agent定义时的可选 参数
# https://google.github.io/adk-docs/agents/llm-agents/
# 注意 include_contents = 'none' 时 ,智能体就不会读取历史对话而是一个专门处理当前输入的无状态智能体 也有作用

#===============一些技巧 End=====================


#  简单智能体 使用 简单工具 和 参数 mcp tool 来为用户提供帮助
#  先从参数mcp 项目启动容器服务和mock service ，然后执行本测试 python -m  src.simple_agent

## 定义google adk 会话和 Agent 执行所需的变量
APP_NAME="hello_world_agent"
USER_ID="user1234"
SESSION_ID="1234"


# ==============================litellm 定义 注意关闭thinking =========================================
# 定义qwenmodel 注意 openai/ 前缀 是为了使用兼容性 (OpenAI Compatibility)
# 使用 OpenAI 的标准 API 格式（输入输出结构）来与这个LLM服务进行

# 外网的qwen LLM
DASHSCOPE_API_KEY = "YOUR_API_KEY"
qwen_model = LiteLlm(
    # 使用通义千问模型,或者使用 litellm支持的vllm前缀也行，model="hosted_vllm/qwen2.5-72b-instruct",
    #model="openai/qwen2.5-72b-instruct",
    
    # 使用通义千问模型,或者使用 litellm支持的vllm前缀也行，model="hosted_vllm/qwen3-32b",
    model="openai/qwen3-32b", 
    api_key=DASHSCOPE_API_KEY,
    api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",

    # 关闭thinking 不然输出内容带有思考内容，过于啰嗦，而且json解析会失败
    # 关闭qwen thinking 有三种方式 参考python示例代码 
    # https://help.aliyun.com/zh/model-studio/deep-thinking?spm=a2c4g.11186623.0.0.5c9869d0OtEP16#24e692e05a220
    
    # [关闭思考的方式1] 对于可以思考和不能思考的model都可配置
    extra_body={"enable_thinking": False },
    # [关闭思考的方式2] 对于可以思考和不能思考的model都可配置 
    #enable_thinking=False,
    # [关闭思考的方式3 无效] extra_body={"chat_template_kwargs":  {"enable_thinking": False} } 对于具有思考和不能思考的model都可配置
    #extra_body={"chat_template_kwargs":  {"enable_thinking": False} },
    
    # litellm 流式输出，这里不用设置 因为流式输出在后续agent代码的run_config中设置
    #stream=True   
    )

# 内网LLM服务  服务经常g
# ONE_API_KEY = "YOUR_API_KEY"
# qwen_model = LiteLlm(
#     model="openai/Qwen3-32B", # 使用设计院内网的通义千问模型
#     api_key=ONE_API_KEY,
#     api_base="http://172.21.111.30:3006/v1",
#     extra_body={"enable_thinking": False },  # 关闭thinking
#     )



# ===================  简单tool 定义 ======================== 
# 用于智能体演示的简单tool-解析llm输出的json```content``` 
def parse_llm_json(text):
    """
    从 LLM 响应中提取并解析 JSON。
    支持处理 ```json ... ``` 包裹的情况。
    """
    if not text:
        return None

    # 1. 尝试使用正则表达式提取代码块中的内容
    # 匹配 ```json 或 ``` 开头，到 ``` 结尾的内容
    # re.DOTALL 让 . 也能匹配换行符
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    
    if match:
        json_str = match.group(1)
    else:
        # 2. 如果没有代码块标记，尝试直接在文本中寻找第一个 { 和最后一个 }
        # 这对于混合了普通文本和JSON的响应也有效
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            json_str = text[start:end+1]
        else:
            # 3. 实在找不到，就假设整个文本就是 JSON
            json_str = text.strip()
            
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
        # 打印出尝试解析的字符串，方便调试
        print(f"尝试解析的内容: {json_str}")
        return None


# 用于智能体演示的简单工具-获取当前时间
def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")




## ==================== Agent + 定义mcp tool + 加载各类tool+ 调用agent主程序 ==========================

async def call_agent(query):
    """
    定义mcptoolset ,先检查mcp server是否启动再连接mcp定义agent的mcptool
    """

    #  参数 mcp tools
    http_mcp_toolset = None
    mcp_url = "http://localhost:9014/mcp"

    try:
        # 1. TCP 预检：尝试建立 TCP 连接，避免直接初始化 McpToolset 导致的资源泄露 bug
        parsed = urlparse(mcp_url)
        # 尝试连接 host:port，超时20秒
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(parsed.hostname, parsed.port), 
            timeout=20.0
        )
        writer.close()
        await writer.wait_closed()
        
        # 2. 只有 TCP 通了才初始化 Toolset
        http_mcp_toolset = McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=mcp_url
            )
        )
        # [可选] 仍然保留 通过get_tools获取tools的验证 以防万一
        await asyncio.wait_for(http_mcp_toolset.get_tools(), timeout=20.0)

    except Exception:
        print(f"MCP 服务未启动或无法连接 (TCP check failed)，将使用占位工具。")
        # 如果已经初始化了 toolset 但后续失败了，尝试关闭
        if http_mcp_toolset and isinstance(http_mcp_toolset, McpToolset):
            try:
                await http_mcp_toolset.close()
            except:
                pass
        # 定义用于占位的mcp tool，兼容后续agent的tools的列表定义      
        async def http_mcp_toolset():
            """MCP 工具集不可用（服务可能未启动）"""
            return "MCP 工具集当前不可用，请检查服务是否启动。"

    ## 定义 Agent  以及tools 包括简单工具 和 参数 mcptoolset
    root_agent = LlmAgent(
    name="basic_agent",
    model=qwen_model,
    description="示例智能体",
    
    # instruction 是写提示词的位置 这个例子中什么提示词都没写 效果就已经可以了
    instruction="根据用户提问自行决定使用工具解决问题",
    #tools=[google_search] # Google 搜索是执行 Google 搜索的预构建工具。没有google search apikey就不要用了
    # 注意这里tools 包含简单工具和 mcptoolset
    tools =[get_current_time, parse_llm_json,http_mcp_toolset],
    # output_key 指定agent的输出key 会带入到session.state字典
    # 参考 https://adp.xindoo.xyz/chapters/Chapter%208_%20Memory%20Management/ 
    # 简单方法：使用 output_key（用于 Agent 文本回复）： 如果您只想将 Agent 的最终文本响应直接保存到状态中，这是最简单的方法。
    # 也可以是agents 之间IO传递 的办法 https://www.zhihu.com/question/1895048274970378499/answer/1911211065997492722
    output_key="hello_world_agent_output",

    # 可选 配置后会观察到 agent的 PLANNING-ACTION-FIANL_ANSWER 过程
    # 但是目前在最终的输出中有bug ，参见 https://github.com/google/adk-python/issues/3697
    # planner=PlanReActPlanner() ,

    # 可选 设置为 none 则不读取历史信息专注于本次任务 避免注意力分散
    include_contents='none' ,
    )

    # full_final_result 用于记录最终的完整结果 
    full_final_result=""
    # 会话和运行器runner
    session_service = InMemorySessionService()
    # session 变量必须定义 否则报错
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    
    # runner.run / runner.run_async 
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
    
    #定义用户输入
    user_query = types.Content(role='user', parts=[types.Part(text=query)])
    
    # agent设置流式输出
    stream = True
    run_config = RunConfig(
        streaming_mode=StreamingMode.NONE if not stream else StreamingMode.SSE,
    )
    
    # agent 输出的过程 注意学习
    try:
        async for event in runner.run_async(
                user_id=USER_ID,
                session_id=SESSION_ID,
                new_message=user_query,
                run_config=run_config
                ):

            # 检查和学习event内容则可以打印 event 中的content 对于tool/code/text 等 格式不同   
            #print(event)
            # 获取 工具调用结果 并实时输出 和 拼接 到 full_final_result
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call:
                        msg = f"[工具调用] {part.function_call.name} 输入参数: {part.function_call.args}"
                        #print(msg)
                        print("[streaming]",msg, end="\n", flush=True)
                        full_final_result += "\n" + msg + "\n"

                        # 工具调用信息 event 加入 session的events 实际上不用加 看Line292行附近的events 执行打印查看内容就能知道 tool call的调用和结果 agent的events都已经存在
                        # 参考 https://github.com/google/adk-python/discussions/3300
                        # 打印session events 从events看出 每个工具调用都有function_call/function_response 不需要手动加text格式的工具调用信息
                        # tool_event = Event(
                        #     invocation_id=str(uuid.uuid4()),
                        #     author="my_tool_call",
                        #     content=types.Content(parts=[types.Part(text=msg)])
                        # )
                        # await session_service.append_event(session, tool_event)

                    if part.function_response:
                        msg = f"[工具调用] {part.function_response.name} 输出结果: {part.function_response.response}"
                        #print(msg)
                        print("[streaming]",msg, end="\n", flush=True)
                        full_final_result += msg + "\n"

                        # Add tool response info as event to session
                        #打印session events 从events看出 每个工具调用都有function_call/function_response 不需要手动加text格式的工具调用信息
                        # tool_event = Event(
                        #     invocation_id=str(uuid.uuid4()),
                        #     author="my_tool_response",
                        #     content=types.Content(parts=[types.Part(text=msg)])
                        # )
                        # await session_service.append_event(session, tool_event)

            # 通过event.is_final_response() 来控制流式输出 避免最终的event重复输出
            # not event.is_final_response() 避免将最终的完整结果输出 因为流式输出每次只输出增量 例如可以 拼接 delta_text 来组成full_final_result
            if not event.is_final_response() and  event.content and event.content.parts and event.content.parts[0].text:
                print("[streaming]",event.content.parts[0].text, end="\n", flush=True)
                #方法1 建议使用 因为实时流式输出和最终的内容都可以支持: full_final_result 通过拼接来获取，以便提供给下一个智能体
                full_final_result += event.content.parts[0].text
            # event.is_final_response()检查是否是完整的输出 这个event的内容是完整的输出内容， 不需要拼接就可用于最终展示，以及提供给下一个流程函数或者智能体使用
            # if event.is_final_response():
            #     final_response = event.content.parts[0].text
            #     print("[Agent final 完整响应]:\n", final_response)
            #     #方法2: full_final_result 也可直接用这个final_response来赋值，可以直接给下一个智能体使用，但是无法实时流式输出
            #     full_final_result = final_response
    finally:
        # 显式关闭 MCP 连接，避免 RuntimeError
        #print("\n[System] Closing MCP connection...")
        if isinstance(http_mcp_toolset, McpToolset):
            await http_mcp_toolset.close()
            
    ## [可选] 在 runner 完成处理所有事件之后检查会话状态state。
    updated_session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    print(f"\nAgent 运行后的状态 注意output key是智能体定义设置的：{updated_session.state}")   

    ## [可选] 在 runner 完成处理所有事件之后检查会话事件event。
    # 打印session events 从events看出 每个工具调用都有function_call/function_response 不需要手动加text格式的工具调用信息
    updated_session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    #print(f"\nAgent 运行后的事件：{updated_session.events}")   
    print("\n打印session events 从events看出 每个工具调用都有function_call/function_response 不需要手动加text格式的工具调用信息\n===Session History Start===")
    for event in updated_session.events:
        if event.content and event.content.parts:
            #print(f"<{event.author}>: {event.content.parts[0].text}")
            print(f"<{event.author}>: {event.content.parts}")
    print("===Session History End===")
    
    return full_final_result

#nest_asyncio.apply [只在Jupyter Notebook运行才需要]防御性编程的措施，确保脚本不仅能在终端直接运行（python src/simple_agent.py）
# 也能方便地在 Jupyter Notebook 或调试控制台中直接执行。
# 但是nest_asyncio 主要用于 Jupyter Notebook 环境（那里 Loop 已经在运行）。在脚本中使用它会干扰 anyio（HTTP 库）对任务取消范围（Cancel Scope）的管理，导致 RuntimeError: Attempted to exit cancel scope...。
#nest_asyncio.apply()



# ================================测试 agent =========================================
# run agent 调用tool 以及agent自动的工具混合使用
# 1.简单工具
res=asyncio.run(call_agent("当前时间是？请使用json格式获取YYYY-MM-DD HH:MM:SS格式的当前时间:json```{{mytime：current_time}}``` 并使用时间抽取工具提取结果"))

# 2.mcp工具(查工单对应的参数修改记录)  + 获取当前时间  ，此时期望调用两次tool
#res=asyncio.run(call_agent("查看HN-HN-20251222-1627工单的参数修改记录，并获取当前时间"))

# 3.mcp工具(生成参数修改草稿) 注意启动mcp项目中的 python -m utils.mock_param_service
#res = asyncio.run(call_agent("生成参数修改草稿: 460-00-538402-107 参数组为M10 4-5迟滞修改为-11"))

# 4.mcp工具(生成工单)  注意启动mcp项目中的 python -m utils.mock_param_service
# create_order_info={
#                 "city": "娄底",
#                 "vendor": "华为",
#                 "net_type": "LTE",
#                 "param_level": "小区级",
#                 "ne_name": "460-00-538402-107",
#                 "param_object": "CELLSEL",
#                 "param_name": "QRxLevMin",
#                 "param_group_id_name": "无",
#                 "param_group_id_value": "N10",
#                 "new_value": "-110",
#                 "current_value": "",
#                 "end_time": "当前时间的一天之后",   # 注意这里会调用简单工具get current time并计算一天之后的时间
#                 "start_time": "2025年12月24号12点23分" #注意这里会利用llm自己的能力翻译成 mcp tool定义中所需的格式
#             }
# res=asyncio.run(call_agent(f"生成工单，参数如下:{create_order_info} ,时间相关的信息通过时间工具获取"))



print("\n[Agent final 完整响应]:\n", res)




