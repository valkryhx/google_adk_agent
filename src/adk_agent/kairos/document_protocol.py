from __future__ import annotations

DOCUMENT_SEMANTIC_ANCHORS = (
    "Goal",
    "Current Status",
    "Current Step",
    "Steps",
    "Expected Artifacts",
    "Blockers",
    "Verification",
    "Replan Notes",
    "Spawned Work",
)


def build_generation_prompt() -> str:
    anchors = "\n".join(f"- {anchor}" for anchor in DOCUMENT_SEMANTIC_ANCHORS)
    return (
        "Write a human-readable markdown work document with the required semantic anchors.\n"
        "Do not respond with json-only output.\n"
        "If key information is missing, record it as open questions instead of omitting it.\n"
        "Required sections:\n"
        f"{anchors}\n"
    )


def build_update_prompt() -> str:
    anchors = ", ".join(DOCUMENT_SEMANTIC_ANCHORS)
    return (
        "Update the existing markdown work document while preserving the semantic anchors: "
        f"{anchors}. "
        "Keep the result readable for humans, avoid json-only rewrites, and surface missing details as open questions."
    )
