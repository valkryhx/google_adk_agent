# AutoCompactAgent Guide

`AutoCompactAgent` is a specialized sub-agent designed to manage the context window of Ciri. It acts as a background cleaner, ensuring the main agent's memory remains manageable without losing critical information.

## 1. Implementation Overview

*   **Source Code**: `src/adk_agent/auto_compact_agent.py`
*   **Inheritance**: Inherits from `LlmAgent`, making it a full-fledged agent but with a specific purpose.
*   **Independence**: It runs in its own temporary session (`temp_compact_task`) to avoid polluting the main agent's context or state.

## 2. Core Logic

### System Prompt
The agent is initialized with a specific system prompt instructing it to act as a "Conversation Summary Expert".
Key rules for summarization:
1.  **Retain Core Goals**: Keep track of the user's intent.
2.  **Record Key Steps**: Note important actions and decisions made.
3.  **Ignore Redundancy**: Remove long code blocks and repetitive tool outputs.
4.  **Maintain Context**: Ensure the summary is coherent enough for another agent (or the main agent after memory wipe) to continue.

### Safe Execution
*   **Input Truncation**: Before processing, it checks `MAX_SAFE_CHARS`. If the history is too long (which is the problem it's trying to solve!), it intelligently truncates the middle part, keeping the beginning (context setup) and the end (recent actions), preventing the compactor itself from crashing due to context overflow.

### The `compact_history` Method
1.  Receives the raw history text.
2.  Performs safety checks (truncation).
3.  Creates a temporary `InMemorySessionService`.
4.  Spins up a temporary `Runner` for itself.
5.  Sends the history to itself with a request to summarize.
6.  Returns the generated summary.

## 3. Integration

This sub-agent is typically called by the `compactor` skill (or the main loop) when:
*   **Token Count High**: The current session's token usage exceeds a threshold.
*   **Turn Count High**: The conversation has gone on for too many turns.

When triggered, the main agent pauses, `AutoCompactAgent` runs, and the main agent's history is replaced with `[System Summary] <new_summary>` + the last few messages.
