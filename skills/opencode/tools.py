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
            # [Fix] 作用域提升：将轨迹内容存入 context 字典，以便主线程在任务结束后能获取并合并结果
            shared_context = {"accumulated_text": "[OpenCode 运行轨迹]\n\n"}
            
            try:
                import threading
                is_finished = threading.Event()
                
                def get_attr_robust(obj, attr, default=None):
                    """鲁棒地获取属性：支持对象属性访问、字典访问和 Vars 访问"""
                    if obj is None: return default
                    # 1. 直接属性访问
                    if hasattr(obj, attr):
                        return getattr(obj, attr, default)
                    # 2. 字典访问 (如果 obj 是 dict)
                    if isinstance(obj, dict):
                        return obj.get(attr, default)
                    # 3. 字典访问 (如果 obj 内部有 __dict__)
                    if hasattr(obj, "__dict__"):
                        return obj.__dict__.get(attr, default)
                    return default

                def event_listener():
                    try:
                        # [Fix] 维护各 part 的已知长度，以精确计算 updated 事件的增量
                        part_lengths = {}
                        
                        for event in client.event.list():
                            if is_finished.is_set():
                                break
                            
                            # 执行期实时中断检查
                            if interruption_queue and not interruption_queue.empty():
                                if status_reporter:
                                    status_reporter("fail", {"error": "强制中断了 OpenCode 执行", "worker_port": "opencode", "session_id": session.id})
                                break

                            props = getattr(event, "properties", None)
                            if props:
                                event_session_id = get_attr_robust(props, "session_id")
                                # [BUG FIX] 允许 session_id 为 None 的事件透传 (针对 jiutian/qwen 等引擎)
                                if event_session_id == session.id or event_session_id is None:
                                    delta_text = ""
                                    part_id = get_attr_robust(props, "part_id", "default")
                                    event_type = getattr(event, "type", "")
                                    
                                    # 1. 处理流增量事件 (delta)
                                    if event_type == "message.part.delta":
                                        delta_text = get_attr_robust(props, "delta", "")
                                        
                                    # 2. 处理全量更新事件 (updated)
                                    elif "updated" in event_type:
                                        part_obj = get_attr_robust(props, "part")
                                        if part_obj:
                                            # 捕获 text (回复), thought (思考过程), content (某些模型的字段)
                                            for field in ["text", "thought", "content"]:
                                                val = get_attr_robust(part_obj, field)
                                                if isinstance(val, str) and val:
                                                    key = f"{part_id}_{field}"
                                                    old_len = part_lengths.get(key, 0)
                                                    if len(val) > old_len:
                                                        delta_text += val[old_len:]
                                                        part_lengths[key] = len(val)
                                                        
                                    # 3. 处理工具调用与结果摘要 (捕获多种变体)
                                    elif ("call" in event_type or "tool_call" in event_type) and ("created" in event_type or "added" in event_type):
                                        tool_name = get_attr_robust(props, "tool_name") or get_attr_robust(props, "name", "某个动作")
                                        delta_text = f"\n[动作]: 正在执行 {tool_name}...\n"
                                        
                                    elif "tool_result" in event_type and ("created" in event_type or "added" in event_type):
                                        tool_name = get_attr_robust(props, "tool_name") or get_attr_robust(props, "name", "动作")
                                        delta_text = f"[结果]: {tool_name} 执行完毕。\n"

                                    if delta_text:
                                        shared_context["accumulated_text"] += delta_text
                                        # 实时同步到前端
                                        if status_reporter:
                                            status_reporter("chunk", {"content": shared_context["accumulated_text"], "worker_port": "opencode", "session_id": session.id})
                                    
                                    elif event_type == "session.error":
                                        err = get_attr_robust(props, "error", "Unknown error")
                                        if status_reporter:
                                            shared_context["accumulated_text"] += f"\n[底层报错]: {err}\n"
                                            status_reporter("chunk", {"content": shared_context["accumulated_text"], "worker_port": "opencode", "session_id": session.id})
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

                # 构建最终回复摘要
                final_parts_text = []
                if hasattr(response, "parts"):
                    for part in response.parts:
                        if get_attr_robust(part, "type") == "text":
                            final_parts_text.append(get_attr_robust(part, "text", ""))
                        elif get_attr_robust(part, "type") == "tool-call":
                            tool_name = get_attr_robust(part, "tool_name", "unknown")
                            final_parts_text.append(f"\n[动作]: 调用 {tool_name}\n")

                final_summary = "".join(final_parts_text)
                
                if status_reporter:
                    # [Fix] 检查轨迹中是否已经包含了 final_summary 的关键内容 (忽略首尾空格)
                    summary_clean = final_summary.strip()
                    # 为了防止重复展示又不错过真正的新信息，我们只在摘要足够新且不重复时追加
                    if summary_clean and summary_clean not in shared_context["accumulated_text"]:
                        full_content = shared_context["accumulated_text"] + "\n\n[任务完成 - 最终回复]:\n" + final_summary
                    else:
                        full_content = shared_context["accumulated_text"]
                    
                    # 变绿，并将完整内容填入 finish 消息
                    status_reporter("chunk", {"content": full_content, "worker_port": "opencode", "session_id": session.id})
                    status_reporter("finish", {"message": full_content, "worker_port": "opencode", "session_id": session.id})

                    
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
