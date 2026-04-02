from ultraplan.prompt_builder import UltraplanPromptBuilder


def test_build_includes_seed_plan_before_instructions():
    builder = UltraplanPromptBuilder("INSTRUCTIONS")
    prompt = builder.build("do work", seed_plan="draft plan")
    assert "Here is a draft plan to refine:" in prompt
    assert "draft plan" in prompt
    assert prompt.endswith("do work")
