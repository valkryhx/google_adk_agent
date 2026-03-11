import asyncio
import traceback
from typing import List
from opencode_ai import Opencode

import os

def get_opencode_config() -> dict:
    """动态读取 OpenCode 服务的本地配置（支持热加载），无需重启且不依赖第三方库"""
    config_path = os.path.join(os.path.dirname(__file__), "opencode_service.yaml")
    config = {
        "url": "http://127.0.0.1:4096",
        "provider": None,
        "model": None
    }
    
    if not os.path.exists(config_path):
        return config
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                    
                if line.startswith("opencode_base_url:"):
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        val = parts[1].strip().strip("\"'")
                        if val:
                            config["url"] = val
                elif line.startswith("opencode_provider:"):
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        val = parts[1].strip().strip("\"'")
                        if val:
                            config["provider"] = val
                elif line.startswith("opencode_model:"):
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        val = parts[1].strip().strip("\"'")
                        if val:
                            config["model"] = val
    except Exception as e:
        print(f"[{__name__}] Warning: Failed to parse yaml, error: {e}")
        
    return config

def get_default_provider_and_model(base_url: str):
    """动态获取 OpenCode 服务当前连接的 provider 和默认模型"""
    try:
        import urllib.request, json
        req = urllib.request.Request(f"{base_url.rstrip('/')}/provider")
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            connected = data.get('connected', [])
            defaults = data.get('default', {})
            
            # 优先使用特定的几个好用的 Provider
            for choice in ['opencode', 'local-deepseek', 'google', 'anthropic', 'openai']:
                if choice in connected and choice in defaults:
                    return choice, defaults[choice]
            
            if connected:
                provider = connected[0]
                return provider, defaults.get(provider, "")
    except Exception as e:
        print(f"[{__name__}] Warning: Failed to fetch providers: {e}")
    
    # 彻底 fallback
    return "opencode", "big-pickle"

def get_tools(*args, **kwargs) -> List:
    """
    动态加载 OpenCode 技能。
    利用 kwargs 捕获从 main_web_start_steering 注入的并发安全上下文。
    """
    status_reporter = kwargs.get('status_reporter')
    interruption_queue = kwargs.get('interruption_queue')

    async def opencode_delegate(prompt: str) -> str:
        """
        [opencode-Agent] 专门处理复杂编码、多文件重构、环境配置和终端命令的底层智能体。
        
        使用场景：
        1. 当你需要执行需要反复试错的复杂代码任务（如安装依赖并修复报错）时。
        2. 当任务跨越多个文件，且你需要一个能自主运行 bash 命令并测试结果的助手时。
        
        注意：
        请在 prompt 中极其详尽地描述任务背景、目标路径和具体要求。不要将此工具用于简单的单文件查看（请优先使用 file_editor）。
        
        Args:
            prompt: 给 OpenCode 智能体的详细任务指令集。
        """
        # 1. 中断防御检查
        if interruption_queue and not interruption_queue.empty():
            return "任务尚未开始即被用户中断。"

        try:
            # 每次被大模型调用时，动态读取最新的 yaml 配置（热加载）
            config = get_opencode_config()
            opencode_base_url = config.get("url", "http://127.0.0.1:4096")
            provider_id = config.get("provider")
            model_id = config.get("model")
            
            print(f"[DEBUG] Raw config from yaml - provider: {provider_id}, model: {model_id}")
            
            if not provider_id or not model_id:
                print("[DEBUG] Provider/Model not fully set, entering fallback discovery...")
                fallback_provider, fallback_model = get_default_provider_and_model(opencode_base_url)
                provider_id = provider_id or fallback_provider
                model_id = model_id or fallback_model
                
            print(f"[OpenCode] 🚀 初始化会话 | Provider: {provider_id} | Model: {model_id}")

            client = Opencode(base_url=opencode_base_url)
            # 为当前任务创建一个隔离的沙盒 Session
            # 经过观察发现，在 create 时强制传 extra_body 的 provider/model 可能会干扰后续 chat 调用
            # 我们先创建一个干净的 session，然后在 chat 时指定引擎
            session = client.session.create(extra_body={})
            print(f"[DEBUG] Session created: {session.id}")
        except Exception as e:
            return f"[异常] 无法连接到 OpenCode 服务，请检查端口 {opencode_base_url} 或 API 状态。错误: {e}"

        if status_reporter:
            # 初始化前端卡片
            status_reporter("init", {
                "task_preview": "正在唤醒 OpenCode 底层代码智能体...",
                "worker_port": "opencode",
                "session_id": session.id,
                "deep_think_role": "OpenCode-Agent"
            })
            # 给出一条初始的 chunk 让界面显示轨迹头
            status_reporter("chunk", {"content": f"[OpenCode 运行轨迹]\n\n", "worker_port": "opencode", "session_id": session.id})
            
        def background_opencode_task():
            try:
                import threading
                is_finished = threading.Event()
                
                def event_listener():
                    try:
                        accumulated_text = ""
                        for event in client.event.list():
                            if is_finished.is_set():
                                break
                            
                            # 执行期实时中断检查
                            if interruption_queue and not interruption_queue.empty():
                                if status_reporter:
                                    status_reporter("fail", {"error": "强制中断了 OpenCode 执行", "worker_port": "opencode", "session_id": session.id})
                                break

                            if hasattr(event, "properties"):
                                event_session_id = getattr(event.properties, "session_id", None)
                                # [BUG FIX] 经过排查发现由于某些 SDK 或模型 (比如 jiutian 和 qwen3.5)，它的 Server-Sent Event 并不会透传所属的 session_id（始终为 None）
                                # 因此，强制校验 session_id == session.id 会导致所有内容被拦截。我们放宽这个限制，允许 session_id 为 None 的事件。
                                if event_session_id == session.id or event_session_id is None:
                                    if "message" in event.type or "session" in event.type:
                                        try:
                                            props_dict = vars(event.properties) if hasattr(event.properties, "__dict__") else dir(event.properties)
                                            print(f"[EVENT DEBUG] {event.type} -> {props_dict}")
                                        except Exception as e:
                                            print(f"[EVENT DEBUG] {event.type} EXCEPTION: {e}")
                                            
                                    # 处理各种流事件：qwen 返回 message.part.delta，jiutian 等返回 message.part.updated
                                    if event.type in ["message.part.delta", "message.part.updated", "message.updated"]:
                                        txt = ""
                                        if event.type == "message.part.delta":
                                            txt = getattr(event.properties, "delta", "")
                                        elif event.type == "message.part.updated" or event.type == "message.updated":
                                            # 处理其它变种事件，这里可能藏在 message.text 或者 part.text 中，试着拿 message 或者 part
                                            part_obj = getattr(event.properties, "part", None)
                                            if part_obj and hasattr(part_obj, "text"):
                                                new_text = getattr(part_obj, "text", "")
                                                # 取增量
                                                if len(new_text) > len(accumulated_text):
                                                    txt = new_text[len(accumulated_text):]
                                        
                                        if isinstance(txt, str) and txt:
                                            accumulated_text += txt
                                            print(f"[OpenCode Stream] {txt}")
                                            if status_reporter:
                                                status_reporter("chunk", {"content": accumulated_text, "worker_port": "opencode", "session_id": session.id})
                                    elif event.type == "session.error":
                                        err = getattr(event.properties, "error", "Unknown error")
                                        if status_reporter:
                                            status_reporter("chunk", {"content": f"[底层报错]: {err}\n", "worker_port": "opencode", "session_id": session.id})
                    except Exception as e:
                        print(f"[OpenCode Stream Exception] {e}")
                        import traceback
                        traceback.print_exc()
                        if status_reporter:
                            status_reporter("chunk", {"content": f"[底层流监听警告]: {e}\n", "worker_port": "opencode", "session_id": session.id})
                listener_thread = threading.Thread(target=event_listener, daemon=True)
                listener_thread.start()

                # 开启官方 SDK 的请求（挂起直到执行完毕）
                print(f"[DEBUG] Calling client.session.chat for session {session.id}")
                response = client.session.chat(
                    id=session.id,
                    provider_id=provider_id,
                    model_id=model_id,
                    parts=[{"type": "text", "text": prompt}]
                )
                
                is_finished.set()

                # 构建最终结果
                final_output = []
                if hasattr(response, "parts"):
                    for part in response.parts:
                        if getattr(part, "type", "") == "text":
                            final_output.append(f"\n\n[最终回复]:\n{getattr(part, 'text', '')}\n")
                        elif getattr(part, "type", "") == "tool-call":
                            tool_name = getattr(part, "tool_name", "unknown")
                            final_output.append(f"\n[动作]: 调用 {tool_name}\n")

                if status_reporter:
                    # 结束时发送最终结果
                    status_reporter("chunk", {"content": "".join(final_output), "worker_port": "opencode", "session_id": session.id})
                    # 变绿
                    status_reporter("finish", {"message": "OpenCode 任务执行完毕。", "worker_port": "opencode", "session_id": session.id})
                    
            except Exception as e:
                err_msg = f"OpenCode 执行期间发生后台崩溃: {str(e)}\n{traceback.format_exc()}"
                if status_reporter:
                    status_reporter("fail", {"error": err_msg, "worker_port": "opencode", "session_id": session.id})
                    
        # 直接同步执行任务（ADK 框架会在独立线程执行同步工具，所以不会阻塞底层 asyncio 事件循环）
        # [Fix]: opencode_delegate 是 async def，如果直接调用会阻塞主事件循环，必须使用 to_thread
        try:
            import asyncio
            await asyncio.to_thread(background_opencode_task)
            return f"[执行完毕] OpenCode 任务已处理完毕：\n{prompt[:100]}...\n执行过程已从前端 UI 呈现。"
        except Exception as e:
            return f"[执行异常] OpenCode 任务处理失败：{str(e)}"

    # 显式重置函数名（防止闭包导致某些底层 Agent 框架反射获取 Tool Name 失败）
    opencode_delegate.__name__ = "opencode_delegate"

    return [opencode_delegate]
