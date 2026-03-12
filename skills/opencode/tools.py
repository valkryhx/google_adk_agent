import asyncio
import traceback
import os
import sys
from typing import List
from opencode_ai import Opencode

# [纯函数] 放在顶层，保证线程安全，不持有任何全局状态
def get_attr_robust(obj, attr, default=None):
    """鲁棒地获取属性：支持对象属性访问、字典访问和 Vars 访问"""
    if obj is None: return default
    if hasattr(obj, attr):
        return getattr(obj, attr, default)
    if isinstance(obj, dict):
        return obj.get(attr, default)
    if hasattr(obj, "__dict__"):
        try:
            return obj.__dict__.get(attr, default)
        except Exception:
            pass
    return default

def get_opencode_config() -> dict:
    """动态读取 OpenCode 服务的本地配置"""
    config_path = os.path.join(os.path.dirname(__file__), "opencode_service.yaml")
    config = {"url": "http://127.0.0.1:4096", "provider": None, "model": None}
    if not os.path.exists(config_path): return config
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if not line or ":" not in line: continue
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k == "opencode_base_url": config["url"] = v
                elif k == "opencode_provider": config["provider"] = v
                elif k == "opencode_model": config["model"] = v
    except Exception: pass
    return config

def get_default_provider_and_model(base_url: str):
    """动态获取服务端的默认引擎配置"""
    try:
        import urllib.request, json
        req = urllib.request.Request(f"{base_url.rstrip('/')}/provider")
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            connected = data.get('connected', [])
            defaults = data.get('default', {})
            for choice in ['opencode', 'local-deepseek', 'google', 'anthropic', 'openai']:
                if choice in connected and choice in defaults:
                    return choice, defaults[choice]
            if connected:
                p = connected[0]
                return p, defaults.get(p, "")
    except Exception: pass
    return "opencode", "big-pickle"

def get_tools(*args, **kwargs) -> List:
    """
    加载 OpenCode 技能。
    [回滚]: 已移除模块强制重载逻辑，确保高并发下的 Session 隔离安全。
    """
    status_reporter = kwargs.get('status_reporter')
    interruption_queue = kwargs.get('interruption_queue')

    async def opencode_delegate(prompt: str) -> str:
        """
        [opencode-Agent] 专门处理复杂编码、多文件重构、环境配置和终端命令的底层智能体。
        """
        # 1. 任务级的上下文隔离 (闭包变量)
        task_context = {
            "accumulated_text": "[OpenCode 运行轨迹]\n\n", 
            "full_content": ""
        }
        
        # 2. 动态读取配置并创建独立 Session
        config = get_opencode_config()
        base_url = config.get("url", "http://127.0.0.1:4096")
        provider_id = config.get("provider")
        model_id = config.get("model")
        
        try:
            client = Opencode(base_url=base_url)
            if not provider_id or not model_id:
                provider_id, model_id = get_default_provider_and_model(base_url)
            
            # 为当前任务创建一个隔离的沙盒 Session (并发隔离的关键)
            session = client.session.create(extra_body={})
            session_id = session.id
            print(f"[OpenCode] 🚀 任务启动 | Session: {session_id} | Model: {model_id}")
        except Exception as e:
            return f"[异常] 无法连接到 OpenCode 服务: {e}"

        if status_reporter:
            status_reporter("init", {
                "task_preview": "正在唤醒 OpenCode 底层代码智能体...",
                "worker_port": "opencode",
                "session_id": session_id,
                "deep_think_role": "OpenCode-Agent"
            })
            status_reporter("chunk", {"content": task_context["accumulated_text"], "worker_port": "opencode", "session_id": session_id})
            
        # 3. 注入当前工程的绝对路径约束 (防止写偏)
        current_project_root = os.getcwd()
        context_aware_prompt = f"[环境约束]: 当前项目根目录的绝对路径是: {current_project_root}\n" \
                               f"请务必在上述路径下执行所有文件读写和终端命令。\n\n" \
                               f"[任务指令]:\n{prompt}"

        def run_opencode_sync():
            try:
                import threading
                stop_event = threading.Event()
                
                def event_listener():
                    part_lengths = {}
                    try:
                        for event in client.event.list():
                            if stop_event.is_set(): break
                            if interruption_queue and not interruption_queue.empty():
                                if status_reporter:
                                    status_reporter("fail", {"error": "用户强制中断", "worker_port": "opencode", "session_id": session_id})
                                break
                            
                            props = getattr(event, "properties", None)
                            if props:
                                e_sid = get_attr_robust(props, "session_id")
                                # 只处理当前 Session 的事件
                                if e_sid == session_id or e_sid is None:
                                    delta = ""
                                    p_id = get_attr_robust(props, "part_id", "default")
                                    e_type = getattr(event, "type", "")
                                    
                                    if e_type == "message.part.delta":
                                        delta = get_attr_robust(props, "delta", "")
                                    elif "updated" in e_type:
                                        p_obj = get_attr_robust(props, "part")
                                        if p_obj:
                                            for field in ["text", "thought", "content"]:
                                                val = get_attr_robust(p_obj, field)
                                                if isinstance(val, str) and val:
                                                    key = f"{p_id}_{field}"
                                                    old_l = part_lengths.get(key, 0)
                                                    if len(val) > old_l:
                                                        delta += val[old_l:]
                                                        part_lengths[key] = len(val)
                                    elif ("call" in e_type) and ("created" in e_type or "added" in e_type):
                                        t_name = get_attr_robust(props, "tool_name") or get_attr_robust(props, "name", "动作")
                                        delta = f"\n[动作]: 正在执行 {t_name}...\n"
                                    
                                    if delta:
                                        task_context["accumulated_text"] += delta
                                        if status_reporter:
                                            status_reporter("chunk", {"content": task_context["accumulated_text"], "worker_port": "opencode", "session_id": session_id})
                    except Exception: pass

                listener = threading.Thread(target=event_listener, daemon=True)
                listener.start()

                # 开启 SDK 请求
                response = client.session.chat(
                    id=session_id, provider_id=provider_id, model_id=model_id,
                    parts=[{"type": "text", "text": context_aware_prompt}]
                )
                stop_event.set()

                # 构建最终回复
                final_parts = []
                if hasattr(response, "parts"):
                    for p in response.parts:
                        if get_attr_robust(p, "type") == "text":
                            final_parts.append(get_attr_robust(p, "text", ""))
                
                final_summary = "".join(final_parts)
                # 检查是否重复
                if final_summary.strip() and final_summary.strip() not in task_context["accumulated_text"]:
                    task_context["full_content"] = task_context["accumulated_text"] + "\n\n[任务完成]:\n" + final_summary
                else:
                    task_context["full_content"] = task_context["accumulated_text"]

                if status_reporter:
                    status_reporter("chunk", {"content": task_context["full_content"], "worker_port": "opencode", "session_id": session_id})
                    status_reporter("finish", {"message": task_context["full_content"], "worker_port": "opencode", "session_id": session_id})
            
            except Exception as e:
                if status_reporter:
                    status_reporter("fail", {"error": str(e), "worker_port": "opencode", "session_id": session_id})

        # 4. 在独立线程运行以避免阻塞 asyncio
        await asyncio.to_thread(run_opencode_sync)
        
        # 5. 返回全量内容，确保刷新后卡片轨迹不消失
        return task_context["full_content"] or task_context["accumulated_text"]

    opencode_delegate.__name__ = "opencode_delegate"
    return [opencode_delegate]
