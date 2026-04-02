# claudecode-best 中 KAIROS 相关文件清单

## 1. 文档目的

本文只分析一个对象：

- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claudecode-best\claude-code`

目标是把这个仓库里所有与 **KAIROS / assistant mode** 明显相关的文件梳理成一份独立清单，并回答三个问题：

1. 这些文件分别负责什么
2. 它们是真实现、外围实现，还是 stub
3. `claudecode-best` 到底有没有把 KAIROS 真正复现出来

本文不与 `claude-code-sourcemap` 做横向对比，只做当前仓库自身的独立盘点。

---

## 2. 总结结论

结论先说在前面：

> `claudecode-best/claude-code` **确实包含一套比较完整的 KAIROS 相关代码骨架和大量外围实现**，包括命令注册、主流程接线、brief、proactive、cron、bridge、memory、UI 状态等；但是 **assistant 核心模块本身仍然是 stub**，所以它还不能算“完整可运行的 KAIROS 复现”。

更具体地说：

- **有真实实现的部分**：KAIROS 相关的外围运行时、工具接线、系统提示、memory 路径、cron 调度、bridge 兼容逻辑、AppState 等
- **只有空壳的部分**：assistant 内核本身，包括 `isAssistantMode`、`initializeAssistantTeam`、`isKairosEnabled`、`discoverAssistantSessions`、assistant 命令 UI 安装逻辑等

因此，这个仓库更准确的定位是：

> **KAIROS 的“半复现工程”或“高保真框架还原版”**，而不是一个真正把 assistant daemon 全量跑起来的成品。

---

## 3. 评估标准

为了避免“看见文件就算实现”的误判，本文把文件分成四类：

### A. 核心真实实现

文件中包含可工作的业务逻辑，而不是只有接口或常量。

### B. 外围真实实现

文件不是 assistant 核心本体，但确实实现了 KAIROS 依赖的能力，例如：

- brief
- proactive prompt
- cron 调度
- bridge 行为分支
- memory 路径与写入策略

### C. 接线文件

文件主要负责：

- feature flag 注册
- import/require 接线
- 状态切换
- 把 KAIROS 接入主流程

这类文件很重要，但不能等同于“完整复现”。

### D. Stub / 占位实现

文件存在，但核心函数直接返回：

- `false`
- `''`
- `[]`
- 空对象 / 空 Promise
- 注释写明 `Auto-generated stub — replace with real implementation`

这类文件代表“接口形状已恢复，但核心逻辑缺失”。

---

## 4. KAIROS 文件清单总表

下面先给出总表，再逐项展开。

| 文件 | 角色 | 类型判断 | 结论 |
|---|---|---|---|
| `src/assistant/index.ts` | assistant 核心入口 | D Stub | 核心能力缺失 |
| `src/assistant/gate.ts` | KAIROS 启用 gate | D Stub | 仅保留接口 |
| `src/assistant/sessionDiscovery.ts` | assistant session 发现 | D Stub | 只返回空数组 |
| `src/assistant/sessionHistory.ts` | assistant 历史读取 | 待谨慎，未展开 | 存在文件，但本次未深入 |
| `src/commands/assistant/assistant.ts` | `/assistant` 命令实现 | D Stub | 仅占位 |
| `src/main.tsx` | KAIROS 主流程接线 | C 接线 + 部分真实逻辑 | 很关键，但不是 assistant 内核 |
| `src/commands.ts` | 命令注册 | C 接线 | 注册 `/assistant` `/brief` `/proactive` |
| `src/tools.ts` | 工具接线 | C 接线 | 接入 Sleep/Brief/Push 等 |
| `src/constants/prompts.ts` | 系统提示 | B 外围真实实现 | 真正定义自治 prompt |
| `src/tools/BriefTool/BriefTool.ts` | brief 输出工具 | A/B 真实实现 | 真实可用 |
| `src/commands/brief.ts` | `/brief` 切换命令 | B 外围真实实现 | 真实可用 |
| `src/tools/ScheduleCronTool/prompt.ts` | cron gate 与 prompt | B 外围真实实现 | 真实可用 |
| `src/hooks/useScheduledTasks.ts` | 定时任务调度 | B 外围真实实现 | 真实可用 |
| `src/bridge/initReplBridge.ts` | bridge 初始化 | B 外围真实实现 | 有 assistant 分支 |
| `src/commands/bridge/bridge.tsx` | bridge 控制命令 | B 外围真实实现 | 兼容 KAIROS perpetual 分支 |
| `src/bridge/bridgeMain.ts` | bridge 主逻辑 | B/C | 有大量 KAIROS 分支 |
| `src/entrypoints/agentSdkTypes.ts` | daemon / remote-control 类型 | B 外围真实实现 | 明示 daemon child 架构 |
| `src/memdir/memdir.ts` | assistant daily-log prompt | B 外围真实实现 | 真实可用 |
| `src/memdir/paths.ts` | daily log 路径规则 | B 外围真实实现 | 真实可用 |
| `src/state/AppStateStore.ts` | kairosEnabled 等状态 | C 接线 | 状态层已接好 |
| `src/bootstrap/state.ts` | kairosActive 等全局状态 | C 接线 | 状态层已接好 |

从这个表就能看出最核心的事实：

- **真正缺的是 `assistant/*` 内核**
- **而 KAIROS 的外围系统其实已经很完整**

---

## 5. 核心 stub 文件

### 5.1 `src/assistant/index.ts`

文件：`src/assistant/index.ts:1-8`

```ts
// Auto-generated stub — replace with real implementation
export const isAssistantMode: () => boolean = () => false;
export const initializeAssistantTeam: () => Promise<void> = async () => {};
export const markAssistantForced: () => void = () => {};
export const isAssistantForced: () => boolean = () => false;
export const getAssistantSystemPromptAddendum: () => string = () => '';
export const getAssistantActivationPath: () => string | undefined = () => undefined;
```

这是整个仓库里最关键的一份证据。

它说明：

- assistant 模式是否启用：**没实现**
- assistant team 初始化：**没实现**
- assistant 附加系统提示：**没实现**
- assistant 激活路径：**没实现**

因此，`claudecode-best` 虽然知道 KAIROS 需要这些能力，但并没有真正还原出其核心逻辑。

**判断：D Stub**

---

### 5.2 `src/assistant/gate.ts`

文件：`src/assistant/gate.ts:1-4`

```ts
// Auto-generated stub — replace with real implementation
export const isKairosEnabled: () => Promise<boolean> = () => Promise.resolve(false);
```

这个文件代表 KAIROS 的运行时资格校验或 gate，但它直接返回 `false`。

这意味着：

- 即便主流程已经接好
- 真实环境下是否能启用 KAIROS 的决策逻辑仍然缺失

**判断：D Stub**

---

### 5.3 `src/assistant/sessionDiscovery.ts`

文件：`src/assistant/sessionDiscovery.ts:1-4`

```ts
// Auto-generated stub — replace with real implementation
export type AssistantSession = { id: string; [key: string]: unknown };
export const discoverAssistantSessions: () => Promise<AssistantSession[]> = () => Promise.resolve([]);
```

这说明：

- `claude assistant [sessionId]` 所依赖的 session discovery 接口存在
- 但实际 discovery 根本没实现
- 所以 attach 到后台 session 的核心能力并没有真正完成

**判断：D Stub**

---

### 5.4 `src/commands/assistant/assistant.ts`

文件：`src/commands/assistant/assistant.ts:1-12`

```ts
// Auto-generated stub — replace with real implementation
...
export const NewInstallWizard ... = (() => null);
export const computeDefaultInstallDir: () => Promise<string> = (() => Promise.resolve(''));
```

这说明 `/assistant` 对应的安装/向导逻辑也还是占位。

也就是说：

- `main.tsx` 虽然能走到 install wizard 这条路径
- 但真正的 assistant 安装体验并没有实现出来

**判断：D Stub**

---

## 6. 主流程接线文件

### 6.1 `src/main.tsx`

这是 `claudecode-best` 里 KAIROS 最重要的“接线中心”。

#### 6.1.1 顶部接线

文件：`src/main.tsx:78-81`

```ts
const assistantModule = feature('KAIROS') ? require('./assistant/index.js') : null;
const kairosGate = feature('KAIROS') ? require('./assistant/gate.js') : null;
```

说明：

- 主流程明确支持 KAIROS
- assistantModule 和 gate 都被纳入主程序

#### 6.1.2 启动逻辑

文件：`src/main.tsx:1048-1086`

关键逻辑包括：

- `let kairosEnabled = false`
- `assistantModule.markAssistantForced()`
- `assistantModule?.isAssistantMode()`
- `kairosGate.isKairosEnabled()`
- `opts.brief = true`
- `setKairosActive(true)`
- `assistantModule.initializeAssistantTeam()`

这说明 KAIROS 的目标启动流程是完整存在的：

1. 判断 assistant mode
2. 走 gate
3. 打开 brief
4. 设置 kairos 状态
5. 初始化 assistant team

但注意：

- 这些调用的**目标实现是 stub**
- 所以这更像“完整流程骨架”而不是完整功能

#### 6.1.3 `claude assistant [sessionId]` viewer 路径

文件：`src/main.tsx:3259-3290`

这里有非常重要的注释：

```ts
// `claude assistant [sessionId]` — REPL as a pure viewer client
// of a remote assistant session.
```

并且还写到：

```ts
The daemon is starting up — run `claude assistant` again...
```

说明：

- 设计上 clearly 存在 daemon + viewer 模式
- 这部分架构意图在代码中被保留得非常完整
- 只是具体 assistant runtime 仍依赖 stub 模块

**判断：C 接线 + 部分真实逻辑**

它非常重要，但不能单独证明 KAIROS 已被完整复现。

---

### 6.2 `src/commands.ts`

文件：`src/commands.ts:62-72,101-102`

```ts
const proactive = feature('PROACTIVE') || feature('KAIROS') ? ...
const briefCommand = feature('KAIROS') || feature('KAIROS_BRIEF') ? ...
const assistantCommand = feature('KAIROS') ? ...
const subscribePr = feature('KAIROS_GITHUB_WEBHOOKS') ? ...
```

说明：

- KAIROS 相关命令的注册是完整的
- `/assistant` `/brief` `/proactive` `/subscribe-pr` 都接进来了

**判断：C 接线文件**

---

### 6.3 `src/tools.ts`

文件：`src/tools.ts:25-50`

```ts
const SleepTool = feature('PROACTIVE') || feature('KAIROS') ? ...
const SendUserFileTool = feature('KAIROS') ? ...
const PushNotificationTool = feature('KAIROS') || feature('KAIROS_PUSH_NOTIFICATION') ? ...
const SubscribePRTool = feature('KAIROS_GITHUB_WEBHOOKS') ? ...
```

说明：

- KAIROS 所需的工具池接线是成体系存在的
- 至少在工具装配层面，KAIROS 被当成一个完整模式在对待

**判断：C 接线文件**

---

## 7. 真正有实现价值的外围模块

### 7.1 `src/constants/prompts.ts`

文件：`src/constants/prompts.ts:72-85,844-861`

它做了几件关键事：

- 复用 `proactive/index.js`
- 接入 `BriefTool`
- 根据 `KAIROS` / `KAIROS_BRIEF` 决定系统提示段落
- 根据 `PROACTIVE || KAIROS` 构建 autonomous work 提示

这意味着：

- KAIROS 的 prompt 语义不是空壳
- 至少“模型应该如何在自治模式下行动”这件事，是有真实实现的

**判断：B 外围真实实现**

---

### 7.2 `src/tools/BriefTool/BriefTool.ts`

文件：`src/tools/BriefTool/BriefTool.ts:67-133`

这里是真实现，不是 stub。

它实现了：

- `isBriefEntitled()`
- `isBriefEnabled()`
- KAIROS / KAIROS_BRIEF gate
- `tengu_kairos_brief` GrowthBook 开关
- `getKairosActive()` 与 `getUserMsgOptIn()` 联动

特别关键的是：

```ts
Assistant mode (kairosActive) bypasses opt-in...
```

这证明 `claudecode-best` 里：

- Brief 逻辑是真实的
- 而且已经按 KAIROS 模式做了专门处理

**判断：A/B 真实实现**

---

### 7.3 `src/commands/brief.ts`

从 grep 结果可见，这个文件包含：

- `tengu_kairos_brief_config`
- `feature('KAIROS') || feature('KAIROS_BRIEF')`

它负责 `/brief` 命令的切换逻辑。

虽然本次没有全量展开，但从已有片段判断，它不是 stub，而是正常可工作的外围实现。

**判断：B 外围真实实现**

---

### 7.4 `src/tools/ScheduleCronTool/prompt.ts`

文件：`src/tools/ScheduleCronTool/prompt.ts:11-38`

这个文件是真实现，但和原始 Anthropic 版本相比，它做了一个“去 gate 化”的简化：

```ts
export function isKairosCronEnabled(): boolean {
  return !isEnvTruthy(process.env.CLAUDE_CODE_DISABLE_CRON)
}
```

也就是说：

- 在这个仓库里，cron 不再真正依赖 `feature('AGENT_TRIGGERS')`
- 它变成了一个只受环境变量控制的公开能力

这是一种典型的“为了让功能可跑起来而做的解锁式改造”。

**判断：B 外围真实实现**

---

### 7.5 `src/hooks/useScheduledTasks.ts`

文件：`src/hooks/useScheduledTasks.ts:53-92`

这里实现了：

- scheduler 的挂载
- `isKairosCronEnabled()` 检查
- 任务触发时把 prompt enqueue 回会话队列
- teammate cron 路由

这说明 KAIROS / proactive 所依赖的“定时唤醒能力”在这个仓库里是真正存在的。

**判断：B 外围真实实现**

---

### 7.6 `src/memdir/memdir.ts`

文件：`src/memdir/memdir.ts:319-348`

这里实现了 assistant-mode 的 daily-log memory prompt：

- 说明 assistant session 是 long-lived
- 新记忆写入按天命名的 append-only log
- 夜间 `/dream` 再蒸馏到 `MEMORY.md`

这不是文档，而是真正的 prompt 组装代码。

**判断：B 外围真实实现**

---

### 7.7 `src/memdir/paths.ts`

文件：`src/memdir/paths.ts:238-250`

这里把 daily log 的路径规则真正落地成：

- `<autoMemPath>/logs/YYYY/MM/YYYY-MM-DD.md`

说明 KAIROS 的长期记忆目录结构已经具备真实实现。

**判断：B 外围真实实现**

---

### 7.8 `src/bridge/initReplBridge.ts`

文件：`src/bridge/initReplBridge.ts:473-484`

```ts
if (feature('KAIROS')) {
  const { isAssistantMode } = require('../assistant/index.js')
  if (isAssistantMode()) {
    workerType = 'claude_code_assistant'
  }
}
```

这说明 bridge 层保留了 assistant 专有 worker type 的逻辑。

也就是说：

- 远程侧是知道 assistant session 和普通 session 不一样的
- 这一层 integration 不是假文档，而是代码路径中的真实分支

**判断：B 外围真实实现**

不过这里依赖的 `isAssistantMode()` 仍然来自 stub。

---

### 7.9 `src/commands/bridge/bridge.tsx`

从 grep 结果可见：

- 它考虑了 KAIROS perpetual 模式
- 会因为 assistant mode 而强制走特定 bridge 路径

这说明 KAIROS 的 remote attach / perpetual continuity 设计并不是只写在 README 里。

**判断：B 外围真实实现**

---

### 7.10 `src/entrypoints/agentSdkTypes.ts`

文件：`src/entrypoints/agentSdkTypes.ts:392-427`

这里明示：

- `src/assistant/daemonBridge.ts` 存在于设计中
- remote control handle 来自 daemon process
- daemon 在 parent 进程持有 websocket
- child agent 崩了可以重拉起

虽然 `daemonBridge.ts` 本体当前未展开，但这些类型和注释已经足以说明：

- 这个仓库保留了完整的 daemon-backed 架构设计
- 不是单纯猜测

**判断：B 外围真实实现 / 类型侧证据**

---

## 8. 状态层文件

### 8.1 `src/bootstrap/state.ts`

从 grep 结果可见，这里包含：

- `kairosActive`
- `getKairosActive()`
- `setKairosActive()`

说明 KAIROS 有单独的全局运行位。

**判断：C 接线文件**

---

### 8.2 `src/state/AppStateStore.ts`

grep 显示这里包含：

- `kairosEnabled`
- `claude assistant` remote session 状态
- remote background task count

这说明 UI 和状态机都已经把 assistant mode 当成一种独立运行形态。

**判断：C 接线文件**

---

## 9. README / CLAUDE.md 属于什么性质

### 9.1 `README.md`

这个文件的作用主要是：

- 给出 KAIROS flag 的用途说明
- 列出 SleepTool / SendUserFileTool / PushNotificationTool / SubscribePRTool
- 说明 `/assistant` `/brief` `/subscribe-pr` 等命令受 KAIROS 相关 flag 控制

它能证明“作者知道 KAIROS 是什么”，但不能证明功能真正可运行。

**判断：文档证据，不计入实现完成度**

### 9.2 `CLAUDE.md`

文件：`CLAUDE.md:89`

说明这个 decompiled 版本里 `feature()` 被 polyfill 成始终 `false`，因此 KAIROS 在默认构建下是关闭的。

这也解释了为什么这个仓库虽然保留了 KAIROS 代码路径，但默认并不会把它跑起来。

---

## 10. 最关键的判断：哪些地方“像复现”，哪些地方“不算复现”

### 可以算“已有较强复现价值”的部分

这些部分已经不仅是占位，而是有真实逻辑：

- KAIROS 与主程序的接线（`main.tsx`）
- KAIROS 命令/工具注册（`commands.ts`, `tools.ts`）
- Brief 机制（`BriefTool.ts`, `brief.ts`）
- Prompt 语义（`constants/prompts.ts`）
- Cron / scheduled tasks（`ScheduleCronTool/prompt.ts`, `useScheduledTasks.ts`）
- Memory daily-log 机制（`memdir.ts`, `paths.ts`）
- Bridge 的 assistant 分支（`initReplBridge.ts`, `bridge.tsx`, `bridgeMain.ts`）

这些模块合起来，已经足够让我们看清 KAIROS 的整体设计和大部分外围运行机制。

### 不能算“已完成复现”的关键缺口

真正卡住的是以下文件仍然是 stub：

- `src/assistant/index.ts`
- `src/assistant/gate.ts`
- `src/assistant/sessionDiscovery.ts`
- `src/commands/assistant/assistant.ts`

这几份文件正好对应了 assistant 内核最关键的能力：

- assistant mode 真正如何判定
- assistant team 真正如何初始化
- assistant session 如何发现
- assistant install / 启动 UI 如何执行

这说明：

> `claudecode-best` 已经把 KAIROS 的“壳”和“周边器官”做得很像了，但“大脑和心脏”仍然缺失。

---

## 11. 最终结论

如果用一句话评价 `claudecode-best` 中的 KAIROS 实现状态：

> 它不是零散提到 KAIROS，而是已经把 KAIROS 的主流程、外围能力、prompt 语义、bridge、memory、cron 等系统基本接齐了；但 assistant 核心模块仍然是 stub，因此它目前更像“高保真半复现工程”，而不是“真正跑通的 KAIROS 成品”。

再直白一点说：

- **有 KAIROS 吗？有。**
- **有独立文件和接线吗？有。**
- **有不少真实外围实现吗？有。**
- **assistant 内核是不是还空着？是。**
- **所以能不能算完整复现？不能。**

---

## 12. 适合如何使用这份仓库

如果你的目的不同，这个仓库的价值也不同：

### 12.1 如果你想理解 KAIROS 架构

它非常有价值，因为：

- 接线完整
- 外围模块多
- 能看清 prompt / tool / bridge / cron / memory 之间的关系

### 12.2 如果你想“直接跑起来一个 KAIROS assistant”

它还不够，因为 assistant 内核还是 stub。

### 12.3 如果你想自己复现 KAIROS

这个仓���非常适合作为骨架，优先补的就是：

1. `src/assistant/index.ts`
2. `src/assistant/gate.ts`
3. `src/assistant/sessionDiscovery.ts`
4. `src/commands/assistant/assistant.ts`

也就是把 assistant 核心 runtime 补上。

---

## 13. 推荐阅读顺序（最适合人工理解 KAIROS）

如果你不是要一次性把所有文件都读完，而是想用最短路径建立对 `claudecode-best` 中 KAIROS 的整体理解，我建议按下面顺序阅读。

### 第 1 组：先看“它是什么模式”

1. `src/main.tsx`
   - 看 KAIROS 在主程序中如何被接线、启用、切到 brief、进入 assistant viewer 模式。
2. `src/commands.ts`
   - 看哪些 slash command 归 KAIROS 管。
3. `src/tools.ts`
   - 看 KAIROS 需要哪些工具被挂进 tool pool。

这一组的目标不是看细节，而是先建立完整脑图：

> KAIROS 不是一个文件，而是一个横跨主流程、命令、工具池的运行模式。

### 第 2 组：再看“它怎么和模型交互”

4. `src/constants/prompts.ts`
   - 看 autonomous / proactive / brief 的系统提示是如何拼出来的。
5. `src/tools/BriefTool/BriefTool.ts`
   - 看为什么 KAIROS 会强绑定 brief，以及对用户输出的协议是什么。
6. `src/commands/brief.ts`
   - 看普通 brief 模式和 assistant mode 的关系。

这一组会让你理解：

> KAIROS 为什么不像普通 CLI 聊天，而更像“后台 agent 通过摘要跟用户沟通”。

### 第 3 组：再看“它怎么长期活着”

7. `src/tools/ScheduleCronTool/prompt.ts`
   - 看 cron 是否启用、调度语义是什么。
8. `src/hooks/useScheduledTasks.ts`
   - 看定时任务如何真正被注入回对话队列。
9. `src/memdir/memdir.ts`
   - 看 daily log memory prompt。
10. `src/memdir/paths.ts`
   - 看 memory daily log 路径规则。

这一组会告诉你：

> KAIROS 是如何获得“定时唤醒 + 长期记忆”能力的。

### 第 4 组：最后看“它怎么远程运行/附着”

11. `src/bridge/initReplBridge.ts`
12. `src/commands/bridge/bridge.tsx`
13. `src/bridge/bridgeMain.ts`
14. `src/entrypoints/agentSdkTypes.ts`

这一组适合最后读，因为它会把问题提升到：

- daemon
- remote-control
- websocket
- viewer client
- bridge session continuity

如果一开始就读这里，会比较容易陷进局部实现细节里。

---

## 14. 最值得优先补实现的 4 个文件

如果你的目标不是继续分析，而是把 `claudecode-best` 往“可运行 KAIROS”推进，那么优先级最高的不是继续改外围模块，而是先补下面 4 个文件。

### 14.1 `src/assistant/index.ts`

这是第一优先级。

原因：

- `isAssistantMode()` 决定整个模式是否切换
- `initializeAssistantTeam()` 决定 assistant 是否真的能带队
- `getAssistantSystemPromptAddendum()` 决定 assistant 是否有专属 system prompt
- `getAssistantActivationPath()` 决定 UI / 状态回显是否完整

不补它，整个 KAIROS 只能停留在“接线图”层面。

### 14.2 `src/assistant/gate.ts`

这是第二优先级。

原因：

- 它控制 KAIROS 能否真正启用
- `main.tsx` 已经依赖它
- 不补它，即使其他代码都在，也会卡在 `false`

### 14.3 `src/assistant/sessionDiscovery.ts`

这是第三优先级。

原因：

- `claude assistant [sessionId]` viewer 流程要靠它发现后台 session
- 不补它，attach 到后台 session 的主路径就无法真正工作

### 14.4 `src/commands/assistant/assistant.ts`

这是第四优先级。

原因：

- assistant install wizard / 初次安装路径都挂在这里
- 不补它，用户侧入口体验不完整

这四个文件的关系可以概括为：

- `index.ts`：运行内核
- `gate.ts`：启用闸门
- `sessionDiscovery.ts`：发现后台会话
- `assistant.ts`：用户入口

---

## 15. 一句最终判断

如果把 `claudecode-best` 里的 KAIROS 比作一台机器，那么现在的状态是：

- 机身、面板、线路、仪表、供电系统基本都在
- 但发动机和点火模块还是空壳

所以它非常适合做：

- 架构分析
- 设计逆向
- 二次复现的骨架工程

但还不适合直接宣称：

- “这就是一个可运行的 KAIROS 复刻版”
