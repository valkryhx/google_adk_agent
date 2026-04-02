from __future__ import annotations


class UltraplanPromptBuilder:
    def __init__(self, instructions: str):
        self.instructions = instructions.rstrip()

    def build(self, blurb: str, seed_plan: str | None = None) -> str:
        parts: list[str] = []
        if seed_plan:
            parts.extend([
                "Here is a draft plan to refine:",
                "",
                seed_plan,
                "",
            ])
        parts.append(self.instructions)
        if blurb:
            parts.extend(["", blurb])
        return "\n".join(parts)
