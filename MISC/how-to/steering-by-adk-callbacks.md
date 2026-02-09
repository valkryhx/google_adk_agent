# Steering by ADK Callbacks

This guide explains the "Steering" mechanism in Ciri, which allows for real-time control and interruption of the agent's execution flow, similar to `claudecode`.

## 1. The Core Mechanism

The steering capability is built upon the **Google ADK's Callback System** (Aspect-Oriented Programming). It allows us to inject control logic at critical points in the agent's lifecycle without cluttering the main business logic.

### Key Components

1.  **Callbacks**:
    *   `before_model_callback`: Triggered just before the agent calls the LLM.
    *   `before_tool_callback`: Triggered just before the agent executes a tool.
    
2.  **SteeringSession**:
    *   Manages the state for each user session.
    *   Maintains an `asyncio.Queue` specifically for interruption signals.

3.  **Interruption Guard**:
    *   A method `interruption_guard(self, ...)` bound to the session instance.
    *   It checks the interruption queue. If a "CANCEL" signal is present, it immediately raises a `UserInterruption` exception.

## 2. Implementation Details

**Source**: `src/adk_agent/main_web_start_steering.py`

```python
class SteeringSession:
    def __init__(self, ...):
        # ...
        self.queue = asyncio.Queue() # The interruption channel
    
    def interruption_guard(self, *args, **kwargs):
        """Interruption Guard (AOP Aspect)"""
        if not self.queue.empty():
            try:
                signal = self.queue.get_nowait()
                if signal == "CANCEL":
                    print(f"🛑 [Steering] Interruption detected! Target: {self.key}")
                    # Clear queue
                    while not self.queue.empty(): self.queue.get_nowait()
                    raise UserInterruption("User requested to stop operation.")
            except asyncio.QueueEmpty:
                pass

    def _create_agent(self) -> LlmAgent:
        # ...
        agent = LlmAgent(
            # ...
            # Bind the guard to critical lifecycle hooks
            before_model_callback=self.interruption_guard,
            before_tool_callback=self.interruption_guard
        )
        return agent
```

## 3. Why This Matters?

### Real-time Control
In traditional agent loops, once you send a request, you have to wait for it to finish. With Steering, if the agent starts going down a wrong path (e.g., "I will now read all 1 million files..."), the user can hit "Stop", and the agent effectively halts **before** executing the expensive tool call or the next network request.

### Agent Team Safety
This mechanism also applies to the **Agent Team (Swarm)**. If a sub-agent task is taking too long or deviating from the goal, the leader or the user can trigger an interruption, implementing a "Fail Fast" philosophy. This saves tokens, time, and prevents cascading errors.
