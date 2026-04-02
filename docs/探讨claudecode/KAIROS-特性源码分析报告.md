# KAIROS 特性源码分析报告

## 1. 报告目的

本文基于 `claude-code-sourcemap` 中已还原出的源码，以及同目录下的分析文档，对 KAIROS 特性做一次尽量“证据驱动”的源码级分析。

本文重点回答三个问题：

- 为什么需要这个特性（why）
- 这个特性到底是什么（what）
- 它在代码里是如何实现的（how）

与 `ULTRAPLAN` 不同，KAIROS 的还原源码并不完整：大量调用点、状态位、工具接线和 UI 逻辑已经能看到，但核心 `src/assistant/*` 模块在当前还原结果中只有极少部分文件可见。因此，本文会**严格区分“源码直接证据”与“基于调用边界的合理推断”**，避免把二手分析结论误当成源码事实。

---

## 2. 源码范围与结论

本次分析主要使用以下文件：

- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\学习claudecode-20260402.md`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\README.md`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claudecode-best\claude-code\README.md`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claudecode-best\claude-code\CLAUDE.md`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\commands.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\main.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\bootstrap\state.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\state\AppStateStore.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\constants\prompts.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\tools.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\tools\BriefTool\BriefTool.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\tools\ScheduleCronTool\prompt.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\hooks\useScheduledTasks.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\tools\BashTool\BashTool.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\tools\PowerShellTool\PowerShellTool.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\hooks\useReplBridge.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\bridge\initReplBridge.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\commands\bridge\bridge.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\memdir\memdir.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\memdir\paths.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\services\autoDream\autoDream.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\services\compact\prompt.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\entrypoints\agentSdkTypes.ts`

结论可以先说在前面：

1. **KAIROS 不是一个单独的小功能，而是一组围绕 “assistant mode” 搭建的长运行自治能力。**
2. **它不是简单的 `/assistant` 命令别名。** 从源码看，KAIROS 同时改写了命令入口、系统提示词、工具列表、任务调度、远程桥接、记忆写入方式以及长时阻塞处理。
3. **它的本质更接近“后台常驻、可远程附着、可定时唤醒、支持摘要回传的 Agent 运行时”。**
4. **“完全托管 daemon、tick loop、自主睡眠、cron/webhook、push 通知、每日记忆日志 + nightly dream 蒸馏”这些能力，在当前还原源码中大部分都有间接或直接证据支持。**
5. **但 `src/assistant/index.js`、`src/assistant/gate.js`、`src/assistant/daemonBridge.ts` 等核心文件在当前恢复结果中缺失。** 所以像“具体 daemon 如何 fork/监护子进程”“完整安装流程怎么落盘”“真正的桥接协议细节”这类问题，只能做到边界还原，不能声称 100% 完整复现。

因此，KAIROS 的本质可以概括为：

> KAIROS 是 Claude Code 内部的一种 Assistant 模式：它把普通的“用户说一句、模型回一句”的前台 REPL，改造成一个可长期存活、可被远程附着、可定时触发、默认偏异步、具备简报输出和记忆沉淀机制的自治 Agent 运行时。

---

## 3. What：KAIROS 到底是什么

### 3.1 从仓库说明可直接看出：KAIROS 对应 Assistant 模式

文件：`claude-code-sourcemap/README.md:35`

```text
assistant/            # 助手模式（KAIROS）
```

这行虽然很短，但意义非常直接：

- `assistant/` 目录不是普通 UI 组件目录
- 它被仓库作者明确标注为 **“助手模式（KAIROS）”**

这意味着 KAIROS 在作者理解里不是单一工具，而是一个完整模式。

### 3.2 从 feature flag 描述可看出其能力边界

文件：`claudecode-best/claude-code/README.md:378-381`

```text
| `KAIROS` | Assistant 模式 — 长期运行的自主 Agent（含 brief、push 通知、文件发送） |
| `KAIROS_BRIEF` | Kairos Brief — 向用户发送简报摘要 |
| `KAIROS_CHANNELS` | Kairos 频道 — 多频道通信 |
| `KAIROS_GITHUB_WEBHOOKS` | GitHub Webhook 订阅 — PR 事件实时推送给 Agent |
```

这里已经把 KAIROS 的外部能力图谱说得很清楚：

- 主体是 **Assistant 模式**
- 有 **Brief（简报输出）**
- 有 **Push Notification（通知）**
- 有 **SendUserFile（向用户发文件）**
- 有 **Channels（频道/多通道）**
- 有 **GitHub Webhook 订阅**

因此，KAIROS 不是“单次自治”，而是“自治 + 回传 + 事件接入 + 长时运行”的组合能力。

### 3.3 从命令注册看：KAIROS 对外暴露的是 assistant / brief / proactive / subscribe-pr

文件：`src/commands.ts:62-72,101-102`

```ts
const proactive =
  feature('PROACTIVE') || feature('KAIROS')
    ? require('./commands/proactive.js').default
    : null
const briefCommand =
  feature('KAIROS') || feature('KAIROS_BRIEF')
    ? require('./commands/brief.js').default
    : null
const assistantCommand = feature('KAIROS')
  ? require('./commands/assistant/index.js').default
  : null
...
const subscribePr = feature('KAIROS_GITHUB_WEBHOOKS')
  ? require('./commands/subscribe-pr.js').default
  : null
```

这说明：

- `/assistant` 是 KAIROS 主入口
- `/brief` 是 KAIROS 生态的一部分
- `/proactive` 与 KAIROS 共享自治基础设施
- `/subscribe-pr` 是 KAIROS 的事件订阅扩展

所以 KAIROS 不是只“打开一个隐藏命令”，而是在命令层面挂出了一整套伴随能力。

---

## 4. Why：为什么需要 KAIROS

### 4.1 普通 REPL 天生是“前台阻塞”的，不适合长期自治

普通 CLI 对话的默认范式是：

1. 用户输入
2. 模型执行
3. 本轮结束
4. 等待下一次用户输入

这种结构很适合问答和短任务，但不适合以下场景：

- 长时间等待外部命令
- 定时巡检
- 用户不在线时的进度回传
- GitHub/外部系统事件触发
- 会话跨重启持续存在

KAIROS 对这些问题的回答，不是单点 patch，而是把运行模式整体切成“长期运行 Agent”。

### 4.2 源码明确要求自治循环必须靠 tick + sleep，而不是空转发言

文件：`src/constants/prompts.ts:864-886`

```ts
# Autonomous work
You are running autonomously. You will receive `<tick>` prompts...
...
If you have nothing useful to do on a tick, you MUST call SleepTool.
Never respond with only a status message like "still waiting"...
```

这段系统提示非常关键，它表明设计目标是：

- 让模型在“被唤醒”后继续工作
- 如果没有工作可做，就显式进入休眠
- 禁止空转输出浪费 token

也就是说，KAIROS 要解决的是**长期自治的节拍控制问题**。

### 4.3 设计目标之一是“保持主 Agent 响应性”

文件：`src/tools/BashTool/BashTool.tsx:973-981`

```ts
// In assistant mode, the main agent should stay responsive.
// Auto-background blocking commands after ASSISTANT_BLOCKING_BUDGET_MS
// so the agent can keep coordinating instead of waiting.
```

文件：`src/tools/PowerShellTool/PowerShellTool.tsx:830-838` 也有同样逻辑。

这说明 KAIROS 的核心目标之一不是让 Agent 更“聪明”，而是让它在工程上变成一个**不会被长命令拖死的协调器**。

### 4.4 设计目标之二是“会话跨重启连续性”

文件：`src/bridge/initReplBridge.ts:407-410`

```ts
// perpetual (assistant-mode session continuity via bridge-pointer.json) is
// env-coupled and not yet implemented here — fall back to env-based when set
// so KAIROS users don't silently lose cross-restart continuity.
```

这段注释非常直接：

- assistant mode 是 **perpetual**（持续型会话）
- 它要求 **cross-restart continuity**（跨重启连续性）

所以 KAIROS 不是一次性长任务，而是长期存在的“工作线程/工作人格”。

### 4.5 设计目标之三是“让用户不必盯着终端”

文件：`src/tools/BriefTool/BriefTool.ts:31-35`

```ts
status: z.enum(['normal', 'proactive']).describe(
  "Use 'proactive' when you're surfacing something the user hasn't asked for and needs to see now..."
)
```

以及 `claudecode-best/claude-code/README.md:150-160` 中列出的 `PushNotificationTool`、`SendUserFileTool`。

这说明 KAIROS 的用户体验目标是：

- Agent 自己干活
- 在关键时刻通过 brief / push / file 回传结果
- 而不是每一步都要求用户在线盯着

---

## 5. How：整体实现架构

结合现有源码，KAIROS 可以拆成 8 个子系统：

1. **特性门控层**：`feature('KAIROS')` 及相关 flag
2. **模式激活层**：`main.tsx` 中计算 `kairosEnabled`、设置 `kairosActive`
3. **系统提示层**：注入 autonomous/proactive/brief 相关 prompt
4. **工具编排层**：挂载 Sleep / Brief / Push / SendUserFile / SubscribePR
5. **执行调度层**：子代理强制异步、长命令自动后台化
6. **定时任务层**：cron / scheduled tasks / loop skill
7. **远程附着层**：bridge + `claude assistant [sessionId]` viewer 模式
8. **记忆沉淀层**：daily log + nightly dream/distill

下面逐层展开。

---

## 6. 激活层：KAIROS 在哪里被打开

### 6.1 全局状态里有独立的 kairosActive 位

文件：`src/bootstrap/state.ts:72,301,1085-1090`

```ts
kairosActive: boolean
...
kairosActive: false,
...
export function getKairosActive(): boolean {
  return STATE.kairosActive
}
export function setKairosActive(value: boolean): void {
  STATE.kairosActive = value
}
```

这说明 KAIROS 不是临时局部变量，而是全局运行态。

### 6.2 UI/AppState 也有单独的 kairosEnabled 位

文件：`src/state/AppStateStore.ts:113-132`

```ts
// Assistant mode fully enabled (settings + GrowthBook gate + trust).
kairosEnabled: boolean
...
// `claude assistant`: count of background tasks ... running inside the REMOTE daemon child.
remoteBackgroundTaskCount: number
```

这里透露出两个关键事实：

- `kairosEnabled` 是“真正启用 assistant mode”的单一真值来源
- `claude assistant` 连接的不是普通会话，而是 **REMOTE daemon child**

后者很重要：这几乎直接证明了“后台守护 + 前台 viewer”架构。

### 6.3 main.tsx 中真正完成启用逻辑

文件：`src/main.tsx:1048-1087`

```ts
let kairosEnabled = false;
...
if (feature('KAIROS') && assistantModule?.isAssistantMode() && ... && kairosGate) {
  if (!checkHasTrustDialogAccepted()) {
    console.warn(...)
  } else {
    kairosEnabled = assistantModule.isAssistantForced() || (await kairosGate.isKairosEnabled());
    if (kairosEnabled) {
      opts.brief = true;
      setKairosActive(true);
      assistantTeamContext = await assistantModule.initializeAssistantTeam();
    }
  }
}
```

这段实现说明：

- KAIROS 受 **feature flag + trust + runtime gate** 三重约束
- 启用后会**强制打开 brief**
- 启用后会设置 `kairosActive = true`
- 启用后会预初始化一个 assistant team

因此，KAIROS 的实际启动不是“多显示一个菜单”，而是切换整个运行语义。

### 6.4 assistant team 是 KAIROS 的内建能力，而不是事后加上的

文件：`src/main.tsx:1082-1086`

```ts
// Pre-seed an in-process team so Agent(name: "foo") spawns
// teammates without TeamCreate.
assistantTeamContext = await assistantModule.initializeAssistantTeam();
```

这说明在 KAIROS 模式里：

- 多 agent 协作是预置能力
- 不需要用户先手动 TeamCreate
- assistant 本身就被设计成一个能带队的运行时

---

## 7. 系统提示层：KAIROS 如何把模型改造成“长期自治 Agent”

### 7.1 KAIROS 复用了 proactive 模块

文件：`src/constants/prompts.ts:72-85`

```ts
const proactiveModule =
  feature('PROACTIVE') || feature('KAIROS')
    ? require('../proactive/index.js')
    : null
const BRIEF_PROACTIVE_SECTION =
  feature('KAIROS') || feature('KAIROS_BRIEF')
    ? require('../tools/BriefTool/prompt.js').BRIEF_PROACTIVE_SECTION
    : null
```

这表明：

- KAIROS 不是完全独立重写一套自治引擎
- 它复用了 `PROACTIVE` 这条执行链
- 同时又叠加了 Brief 能力

所以更准确地说，**KAIROS = assistant mode + proactive loop + brief output + bridge/daemon 扩展**。

### 7.2 系统提示明确使用 `<tick>` 作为存活/唤醒机制

文件：`src/constants/prompts.ts:864-887`

```ts
You will receive `<tick>` prompts that keep you alive between turns...
If you have nothing useful to do on a tick, you MUST call SleepTool.
```

这几乎就是“tick loop”在 prompt 层的明示版：

- 模型会周期性收到 tick
- tick 的语义是“你还活着，现在继续判断要不要工作”
- 没事做就 Sleep

因此，`学习claudecode-20260402.md` 中提到的 Tick Loop，并非空穴来风，而是和源码高度一致。

### 7.3 compaction 也专门照顾自治模式的连续工作语义

文件：`src/services/compact/prompt.ts:361-367`

```ts
You are running in autonomous/proactive mode. This is NOT a first wake-up —
you were already working autonomously before compaction. Continue your work loop...
```

这说明 KAIROS 不是只在“正常对话”中自治。

连上下文压缩之后，系统也会显式告诉模型：

- 你不是第一次醒来
- 不要重新打招呼
- 继续之前的工作循环

这是一种非常典型的“长活 Agent”工程补丁。

---

## 8. 输出层：为什么 KAIROS 强制绑定 Brief

### 8.1 启动时直接强制 `opts.brief = true`

文件：`src/main.tsx:1076-1081`

```ts
if (kairosEnabled) {
  const opts = options as { brief?: boolean };
  opts.brief = true;
  setKairosActive(true);
}
```

这说明在 Anthropic 的设计里：

- assistant mode 不只是“可选支持 brief”
- 而是 **默认必须 brief 化**

### 8.2 Brief 的 entitlement 直接把 kairosActive 作为放行条件

文件：`src/tools/BriefTool/BriefTool.ts:88-99`

```ts
export function isBriefEntitled(): boolean {
  return feature('KAIROS') || feature('KAIROS_BRIEF')
    ? getKairosActive() || ...
    : false
}
```

这意味着只要 KAIROS 已激活，Brief 资格自动成立。

### 8.3 Brief 的 activation 逻辑明确写着“assistant mode bypasses opt-in”

文件：`src/tools/BriefTool/BriefTool.ts:103-118`

注释原文：

- `Assistant mode (kairosActive) bypasses opt-in...`
- `its system prompt already mandates SendUserMessage`

以及 `src/commands/brief.ts:105-117`：

```ts
// Skip when Kairos is active ...
// the Kairos system prompt already mandates SendUserMessage.
```

这几乎明确告诉我们：

- 在普通模式里，Brief 是一种“可选显示模式”
- 在 KAIROS 模式里，Brief 是**对外沟通协议的一部分**

也就是说，KAIROS 不是普通终端聊天，而是更偏“后台 agent 定期给用户发简报”。

---

## 9. 调度层：KAIROS 如何避免被阻塞

### 9.1 AgentTool 在 KAIROS 下强制所有 subagent 异步化

文件：`src/tools/AgentTool/AgentTool.tsx:559-567`

```ts
// Assistant mode: force all agents async.
const assistantForceAsync = feature('KAIROS') ? appState.kairosEnabled : false;
const shouldRunAsync = (... || assistantForceAsync || ...)
```

注释写得很清楚：

- 如果 subagent 同步执行，主循环会一直被占住
- daemon 的输入队列会积压
- 一旦有 overdue cron catch-up，用户输入会被串行阻塞

所以 KAIROS 选择：**所有 agent 调用强制异步**。

这就是典型的“Coordinator / supervisor 不亲自阻塞干活，而是只负责调度”的思路。

### 9.2 Bash / PowerShell 在 KAIROS 下会自动后台化长命令

文件：`src/tools/BashTool/BashTool.tsx:973-981`

```ts
// In assistant mode, the main agent should stay responsive.
// Auto-background blocking commands after ASSISTANT_BLOCKING_BUDGET_MS...
```

文件：`src/tools/PowerShellTool/PowerShellTool.tsx:830-839` 同理。

这说明 KAIROS 确实实现了“短阻塞预算 + 超时转后台”的机制。

虽然当前片段没有直接暴露预算常量值，但工程意图非常明确：

- 主 agent 要维持协调能力
- 外部命令可以继续跑
- 不能因为一个慢命令把自治循环锁死

因此，`学习claudecode-20260402.md` 中“异步阻塞预算”的说法，至少在设计方向上是被源码支持的。

---

## 10. 定时任务层：KAIROS 如何获得“定时唤醒”能力

### 10.1 KAIROS 相关 cron gate 被明确命名出来

文件：`src/tools/ScheduleCronTool/prompt.ts:11-18`

```ts
Unified gate for the cron scheduling system...
`tengu_kairos_cron` GrowthBook gate...
AGENT_TRIGGERS is independently shippable from KAIROS...
```

这里有两个信息：

1. cron 模块在命名上明确沿用了 `kairos_cron`
2. 但它又被设计成可以独立于 KAIROS 发货

这说明：

- “定时唤醒”最早很可能就是为 assistant mode 设计的
- 后来 cron 能力被抽出来，做成更通用的 AGENT_TRIGGERS 模块

### 10.2 useScheduledTasks 证明了定时任务会向 Agent 注入 prompt

文件：`src/hooks/useScheduledTasks.ts:32-39,71-82,84-121`

关键逻辑包括：

- 挂载一个 scheduler
- 到点后调用 `enqueuePendingNotification`
- 以 `mode: 'prompt'` 的形式把任务重新塞回命令队列
- 使用 `assistantMode` 区分运行语义
- 通过 `isKilled: () => !isKairosCronEnabled()` 支持 kill switch

这说明 cron 在本质上不是“执行 shell 脚本”，而是：

> 把未来某个时刻的任务，重新注入成一条新的用户 prompt / 系统 prompt，唤醒 Agent 继续做事。

这就是典型的 agent tick / scheduled wake-up 机制。

### 10.3 assistant mode 有内建永久任务

文件：`src/utils/cronTasks.ts:51-56`

```ts
System escape hatch for assistant mode's built-in tasks (catch-up/
morning-checkin/dream)...
only written directly to scheduled_tasks.json by src/assistant/install.ts.
```

这是非常强的证据。它直接说明 assistant mode 内建至少几类持久化任务：

- `catch-up`
- `morning-checkin`
- `dream`

所以 KAIROS 不是只支持“用户自定义定时提醒”，而是系统自己就有长期常驻任务模板。

---

## 11. 远程与守护进程层：KAIROS 为什么像一个 daemon

### 11.1 CLI 子命令 `claude assistant [sessionId]` 只是 viewer client

文件：`src/main.tsx:3259-3264`

```ts
// `claude assistant [sessionId]` — REPL as a pure viewer client
// of a remote assistant session. The agentic loop runs remotely; this
// process streams live events and POSTs messages.
```

这段注释几乎可以定性：

- `claude assistant` 前台进程不是主执行者
- 真正的 agentic loop 在远端 / 后台运行
- 当前 REPL 只是一个 viewer + message bridge

这是 KAIROS 最核心的实现特征之一。

### 11.2 如果没有 session，会先安装 assistant，再等待 daemon 启动

文件：`src/main.tsx:3277-3290`

```ts
Assistant installed in ${installedDir}. The daemon is starting up —
run `claude assistant` again in a few seconds to connect.
```

这句话基本上已经把“后台 daemon”写死了。

也就是说：

- assistant 需要单独安装/部署
- 它会启动 daemon
- 之后 CLI 再 attach 上去

### 11.3 RemoteControlHandle 的注释明确区分 daemon parent 和 agent child

文件：`src/entrypoints/agentSdkTypes.ts:420-427`

```ts
Hold a claude.ai remote-control bridge connection from a daemon process.
The daemon owns the WebSocket in the PARENT process...
If the agent subprocess crashes, the daemon respawns it...
```

这段是全篇最强证据之一。它证明：

- 存在一个 **daemon process**
- daemon 自己持有 WebSocket
- 真正 agent loop 在其子进程中运行
- 子进程崩了，daemon 可以拉起新的 child
- claude.ai 侧会保持同一个 session

这完全符合“后台常驻 supervisor + worker child”的架构。

### 11.4 assistant mode 使用 perpetual bridge，强调会话连续性

文件：`src/hooks/useReplBridge.tsx:156-170`

```ts
continuous conversation across CLI restarts ...
let perpetual = false;
if (feature('KAIROS')) {
  const { isAssistantMode } = await import('../assistant/index.js');
  perpetual = isAssistantMode();
}
```

文件：`src/bridge/initReplBridge.ts:473-484`

```ts
Assistant-mode sessions advertise a distinct worker_type ...
if (isAssistantMode()) {
  workerType = 'claude_code_assistant'
}
```

这说明 KAIROS 的桥接会话和普通 `claude_code` worker 是分开的：

- 有专门的 `worker_type`
- 有 perpetual 连续会话语义
- 远程 UI 可以单独识别 assistant session

因此，KAIROS 不是在现有 REPL 上打补丁，而是定义了另一类 runtime。

---

## 12. 事件与外部输入层：KAIROS 如何接外部世界

### 12.1 GitHub Webhook 是明确存在的

文件：`src/tools.ts:42-51`

```ts
const SendUserFileTool = feature('KAIROS') ...
const PushNotificationTool = feature('KAIROS') || feature('KAIROS_PUSH_NOTIFICATION') ...
const SubscribePRTool = feature('KAIROS_GITHUB_WEBHOOKS') ...
```

以及文件：`src/hooks/useReplBridge.tsx:193-200`

```ts
if (feature('KAIROS_GITHUB_WEBHOOKS')) {
  const { sanitizeInboundWebhookContent } = require('../bridge/webhookSanitizer.js')
  sanitized = sanitizeInboundWebhookContent(fields.content);
}
```

再加上：`src/components/messages/UserTextMessage.tsx:93-107`（从 grep 结果可见）会识别 `<github-webhook-activity>`。

这串证据表明：

- GitHub webhook 不是文档幻想，而是代码里的正式输入通道
- webhook 内容进入系统前还要做 sanitizer
- 它会以用户消息/活动消息的形式注入会话

### 12.2 Channels 也是真实的一层能力

文件：`src/main.tsx:1642-1697`

这里会解析 `--channels` 和 `--dangerously-load-development-channels`，把 `plugin:<name>@<marketplace>` / `server:<name>` 解析成 channel entry。

这说明 KAIROS 的“多通道”不是抽象概念，而是已经进入参数和权限模型。

因此可以推断：

- KAIROS 在架构上是把外部事件源都看成“可注入消息渠道”
- GitHub webhook 只是其中一种 channel/bridge 输入

---

## 13. 记忆层：KAIROS 如何做长期记忆与蒸馏

### 13.1 assistant mode 不直接维护 MEMORY.md，而是写每日日志

文件：`src/memdir/memdir.ts:319-348`

```ts
Assistant sessions are effectively perpetual, so the agent writes memories
append-only to a date-named log file rather than maintaining MEMORY.md as
a live index. A separate nightly /dream skill distills logs into topic
files + MEMORY.md.
```

这段注释很关键，直接回答了 KAIROS 的长程记忆机制：

- assistant session 是长期持续的
- 新记忆写入 **append-only daily log**
- 不是实时改 `MEMORY.md`
- 夜间有独立 `/dream` 流程做蒸馏

### 13.2 daily log 的具体路径规则也有直接实现

文件：`src/memdir/paths.ts:238-250`

```ts
Shape: <autoMemPath>/logs/YYYY/MM/YYYY-MM-DD.md
...
Used by assistant mode (feature('KAIROS'))
```

这说明 daily log 并非概念，而是已落到实际路径结构。

### 13.3 autoDream 在 KAIROS 下会让位给 disk-skill dream

文件：`src/services/autoDream/autoDream.ts:95-99`

```ts
if (getKairosActive()) return false // KAIROS mode uses disk-skill dream
```

这意味着：

- 普通模式有一套 `autoDream`
- KAIROS 模式有另一套更适合长期会话的 dream 路径
- 它们不是混用，而是显式分流

因此，`学习claudecode-20260402.md` 里对 autoDream / 记忆蒸馏的描述，和源码并不冲突，反而能被这一层直接支撑。

---

## 14. 还原出的运行机制

综合前面的证据，可以把 KAIROS 的运行过程还原成如下流程：

### 14.1 启动

1. 用户或系统进入 `assistant mode`
2. `main.tsx` 检查 trust、gate 和 feature flag
3. 设置 `kairosActive = true`
4. 强制启用 brief
5. 初始化 assistant team
6. 以 `kairosEnabled` 启动 REPL / headless 环境

### 14.2 进入自治循环

1. 系统提示词告诉模型：你正在 autonomous/proactive mode
2. 后续会收到 `<tick>` 提示
3. 如果没事做，调用 SleepTool
4. 如果有事做，就继续读文件、调工具、派子代理

### 14.3 遇到慢任务

1. 子代理默认异步执行
2. Bash/PowerShell 长命令超过阻塞预算会被自动后台化
3. 主 Agent 继续保持响应和调度能力

### 14.4 定时任务与外部事件

1. scheduler 根据 cron 或系统内建任务触发 prompt
2. GitHub webhook / channels / remote bridge 可注入外部消息
3. 这些输入被转换为“新的会话消息”，驱动 Agent 继续工作

### 14.5 对外回传

1. KAIROS 默认依赖 Brief 进行用户可见输出
2. 关键进度可通过 push / file / message 回传
3. 前台 `claude assistant` 客户端只负责 attach 查看和输入

### 14.6 记忆沉淀

1. 长会话期间新知识追加到 daily log
2. 夜间 dream 任务把日志蒸馏为 topic files + MEMORY.md
3. 下一轮长期运行再继续使用 distilled memory

这套链路完整地解释了为什么 KAIROS 看起来像“后台同事”而不是“终端里的一次性助手”。

---

## 15. 关键设计点

### 15.1 把“自治”拆成多个工程机制，而不是依赖一句 prompt

KAIROS 实现不是只加一句“你现在自主工作”。它至少同时改了：

- prompt
- tool pool
- async policy
- backgrounding policy
- cron scheduler
- bridge session model
- memory write path
- remote viewer mode

这说明 Anthropic 的思路很务实：

> 自治不是语言层幻觉，而是运行时约束 + 状态机 + I/O 通道 + 持久化策略的总和。

### 15.2 “主 Agent 保持轻、任务尽量异步”是第一原则

从 `AgentTool` 强制 async，到 Bash/PowerShell 自动 background，再到 remote daemon + child respawn，都说明 KAIROS 的核心不是“更强的推理”，而是：

- 主 loop 永远不要被重任务锁死
- coordinator/assistant 要像操作系统的 scheduler 一样工作

### 15.3 KAIROS 把“人类可见输出”从普通文本提升为专用协议

Brief 在普通模式是可选，在 KAIROS 中是默认绑定。这意味着 Anthropic 把“后台 agent 如何打扰用户”当作一等设计问题，而不是 UI 细节。

### 15.4 KAIROS 的记忆设计是 append-only，再 nightly distill

这点很值得借鉴。因为长期运行 agent 最怕两件事：

- 一边工作一边频繁重写结构化记忆，容易损坏
- 记忆越来越脏，越来越长

KAIROS 的做法是：

- 白天只追加日志
- 夜里统一蒸馏
- MEMORY.md 只保留 distilled index

这是非常典型的日志型架构思想。

---

## 16. 与《学习claudecode-20260402.md》中的说法逐项对照

### 16.1 可以被源码支持的部分

以下说法可以认为**基本被源码支持**：

- KAIROS 是 assistant mode / 长期运行的自主 Agent
- 它具备 tick + sleep 的自治循环语义
- 它强调保持主循环响应性，不让长命令阻塞
- 它支持 cron / scheduled tasks
- 它支持 GitHub webhook 与 push/file/message 类回传
- 它有长期记忆日志与 nightly dream/distill 路径
- 它通过 daemon + remote bridge + viewer client 形成长期会话

### 16.2 只能部分支持、不能下绝对结论的部分

以下说法**方向上很像真相，但当前恢复源码不足以完全证实**：

- “KAIROS 是完全托管的系统级后台守护进程”
  - 可以确认存在 daemon process，但“完全托管”的部署细节还看不到
- “15 秒阻塞预算”
  - 当前可确认存在 `ASSISTANT_BLOCKING_BUDGET_MS`，但我未在本次已读片段中拿到具体数值
- “跨会话记忆整合”
  - 当前可确认 daily log + nightly dream 路径，但整合算法细节没有完整源码
- “SleepTool 会根据任务队列和资源消耗自主休眠”
  - 当前可确认 SleepTool 被系统提示强制使用，但具体 sleep 策略逻辑未见完整实现

所以更稳妥的表述是：

> 那份学习笔记对 KAIROS 的总体方向判断大体是对的，但其中一部分细节属于“根据调用点和架构痕迹作出的高可信推断”，而不是所有点都能被当前恢复源码逐行证明。

---

## 17. 当前恢复源码的缺口

这次分析最需要强调的一点是：**KAIROS 相关源码存在恢复缺口。**

比如从 `src/main.tsx` 可以明确看到这些模块被引用：

- `./assistant/index.js`
- `./assistant/gate.js`
- `./assistant/sessionDiscovery.js`
- `src/assistant/daemonBridge.ts`（在注释中被提及）
- `src/assistant/install.ts`（在 cron 注释中被提及）

但在当前 `restored-src/src/assistant` 目录里，可直接看到的只有极少文件。

这意味着：

- 我们已经能看清 KAIROS 的**外围架构和运行语义**
- 但还看不到 assistant 子系统的**全部内部实现细节**

因此，当前报告适合用于：

- 理解 KAIROS 是什么
- 理解它为什么要存在
- 理解它是如何接入现有 CLI 运行时的

但不适合宣称：

- 已经完整还原出 daemon supervisor 的全部实现
- 已经完整还原出 assistant install / session discovery / gate 细节

---

## 18. 最终结论

如果只用一句话总结 KAIROS，我会这样定义：

> KAIROS 是 Claude Code 内部的 Assistant Mode 运行时：它把一次一答式 REPL，升级成一个长期存活、可定时唤醒、默认异步、支持 remote attach、支持 brief/push/webhook 回传，并通过 daily-log + dream 机制沉淀长期记忆的后台自治 Agent。

进一步拆开看：

- **Why**：为了解决普通 CLI 不适合长期自治、定时巡检、事件触发、跨重启连续性和后台进度回传的问题。
- **What**：它是一个 assistant mode / daemon-backed autonomous runtime，而不是单独命令。
- **How**：通过 `kairosActive/kairosEnabled` 状态位、proactive/tick prompt、Brief 强绑定、异步子代理、长命令后台化、cron 调度、remote bridge viewer、webhook/channel 输入，以及 daily-log + dream 蒸馏共同实现。

从工程角度看，KAIROS 最值得借鉴的不是某一个隐藏命令，而是它背后的设计原则：

1. 自治 Agent 必须有专门的运行时，不是给普通聊天 prompt 多写几句指令就够了。
2. 长任务系统要默认异步化，主循环永远保持可调度。
3. 长期记忆要走 append-only + batch distill，而不是在线频繁重写索引。
4. 用户交互必须被产品化：brief、push、viewer、webhook 都属于自治系统的一部分。

---

## 19. 附：一句“初步判断版”结论

如果只根据现有材料做一个最简初步解释：

> KAIROS 看起来就是 Claude Code 内部的“后台助手模式”。它不是在当前终端里同步跑完就结束，而是把 Agent 变成一个可长期存活的后台 worker / daemon：能定时被唤醒、能接收外部事件、能把进度主动摘要给用户、能跨重启继续会话，还会把长期经验记到每日日志，夜间再蒸馏成更稳定的记忆。

这个结论有充分源码支撑；唯一需要保留的谨慎是：assistant 核心子模块在当前恢复结果中不完整，所以部分 daemon 内部细节仍属于高可信推断，而不是全量源码实证。
