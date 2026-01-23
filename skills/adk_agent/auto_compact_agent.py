from typing import Optional
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from config import AgentConfig

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
