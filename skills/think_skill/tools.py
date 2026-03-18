# -*- coding: utf-8 -*-
from typing import List, Optional

async def think_and_plan(
    current_state_analysis: str, 
    next_steps: List[str], 
    potential_risks: Optional[str] = None
) -> str:
    """
    在调用实质性工具（如执行代码、修改文件、查询数据库等）之前，必须先调用此工具。
    这有助于进行逻辑梳理、步骤拆解或错误反思，并为你提供额外的思考空间。

    Args:
        current_state_analysis: 分析当前的任务状态和已获取的上下文。
        next_steps: 接下来要执行的具体动作列表 (TODO list)。
        potential_risks: 这一步可能遇到的问题或潜在的陷阱（可选）。
    """
    print(f"\nAgent is thinking...")
    print(f"Analysis: {current_state_analysis}")
    print(f"Plan:")
    for i, step in enumerate(next_steps, 1):
        print(f"  {i}. {step}")
    if potential_risks:
        print(f"Potential Risks: {potential_risks}")
    print("-" * 20 + "\n")
    
    return "思考过程已成功记录。你现在可以执行计划中的下一步操作。"

def get_tools(*args, **kwargs) -> List:
    """
    返回供挂载的工具函数列表。
    """
    return [think_and_plan]
