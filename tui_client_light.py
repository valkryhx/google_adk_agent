import json
import asyncio
import logging
from typing import List, Dict, Optional

import httpx
from textual import work, on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll, Container
from textual.widgets import (
    Header, Footer, Input, Button,
    ListView, ListItem, Label, Static
)
from textual.binding import Binding
from rich.markup import escape
from rich.text import Text

# === 配置 ===
BASE_URL = "http://127.0.0.1:8000"
APP_NAME = "dynamic_expert"
DEFAULT_USER = "user_001"

# === 日志配置 ===
import os
import sys
import time
import logging

LOG_FILE = r"d:\git_codes\google_adk_helloworld_git\tui_debug_force.log"

def log_to_file(msg: str):
    """强制写入文件的调试函数，绕过所有 logging 配置"""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
            f.flush()
            os.fsync(f.fileno()) # 强制刷入磁盘
    except Exception as e:
        pass # 绝不抛出异常影响主程序

logger = logging.getLogger('tui_client')
logger.setLevel(logging.INFO)

# 文件handler - 确保绝对路径
try:
    log_file_path = os.path.abspath("tui_stream.log")
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.info("=== TUI Client 启动 ===")
    
    # 同时记录到强制日志
    log_to_file("=== TUI Client 启动 (Log Restored) ===")
except Exception:
    pass # 如果日志配置失败，不影响主程序运行

# === 自定义组件 ===


# === 自定义组件 ===

class SidebarItem(ListItem):
    """侧边栏会话项"""
    def __init__(self, session_id: str, title: str, **kwargs):
        super().__init__(**kwargs)
        self.session_id = session_id
        self.session_title = title

    def compose(self) -> ComposeResult:
        with Horizontal(classes="sidebar-item-container"):
            yield Label(self.session_title, classes="sidebar-title")
            yield Button("×", variant="error", classes="delete-btn", id=f"del_{self.session_id}")

class MessageBlock(Vertical):
    """
    可折叠的消息块
    - thought/tool_result: 默认折叠，部分显示(Header)，点击展开
    - text/tool_call: 默认展开，无交互
    """
    def __init__(self, block_type: str, content: str = "", **kwargs):
        super().__init__(**kwargs)
        self.block_type = block_type
        self._raw_text = content
        self.add_class(f"block-{block_type}")
        
        # 折叠状态
        self.is_collapsible = block_type in ["thought", "tool_result"]
        self.is_collapsed = self.is_collapsible # 默认折叠
        
        # 子组件
        self.header = Static("", classes="block-header")
        self.content_static = Static("", classes="block-content")
        
        # 初始化内容
        self.refresh_content()
        log_to_file(f"[MessageBlock init] type={block_type}, raw_len={len(self._raw_text)}")

    def compose(self) -> ComposeResult:
        if self.is_collapsible:
            yield self.header
        yield self.content_static

    def on_mount(self):
        if self.is_collapsible:
            self.content_static.display = not self.is_collapsed
            self.header.display = True
        else:
            self.header.display = False
            
    def on_click(self, event) -> None:
        # 只响应 Header 点击
        if self.is_collapsible and event.widget == self.header:
            self.toggle()
            # 阻止事件冒泡 (尽管 Textual 默认可能不冒泡，显式阻止更安全)
            event.stop()

    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        self.content_static.display = not self.is_collapsed
        self.refresh_header()
        
    def refresh_header(self):
        if not self.is_collapsible:
            return
            
        icon = "▶" if self.is_collapsed else "▼"
        title = ""
        if self.block_type == "thought":
            title = "思考过程"
        elif self.block_type == "tool_result":
            title = "工具结果"
            
        header_text = f"{icon} [{title}] (点击查看)"
        self.header.update(header_text)

    def refresh_content(self):
        """渲染逻辑"""
        try:
            # 1. 更新 Header
            self.refresh_header()
            
            # 2. 更新 Content
            clean_text = self._raw_text.replace("\r", "")
            
            # 只有非折叠类型才需要 prefix? 或者保留 prefix 但放在 Content 里?
            # 原始逻辑是 prefix + text。
            # 为了保持一致性，Header 已经显示了类型，Content 里是否还需要 "[思考过程]" 前缀？
            # 之前 prefix 是为了区分块类型。现在有了 Header，Content 里可以只放内容。
            # 但为了兼容 Text 块 (无 Header)，我们需要区分处理。
            
            prefix = ""
            if not self.is_collapsible:
                if self.block_type == "tool_call":
                    prefix = "[工具调用]\n"
                # thought 和 tool_result 由 Header 承担标题功能，Content 纯显示内容
            
            full_text = prefix + clean_text
            
            # 样式
            text_style = None
            if self.block_type == "tool_call":
                text_style = "orange1"
            elif self.block_type == "tool_result":
                # 工具结果通常很长，折叠时 header 需明显
                text_style = "grey70" 
            elif self.block_type == "thought":
                text_style = "magenta1"
                
            renderable = Text(full_text, style=text_style)
            self.content_static.update(renderable)
            
            # 记录日志
            # log_to_file(f"[refresh_content] type={self.block_type}, collapsed={self.is_collapsed}, len={len(clean_text)}")
            
        except Exception as e:
            log_to_file(f"渲染错误 type={self.block_type}: {e}")
            import traceback
            log_to_file(traceback.format_exc())
            self.content_static.update(f"渲染错误: {e}")

    def append_content(self, new_text: str):
        """追加内容(用于流式合并)"""
        self._raw_text += new_text
        self.refresh_content()

class ProcessingIndicator(Static):
    """显示 Thinking and processing... 动画"""
    def __init__(self, **kwargs):
        super().__init__("Thinking and processing.", **kwargs)
        self.add_class("processing-indicator")
        self._dots = 1

    def on_mount(self):
        self.set_interval(0.5, self.update_dots)

    def update_dots(self):
        self._dots = (self._dots % 3) + 1
        dots_str = "." * self._dots
        self.update(f"Thinking and processing{dots_str}")


class ChatMessage(Container):
    """
    一条聊天记录 (User 或 Model)
    包含一个 Role Label 和 一个 Blocks Container
    """
    def __init__(self, role: str, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self.blocks: List[MessageBlock] = []
        
        if role == "user":
            self.add_class("msg-user")
        else:
            self.add_class("msg-model")

    def compose(self) -> ComposeResult:
        # 角色标签
        icon = "👤" if self.role == "user" else "🤖"
        role_name = "User" if self.role == "user" else "Model"
        yield Label(f"{icon} {role_name}", classes="role-label")
        
        # 内容容器
        yield Container(id="blocks-container", classes="blocks-wrapper")

    def add_block(self, block_type: str, content: str = "") -> MessageBlock:
        """同步添加块（简化版，不用 async）"""
        block = MessageBlock(block_type, content)
        self.blocks.append(block)
        # 同步 mount
        container = self.query_one("#blocks-container")
        container.mount(block)
        
        return block

    def show_loading(self):
        """显示加载指示器"""
        # 避免重复添加
        if not self.query("ProcessingIndicator"):
            # 放在 blocks-container 之后
            self.mount(ProcessingIndicator(id="loading-indicator"))

    def remove_loading(self):
        """移除加载指示器"""
        for widget in self.query("ProcessingIndicator"):
            widget.remove()

class SmartInput(Input):
    """
    自定义 Input 组件
    解决 Textual 默认聚焦时不将光标置于末尾的问题
    """
    def _on_focus(self, event) -> None:
        super()._on_focus(event)
        # 强制将光标移到末尾
        self.cursor_position = len(self.value)

# === 主程序 ===

class ADKTextualClientClaude(App):
    """
    TUI Client - Simplified & Robust
    - 移除复杂的 Collapsible，使用简单的 Static
    - 同步mount，避免时序问题
    - 清晰的块类型标识
    """
    
    CSS = """
    /* === 全局配色 === */
    $bg-color: #1a1a1a;
    $sidebar-bg: #222222;
    $text-color: #e6e6e6;
    $secondary-text: #9ca3af;
    $accent-color: #d97757;
    $accent-hover: #e08b6e;
    
    $user-msg-bg: #2d2d2d;
    $border-color: #404040;
    $input-bg: #101010;
    
    $tool-call-color: #60a5fa;
    $tool-result-color: #10b981;
    $thought-color: #6b7280;

    Screen { background: $bg-color; color: $text-color; }
    
    /* === 侧边栏 === */
    #sidebar {
        width: 30;
        background: $sidebar-bg;
        border-right: solid $border-color;
        dock: left;
    }
    #sidebar-header { height: auto; padding: 1; background: $sidebar-bg; }
    #session-list { background: $sidebar-bg; }
    ListItem { background: $sidebar-bg; color: $secondary-text; padding: 0; margin-bottom: 1; height: auto; border: none; }
    ListItem:hover { background: #2c2c2c; color: $text-color; }
    .sidebar-title { width: 1fr; margin-left: 1; height: auto; content-align: left middle; }
    .sidebar-item-container { align: left middle; height: auto; padding: 0; margin: 0; }

    #new-chat-btn {
        width: 100%;
        margin-bottom: 1;
        background: $accent-color;
        color: #1a1a1a;
        text-style: bold;
        border: none;
    }
    #new-chat-btn:hover { background: $accent-hover; }

    .delete-btn {
        min-width: 3;
        height: 1;
        padding: 0;
        margin: 0;
        background: transparent;
        color: $secondary-text;
        border: none;
    }
    .delete-btn:hover { color: #ef4444; background: #3f1d1d; }

    .sidebar-label { color: $accent-color; margin-top: 1; margin-left:1; }
    #user-id-input {
        background: $input-bg;
        border: solid $border-color;
        color: $accent-color;
        height: 3;
    }
    #user-id-input:focus { border: solid $accent-color; }

    /* === 聊天区域 === */
    #chat-scroll { height: 1fr; background: $bg-color; }
    
    .msg-user {
        background: $user-msg-bg;
        color: #ffffff;
        margin: 1 2 1 10;
        padding: 0 2;
        border-left: solid $accent-color;
        min-height: 1;
        height: auto;
    }
    .msg-model {
        background: transparent;
        margin: 1 6 1 2;
        padding: 1 2;
        height: auto;
        overflow-y: auto;
    }
    
    .role-label {
        color: $secondary-text;
        text-style: bold;
        margin-bottom: 1;
    }

    .blocks-wrapper {
        height: auto;
        width: 100%;
        overflow-y: auto;
    }

    /* === 消息块样式 === */
    MessageBlock {
        height: auto;
        width: 100%;
        margin-bottom: 1;
        padding: 0 1;
        min-height: 1;
    }
    
    .block-header {
        width: 100%;
        height: auto;
        text-style: bold;
        color: $accent-color;
    }
    .block-header:hover {
        background: #333333;
    }
    
    .block-content {
        width: 100%;
        height: auto;
    }

    .block-text {
        background: transparent;
        margin: 0;
        padding: 0;
        color: $text-color;
        border-left: none;
    }
    
    .processing-indicator {
        color: #888888;
        text-style: italic;
        margin: 1 0 1 2;
        height: auto;
    }

    .block-thought {
        background: #1e1e1e;
        color: $thought-color;
        border-left: thick $thought-color;
        text-style: italic;
    }

    .block-tool_call {
        background: #0f1a2e;
        color: $tool-call-color;
        border-left: thick $tool-call-color;
    }

    .block-tool_result {
        background: #0f1e18;
        color: $tool-result-color;
        border-left: thick $tool-result-color;
    }

    /* === 输入区 === */
    #input-area {
        height: auto;
        dock: bottom;
        background: $bg-color;
        padding: 0 1 1 1;
        border-top: solid $border-color;
    }
    #msg-input {
        background: #2d2d2d;
        border: solid $border-color;
        color: #ffffff;
        height: 3;
    }
    #msg-input:focus {
        border: solid $accent-color;
        background: #000000;
    }

    Footer { background: $sidebar-bg; color: $secondary-text; }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_chat", "新对话"),
        Binding("ctrl+u", "focus_user_select", "切换用户"),
        Binding("ctrl+d", "toggle_sidebar", "侧边栏"),
        Binding("ctrl+s", "cancel_generation", "停止"),
        Binding("ctrl+q", "quit", "退出"),
    ]

    def __init__(self):
        super().__init__()
        self.user_id = DEFAULT_USER
        self.current_session_id: Optional[str] = None
        self.generation_worker = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-layout"):
            with Vertical(id="sidebar"):
                with Container(id="sidebar-header"):
                    yield Button("✨ 新对话", id="new-chat-btn")
                    yield Label("用户 ID:", classes="sidebar-label")
                    yield SmartInput(value=self.user_id, id="user-id-input", placeholder="输入用户名")
                yield ListView(id="session-list")
            
            with Vertical(id="chat-container"):
                yield VerticalScroll(id="chat-scroll")
                with Container(id="input-area"):
                    yield SmartInput(placeholder="向 Ciri 提问...", id="msg-input")
        
        yield Footer()

    async def on_mount(self):
        self.title = f"CLAUDE CLIENT ({self.user_id})"
        self.query_one("#msg-input").focus()
        await self.load_sessions()

    # === UI Actions ===

    async def action_focus_user_select(self):
        inp = self.query_one("#user-id-input")
        inp.focus()
        inp.cursor_position = len(inp.value)
        
    def action_toggle_sidebar(self):
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    async def action_new_chat(self):
        await self.create_session()

    async def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "user-id-input":
            new_uid = event.value.strip()
            if new_uid and new_uid != self.user_id:
                self.user_id = new_uid
                self.title = f"CLAUDE CLIENT ({self.user_id})"
                self.current_session_id = None
                await self.query_one("#chat-scroll").remove_children()
                await self.load_sessions()
                self.notify(f"用户切换至: {self.user_id}")
            return

        if event.input.id == "msg-input":
            message = event.value.strip()
            if not message: return
            event.input.value = ""
            
            if not self.current_session_id:
                await self.create_session()
            
            scroll = self.query_one("#chat-scroll")
            
            # 用户消息
            user_msg = ChatMessage("user")
            await scroll.mount(user_msg)
            user_msg.add_block("text", message)
            user_msg.scroll_visible()
            
            # 模型消息占位
            model_msg = ChatMessage("model")
            await scroll.mount(model_msg)
            
            # 启动流式生成
            self.generation_worker = self.run_worker(
                self.stream_response(message, model_msg)
            )

    async def on_new_chat_pressed(self):
        await self.create_session()

    async def action_cancel_generation(self):
        """取消当前正在生成的任务
        
        不主动取消 worker,而是通知后端中断,让 worker 自然接收完后端返回的取消消息。
        这样可以确保 '[已停止] 任务已取消。' 消息能够立即显示,而不是延迟到下次请求。
        """
        if self.generation_worker and self.generation_worker.is_running:
            # 不再调用 self.generation_worker.cancel()
            # 让 worker 继续运行,接收后端返回的取消消息
            
            if self.current_session_id:
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"{BASE_URL}/api/cancel",
                            json={
                                "app_name": APP_NAME,
                                "user_id": self.user_id,
                                "session_id": self.current_session_id
                            }
                        )
                    # 不显示本地通知,让后端返回的正式消息成为唯一提示
                    # self.notify("已发送停止信号")
                except Exception as e:
                    self.notify(f"停止失败: {e}", severity="error")
        else:
            self.notify("当前没有正在生成的任务")

    # === API Logic ===

    async def create_session(self):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{BASE_URL}/api/sessions", 
                    json={"app_name": APP_NAME, "user_id": self.user_id}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.current_session_id = data["session_id"]
                    await self.query_one("#chat-scroll").remove_children()
                    await self.load_sessions()
        except Exception as e:
            self.notify(f"创建会话失败: {e}", severity="error")

    async def load_sessions(self):
        list_view = self.query_one("#session-list")
        await list_view.clear()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{BASE_URL}/api/sessions", 
                    params={"app_name": APP_NAME, "user_id": self.user_id}
                )
                if resp.status_code == 200:
                    sessions = resp.json().get("sessions", [])
                    for s in sessions:
                        title = s.get("title")
                        if not title or title == "新对话":
                            title = "✨ 新对话"
                        list_view.append(SidebarItem(s["session_id"], title))
        except Exception:
            pass

    @on(ListView.Selected, "#session-list")
    async def on_session_selected(self, event: ListView.Selected):
        if isinstance(event.item, SidebarItem):
            sid = event.item.session_id
            if self.current_session_id != sid:
                await self.switch_session(sid)

    @on(Button.Pressed, ".delete-btn")
    async def on_delete_session(self, event: Button.Pressed):
        event.stop()
        sid = event.button.id.replace("del_", "")
        await self.delete_session(sid)

    async def delete_session(self, session_id: str):
        try:
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{BASE_URL}/api/sessions/{session_id}", 
                    params={"app_name": APP_NAME, "user_id": self.user_id}
                )
            
            if self.current_session_id == session_id:
                self.current_session_id = None
                await self.query_one("#chat-scroll").remove_children()
            
            await self.load_sessions()
        except Exception as e:
            self.notify(f"删除失败: {e}", severity="error")

    async def switch_session(self, session_id: str):
        self.current_session_id = session_id
        scroll = self.query_one("#chat-scroll")
        await scroll.remove_children()
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{BASE_URL}/api/sessions/{session_id}/history", 
                    params={"app_name": APP_NAME, "user_id": self.user_id}
                )
                if resp.status_code == 200:
                    await self.render_history(resp.json().get("messages", []))
        except Exception as e:
            self.notify(f"加载历史失败: {e}", severity="error")

    async def render_history(self, messages: List[Dict]):
        """渲染历史消息"""
        scroll = self.query_one("#chat-scroll")
        
        for msg_data in messages:
            role = msg_data.get("role", "unknown")
            msg_widget = ChatMessage(role)
            await scroll.mount(msg_widget)
            
            blocks = msg_data.get("blocks", [])
            has_blocks = False
            
            if blocks:
                for block in blocks:
                    b_type = block.get("type", "text")
                    content = block.get("content", "")
                    if content:
                        msg_widget.add_block(b_type, content)
                        has_blocks = True
            
            # 兼容旧格式
            if not has_blocks:
                text = msg_data.get("content") or msg_data.get("text")
                if text:
                    msg_widget.add_block("text", text)
        
        if scroll.children:
            scroll.children[-1].scroll_visible()

    async def stream_response(self, user_msg: str, model_msg_widget: ChatMessage):
        """流式接收并渲染响应"""
        payload = {
            "message": user_msg, 
            "app_name": APP_NAME, 
            "user_id": self.user_id, 
            "session_id": self.current_session_id
        }
        
        
        
        
        # 记录流式响应开始
        log_to_file(f"{'='*60}")
        log_to_file(f"开始新的流式响应: {user_msg}")
        log_to_file(f"{'='*60}")
        
        # 显示加载动画
        model_msg_widget.show_loading()
        
        # 追踪当前块列表
        current_blocks: List[MessageBlock] = []
        
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", f"{BASE_URL}/api/chat", json=payload, timeout=120.0) as response:
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        
                        try:
                            data = json.loads(line)
                            if "chunk" not in data:
                                continue
                            
                            chunk = data["chunk"]
                            
                            # 解析 chunk
                            c_type = "text"
                            content = ""
                            
                            if isinstance(chunk, str):
                                # 兼容旧版字符串格式
                                content = chunk
                            elif isinstance(chunk, dict):
                                c_type = chunk.get("type", "text")
                                content = chunk.get("content", "")
                            
                            
                            
                            # 记录详细日志
                            log_to_file(f"[接收chunk] type={c_type}, len={len(content)}")
                            log_to_file(f"  内容预览: {content[:80]}")
                            log_to_file(f"  当前块数: {len(current_blocks)}, 类型: {[b.block_type for b in current_blocks]}")
                            
                            # === 核心逻辑：参考前端 script.js ===
                            # text 和 thought：如果上一个块是相同类型，则合并
                            # tool_call 和 tool_result：每次都是新块
                            
                            should_merge = False
                            last_block = current_blocks[-1] if current_blocks else None
                            
                            if last_block and c_type in ["text", "thought"]:
                                if last_block.block_type == c_type:
                                    should_merge = True
                            
                            if should_merge and last_block:
                                # 合并到上一个块
                                last_block.append_content(content)
                                last_block.scroll_visible()
                            else:
                                # 创建新块
                                new_block = model_msg_widget.add_block(c_type, content)
                                current_blocks.append(new_block)
                                new_block.scroll_visible()
                                log_to_file(f"[新建] 创建 {c_type} 块, 当前块数={len(current_blocks)}")
                                log_to_file(f"[块详情] block_type={c_type}, _raw_text_len={len(new_block._raw_text)}, display={new_block.display}")
                                
                        except json.JSONDecodeError as e:
                            pass
                        
        except Exception as e:
            if "Cancelled" not in str(e) and not isinstance(e, asyncio.CancelledError):
                log_to_file(f"流式错误: {e}")
                model_msg_widget.add_block("text", f"\n\n❌ 错误: {str(e)}")
                model_msg_widget.scroll_visible()
        finally:
            # 无论成功失败，都移除加载动画
            model_msg_widget.remove_loading()

if __name__ == "__main__":
    app = ADKTextualClientClaude()
    app.run()
