from typing import Optional
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from skills.adk_agent.config import AgentConfig

class AutoCompactAgent(LlmAgent):
    """
    专门负责生成对话摘要的 Sub-Agent。
    继承自 LlmAgent，可作为 Main Agent 的子 Agent 运行。
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig()
        
        # Reuse main agent's model config
        llm_model = LiteLlm(
            model=config.model,
            api_key=config.api_key,
            api_base=config.api_base,
            extra_body=config.extra_body
        )
        
        system_prompt = """你是一个专业的对话摘要专家。你的任务是阅读以下对话历史，并生成一个精炼的摘要。

请遵循以下规则：
1. **保留核心目标**：明确用户的意图和当前任务。
2. **记录关键步骤**：保留已完成的重要操作和决策。
3. **忽略冗余细节**：省略具体的代码块、长文本输出和重复的工具调用细节。
4. **保持上下文连贯**：确保摘要能让另一个 Agent 接手任务而无需阅读原始历史。
5. **格式清晰**：使用简洁的段落或列表。

输出格式示例：
"用户希望实现 X 功能。目前已完成 A 和 B 步骤。在执行 C 步骤时遇到错误 Y，正在尝试 Z 方案解决。"
"""
        
        super().__init__(
            name="auto_compactor",
            model=llm_model,
            instruction=system_prompt,
            tools=[] # No tools needed for pure summarization
        )
        
    async def compact_history(self, history_text: str) -> str:
        """
        执行摘要生成任务。
        由于是 Sub-Agent，我们可以在这里创建一个临时的 Runner 来执行一次性的摘要任务。
        """
        print(f"[AutoCompactAgent] 收到摘要请求，文本长度: {len(history_text)}")
        
        # [SAFETY] 超大文本截断保护
        # 如果历史记录太大 (例如 > 200k chars，约 50k tokens)，可能会导致 Compactor 自身也爆 Token
        # 此时我们需要强行截断，只保留开头(System)和结尾(最近对话)，丢弃中间
        MAX_SAFE_CHARS = 200000 
        if len(history_text) > MAX_SAFE_CHARS:
             print(f"[AutoCompactAgent] ⚠️ 警告：输入文本过长 ({len(history_text)} chars)，执行安全截断...")
             # 保留前 20% 和后 30%，中间用占位符
             keep_head = int(MAX_SAFE_CHARS * 0.2)
             keep_tail = int(MAX_SAFE_CHARS * 0.3)
             history_text = (
                 history_text[:keep_head] + 
                 f"\n\n... [中间 {len(history_text) - keep_head - keep_tail} 字符因过长已省略] ...\n\n" + 
                 history_text[-keep_tail:]
             )

        # Create a temporary session for this summarization task
        temp_session_service = InMemorySessionService()
        temp_session = await temp_session_service.create_session(
            app_name="compactor_service",
            user_id="system",
            session_id="temp_compact_task"
        )
        
        # Use a Runner to execute the agent
        runner = Runner(
            agent=self,
            session_service=temp_session_service,
            app_name="compactor_service"
        )
        
        from google.genai import types
        prompt_content = types.Content(role='user', parts=[types.Part(text=f"请为以下对话历史生成摘要：\n\n{history_text}")])
        
        response_text = ""
        try:
            # Run the agent
            async for event in runner.run_async(
                user_id="system",
                session_id="temp_compact_task",
                new_message=prompt_content
            ):
                if hasattr(event, 'is_final_response') and event.is_final_response():
                    if event.content and event.content.parts:
                        response_text = event.content.parts[0].text
            
        except Exception as e:
            print(f"[AutoCompactAgent] Error generating summary: {e}")
            import traceback
            traceback.print_exc()
            response_text = "Error generating summary."
            
        return response_text
