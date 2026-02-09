# Agent Team: The Fractal Swarm Architecture

Ciri implements a **Fractal Agent Architecture**, inspired by *Agent Smith* from *The Matrix*. In this system, every agent is identical in code and capability. There are no hardcoded "Manager Agents" or "Coder Agents". Role is determined dynamically by the task at hand.

## 1. The "Agent Smith" Philosophy

*   **Uniformity**: Every node in the swarm runs the same `adk_agent` code.
*   **Fractal Nature**: A "Leader" in one context can be a "Worker" in another. If Agent A dispatches a task to Agent B, A is the leader. If B then needs help and dispatches to C, B becomes a leader relative to C.
*   **Dynamic Roles**: You don't configure "Agent 1 is a Coder, Agent 2 is a Tester". instead, you just spawn 5 generic agents. If the task is "Write code", Agent 1 becomes a Coder. If the task is "Test this", Agent 2 becomes a Tester.

## 2. Core Implementation

*   **Skill**: `skills/agent_team`
*   **Tool**: `dispatch_task(task_instruction, context_info, target_port, priority)`
*   **Service Discovery**:
    *   **Mechanism**: A lightweight SQLite registry (`sqlite_db/swarm_registry.db`).
    *   **Registration**: When an agent starts, it registers its IP/Port and Status in the DB.
    *   **Discovery**: When `dispatch_task` is called, the agent queries the DB for `status='active'` nodes, excluding itself.

## 3. Key Features

### True Flexibility
Since every agent is backed by **LiteLLM**, you can hook up *any* model that supports function calling (Deepseek, Claude, GPT-4, etc.). You can have a swarm of weak models managed by a strong model, or a homogenous cluster of strong models.

### "Fail Fast" Interruption
The swarm supports a robust interruption mechanism.
*   **Scenario**: Leader sends a task "Count to infinity" to Worker A.
*   **Problem**: Worker A will never finish.
*   **Solution**: Leader (or User) issues a new command with `priority="URGENT"`. The Worker's `SteeringSession` detects this, kills the running infinite loop, and immediately processes the new high-priority instruction.

### Frontend/Backend Separation
*   **Backend**: The Swarm runs as a cluster of headless Python services.
*   **Frontend**: A separate Web UI or TUI connects to any node. Since all nodes are fractal, connecting to *any* node allows you to control the whole swarm.

## 4. Easy to Start
The architecture is designed to be "Easy to Start, Hard to Master".
*   **Single File**: `tools.py` in `skills/agent_team` contains the entire swarm logic.
*   **No Complex Protocol**: No Raft/Paxos. Just simple HTTP calls and a shared DB file for discovery.
*   **ReAct Self-Healing**: If a task fails, the receiving agent naturally reports back the error. The sender agent (Leader) uses its LLM reasoning to decide whether to retry, change the prompt, or ask another worker, implementing basic self-healing without complex orchestration code.

## 5. Summary
Ciri's Agent Team is not a rigid hierarchy. It's a **liquid network of intelligence**. Like Agent Smith, they are infinite, interchangeable, and relentless in achieving the goal.
