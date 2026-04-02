# ULTRAPLAN 特性源码分析报告

## 1. 报告目的

本文基于 `claude-code-sourcemap` 中还原出的源码，分析 ULTRAPLAN 的实现原理、运行机制和关键设计点。

本文目标不是泛泛介绍，而是回答三个问题：

- 为什么需要这个特性（why）
- 这个特性到底是什么（what）
- 它在代码里是如何实现的（how）

另外，本文会补充 Python 复现时必须注意的工程细节，使开发者可以按本文的结构自行实现一个等价的原型。

## 2. 源码范围与结论

本次分析主要使用以下源码文件：

- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\commands.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\commands\ultraplan.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\utils\ultraplan\keyword.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\utils\ultraplan\ccrSession.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\utils\teleport.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\utils\processUserInput\processUserInput.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\components\PromptInput\PromptInput.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\components\permissions\ExitPlanModePermissionRequest\ExitPlanModePermissionRequest.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\screens\REPL.tsx`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\state\AppStateStore.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\state\onChangeAppState.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\entrypoints\sdk\controlSchemas.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\constants\xml.ts`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\claude-code-sourcemap\restored-src\src\tasks\RemoteAgentTask\RemoteAgentTask.tsx`

结论很明确：ULTRAPLAN 不是一个简单的命令别名，也不是普通的远程执行。它是一个“远程规划专用会话模式”，特点包括：

1. 从本地 CLI 或输入关键字触发
2. 在 Claude Code on the web 中创建远程会话
3. 远程会话一开始就被置为 `plan` 权限模式
4. 本地持续轮询远程事件流，而不是阻塞等待
5. 当远程会话产出并经过用户审批后，本地得到一个正式 plan
6. 这个 plan 可以继续留在远程执行，也可以传回本地执行

因此，ULTRAPLAN 的本质是：

> 把“高成本、长耗时、需要审批的规划阶段”从本地会话中剥离出来，交给远程会话完成，并在本地只保留状态跟踪、审批承接和结果接收。

---

## 3. What：ULTRAPLAN 是什么

从命令注册可以直接看出，它是一个独立命令，并受特性开关控制。

### 3.1 命令注册

文件：`src/commands.ts:104-106`

```ts
const ultraplan = feature('ULTRAPLAN')
  ? require('./commands/ultraplan.js').default
  : null
```

以及：`src/commands.ts:239`

```ts
...(ultraplan ? [ultraplan] : []),
```

这说明它不是普通 prompt 分支，而是正式命令模块。

### 3.2 命令说明

文件：`src/commands/ultraplan.tsx:461-470`

```ts
export default {
  type: 'local-jsx',
  name: 'ultraplan',
  description: `~10–30 min · Claude Code on the web drafts an advanced plan you can edit and approve. See ${CCR_TERMS_URL}`,
  argumentHint: '<prompt>',
  isEnabled: () => "external" === 'ant',
  load: () => Promise.resolve({
    call
  })
} satisfies Command;
```

从这段定义可以抽出几个事实：

- ULTRAPLAN 是本地 JSX 命令，不是纯文本命令
- 它的主要工作场所是网页端的 Claude Code on the web
- 它的产物是“可编辑、可审批的计划”
- 它不是通用执行模式，而是专门的“高级规划模式”

### 3.3 远程会话中的专有标记

文件：`src/constants/xml.ts:40-41`

```ts
// XML tag names for ultraplan mode (remote parallel planning sessions)
export const ULTRAPLAN_TAG = 'ultraplan'
```

这说明远程输出里有专门的 `<ultraplan>...</ultraplan>` 标签语义，供本地提取计划内容使用。

---

## 4. Why：为什么需要 ULTRAPLAN

源码中的注释已经说明了设计动机，主要有四点。

### 4.1 长规划不适合阻塞本地终端

文件：`src/commands/ultraplan.tsx:23-25`

```ts
// Multi-agent exploration is slow; 30min timeout.
const ULTRAPLAN_TIMEOUT_MS = 30 * 60 * 1000;
```

这说明作者直接承认：多智能体规划很慢，可能运行 30 分钟。对于本地 CLI，这会带来两个问题：

- 终端被长时间占用
- 本地对话上下文会越来越重

ULTRAPLAN 的解决方式是把规划移到远程，只让本地维持“状态机”和“结果承接”。

### 4.2 规划和执行应该分离

文件：`src/commands/ultraplan.tsx:100-137` 显示了两种不同的后续路径：

- 继续在远程执行
- 把计划传回本地，再由本地决定如何执行

这说明 ULTRAPLAN 不是“远程替你写代码”的唯一入口，而是先把规划阶段独立出来，执行可以另选。

### 4.3 需要用户审批，而不是自动推进

文件：`src/utils/ultraplan/ccrSession.ts:190-197`

```ts
// Returns the approved plan text and where the user wants it executed.
// 'approved' scrapes from the "## Approved Plan:" marker ...
// 'teleport' scrapes from the ULTRAPLAN_TELEPORT_SENTINEL in a deny tool_result ...
// browser sends a rejection so the remote stays in plan mode, with the plan
// text embedded in the feedback.
```

这里说明了一个关键设计：

- 远程会话不是自动把 plan 推回本地
- 用户会在浏览器里审批 plan
- 审批结果决定 plan 的落点和执行地点

### 4.4 需要保留本地工作自由度

文件：`src/commands/ultraplan.tsx:189-190`

```ts
return `${DIAMOND_OPEN} ultraplan · Monitor progress in Claude Code on the web ${url}
You can continue working ...`
```

这句文案不是装饰，而是架构目标：

> 本地用户在远程规划期间可以继续干别的事。

这是一种典型的“前台轻状态、后台长任务”设计。

---

## 5. How：整体实现架构

ULTRAPLAN 的实现可以拆成 7 个子系统：

1. 入口层：slash command 和关键字触发
2. UI 层：输入高亮、启动对话框、审批后选择对话框
3. 启动层：构造 prompt，检查前置条件，发起远程会话
4. 远程会话初始化层：把远程会话直接置为 `plan` 模式，并写入 `ultraplan` 标记
5. 状态同步层：本地 AppState 与远程 external metadata 同步
6. 轮询层：持续读取远程事件流，识别 plan 是否已准备、是否等待用户输入、是否结束
7. 收尾层：远程继续执行、本地接管执行、失败归档、手动停止

下面逐层展开。

---

## 6. 入口层：从哪里触发 ULTRAPLAN

### 6.1 Slash 命令触发

文件：`src/commands/ultraplan.tsx:411-459`

```ts
const call: LocalJSXCommandCall = async (onDone, context, args) => {
  const blurb = args.trim();

  if (!blurb) {
    const msg = await launchUltraplan({
      blurb,
      getAppState: context.getAppState,
      setAppState: context.setAppState,
      signal: context.abortController.signal
    });
    onDone(msg, {
      display: 'system'
    });
    return null;
  }

  const {
    ultraplanSessionUrl: active,
    ultraplanLaunching
  } = context.getAppState();
  if (active || ultraplanLaunching) {
    onDone(buildAlreadyActiveMessage(active), {
      display: 'system'
    });
    return null;
  }

  context.setAppState(prev => ({
    ...prev,
    ultraplanLaunchPending: {
      blurb
    }
  }));
  onDone(undefined, {
    display: 'skip'
  });
  return null;
};
```

行为非常清楚：

- `/ultraplan <prompt>` 先进入本地流程
- 若已有活跃会话或正在启动，直接拒绝重复启动
- 否则设置 `ultraplanLaunchPending`，弹出启动确认对话框

### 6.2 关键字触发

文件：`src/utils/processUserInput/processUserInput.ts:455-493`

```ts
if (
  feature('ULTRAPLAN') &&
  mode === 'prompt' &&
  !context.options.isNonInteractiveSession &&
  inputString !== null &&
  !effectiveSkipSlash &&
  !inputString.startsWith('/') &&
  !context.getAppState().ultraplanSessionUrl &&
  !context.getAppState().ultraplanLaunching &&
  hasUltraplanKeyword(preExpansionInput ?? inputString)
) {
  logEvent('tengu_ultraplan_keyword', {})
  const rewritten = replaceUltraplanKeyword(inputString).trim()
  const { processSlashCommand } = await import('./processSlashCommand.js')
  const slashResult = await processSlashCommand(
    `/ultraplan ${rewritten}`,
    ...
  )
  return addImageMetadataMessage(slashResult, imageMetadataTexts)
}
```

这段代码表明：

- 用户并不一定非要输入 `/ultraplan`
- 只要普通对话里出现可触发的 `ultraplan` 关键字，本地就会自动改写成 `/ultraplan ...`
- 这个能力只在交互式 prompt 模式下生效，不在 headless 模式下生效

### 6.3 关键字识别不是简单字符串搜索

文件：`src/utils/ultraplan/keyword.ts:46-99`

```ts
function findKeywordTriggerPositions(
  text: string,
  keyword: string,
): TriggerPosition[] {
  const re = new RegExp(keyword, 'i')
  if (!re.test(text)) return []
  if (text.startsWith('/')) return []
  ...
}

export function findUltraplanTriggerPositions(text: string): TriggerPosition[] {
  return findKeywordTriggerPositions(text, 'ultraplan')
}
```

同文件 `13-45` 行的注释还明确列出了排除规则：

- 不在引号、反引号、括号、标签里触发
- 不在路径或标识符上下文里触发，如 `src/ultraplan/foo.ts`、`ultraplan.tsx`
- 跟着 `?` 时不触发，因为那通常是在“问这个功能是什么”
- 以 `/` 开头的整句不触发，因为那已经是 slash command 语境

这是一个很重要的工程点：

> ULTRAPLAN 关键字触发器不是语义理解，而是“非常克制的文本触发器”。

这使其容易复现，也更可控。

### 6.4 输入框高亮只是提示，不是执行

文件：`src/components/PromptInput/PromptInput.tsx:520-523`

```ts
const ultraplanSessionUrl = useAppState(s => s.ultraplanSessionUrl);
const ultraplanLaunching = useAppState(s => s.ultraplanLaunching);
const ultraplanTriggers = useMemo(() => feature('ULTRAPLAN') && !ultraplanSessionUrl && !ultraplanLaunching ? findUltraplanTriggerPositions(displayedValue) : [], [displayedValue, ultraplanSessionUrl, ultraplanLaunching]);
```

输入框会根据 `findUltraplanTriggerPositions` 做高亮，但只在以下情况下高亮：

- 特性开启
- 当前没有活跃 ULTRAPLAN 会话
- 当前不处于启动中

这说明高亮只是前端提示层，真正执行仍由 `processUserInput.ts` 完成。

---

## 7. UI 层：为什么需要两个对话框

ULTRAPLAN 在 REPL 中至少有两个对话框状态：

- `ultraplan-launch`
- `ultraplan-choice`

文件：`src/screens/REPL.tsx:2017-2038`

```ts
function getFocusedInputDialog(): ... | 'ultraplan-choice' | 'ultraplan-launch' | undefined {
  ...
  if (feature('ULTRAPLAN') && allowDialogsWithAnimation && !isLoading && ultraplanPendingChoice) return 'ultraplan-choice';
  if (feature('ULTRAPLAN') && allowDialogsWithAnimation && !isLoading && ultraplanLaunchPending) return 'ultraplan-launch';
}
```

文件：`src/screens/REPL.tsx:4850-4852`

```tsx
{feature('ULTRAPLAN') ? focusedInputDialog === 'ultraplan-choice' && ultraplanPendingChoice && <UltraplanChoiceDialog ... /> : null}
{feature('ULTRAPLAN') ? focusedInputDialog === 'ultraplan-launch' && ultraplanLaunchPending && <UltraplanLaunchDialog ... /> : null}
```

这两个对话框分别负责不同阶段：

### 7.1 启动前对话框

作用：

- 确认是否真的要发起远程规划
- 可能承接一些前置说明，如 Terms、断开 remote control 等

### 7.2 计划审批后的选择对话框

作用：

- 远程规划已经结束，并且 plan 已经被用户认可
- 此时用户决定：是继续在远程执行，还是把 plan 传回本地执行

这两个阶段不要混在一个弹窗里。源码选择分开，是因为：

- 启动决策和执行地点决策不是一回事
- 第二个决策要等待远程会话真的产出 plan 之后才能发生

---

## 8. 启动层：launchUltraplan 做了什么

### 8.1 重复启动保护

文件：`src/commands/ultraplan.tsx:260-283`

```ts
const {
  ultraplanSessionUrl: active,
  ultraplanLaunching
} = getAppState();
if (active || ultraplanLaunching) {
  ...
  return buildAlreadyActiveMessage(active);
}

setAppState(prev => prev.ultraplanLaunching ? prev : {
  ...prev,
  ultraplanLaunching: true
});
```

这里用了两个状态位：

- `ultraplanSessionUrl`：代表远程会话已经真正存在
- `ultraplanLaunching`：代表正在从本地发起远程会话，但 URL 还没拿到

这是一个细节很重要的设计。只检查 `ultraplanSessionUrl` 不够，因为在 `teleportToRemote()` 的数秒时间窗口里，URL 尚未设置，用户可能重复触发。加上 `ultraplanLaunching` 就能挡住这个竞态。

### 8.2 启动流程放到 detached 任务里

文件：`src/commands/ultraplan.tsx:284-292`

```ts
void launchDetached({
  blurb,
  seedPlan,
  getAppState,
  setAppState,
  signal,
  onSessionReady
});
return buildLaunchMessage(disconnectedBridge);
```

这意味着：

- 用户先立即得到“已开始启动”的反馈
- 真正耗时的远程创建在后台跑
- 本地 REPL 不被阻塞

这个模式非常适合 Python 复现：

- 前台函数立即返回状态消息
- 后台协程负责创建远程 session、注册任务、轮询事件

---

## 9. Prompt 构造：ULTRAPLAN 给远程会话喂了什么

### 9.1 Prompt 的组成

文件：`src/commands/ultraplan.tsx:63-72`

```ts
export function buildUltraplanPrompt(blurb: string, seedPlan?: string): string {
  const parts: string[] = [];
  if (seedPlan) {
    parts.push('Here is a draft plan to refine:', '', seedPlan, '');
  }
  parts.push(ULTRAPLAN_INSTRUCTIONS);
  if (blurb) {
    parts.push('', blurb);
  }
  return parts.join('\n');
}
```

Prompt 由三部分组成：

1. 可选的 `seedPlan`
2. 固定的 `ULTRAPLAN_INSTRUCTIONS`
3. 用户输入的 `blurb`

### 9.2 为什么源码特意避免在 prompt 里裸写 “ultraplan”

文件：`src/commands/ultraplan.tsx:36-43`

```ts
// Phrasing deliberately avoids the feature name because
// the remote CCR CLI runs keyword detection on raw input before
// any tag stripping, and a bare "ultraplan" in the prompt would self-trigger as
// /ultraplan, which is filtered out of headless mode as "Unknown skill"
```

这是复现时最容易忽略、但非常关键的一点：

> 远程环境自己也有关键字检测。如果 prompt 文本本身带了 `ultraplan`，可能在远程侧再次触发 `/ultraplan`，形成错误递归或未知技能错误。

所以作者明确要求：

- prompt 内部描述这个模式时，避免裸用关键字名
- 这不是文案问题，而是防止触发器误伤

Python 复现时必须保留这个约束。

---

## 10. 远程会话创建：teleportToRemote 是核心桥接点

### 10.1 调用方式

文件：`src/commands/ultraplan.tsx:328-341`

```ts
const session = await teleportToRemote({
  initialMessage: prompt,
  description: blurb || 'Refine local plan',
  model,
  permissionMode: 'plan',
  ultraplan: true,
  signal,
  useDefaultEnvironment: true,
  onBundleFail: msg => {
    bundleFailMsg = msg;
  }
});
```

这个调用已经把 ULTRAPLAN 的模式信息全塞进去了：

- `initialMessage`: 远程第一条用户消息
- `description`: 用于命名 session / branch
- `model`: 专门的 ultraplan 模型
- `permissionMode: 'plan'`: 远程一开始就是 plan 模式
- `ultraplan: true`: 远程会话被打上 ultraplan 标记
- `useDefaultEnvironment: true`: 运行在默认远程环境中

### 10.2 `teleportToRemote` 的参数定义

文件：`src/utils/teleport.tsx:730-742`

```ts
export async function teleportToRemote(options: {
  initialMessage: string | null;
  branchName?: string;
  title?: string;
  description?: string;
  model?: string;
  permissionMode?: PermissionMode;
  ultraplan?: boolean;
  signal: AbortSignal;
  useDefaultEnvironment?: boolean;
  ...
}): Promise<TeleportToRemoteResponse | null> {
```

这说明 `ultraplan` 不是松散字段，而是 `teleportToRemote` 的正式参数之一。

### 10.3 远程创建时把权限模式作为 control_request 注入

文件：`src/utils/teleport.tsx:1117-1138`

```ts
// CreateCCRSessionPayload has no permission_mode field — a top-level
// body entry is silently dropped by the proto parser server-side.
// Instead prepend a set_permission_mode control_request event. Initial
// events are written to threadstore before the container connects, so
// the CLI applies the mode before the first user turn — no readiness race.
const events: Array<{
  type: 'event';
  data: Record<string, unknown>;
}> = [];
if (options.permissionMode) {
  events.push({
    type: 'event',
    data: {
      type: 'control_request',
      request_id: `set-mode-${randomUUID()}`,
      request: {
        subtype: 'set_permission_mode',
        mode: options.permissionMode,
        ultraplan: options.ultraplan
      }
    }
  });
}
```

这是 ULTRAPLAN 的实现核心之一。

重点如下：

1. 服务端 CreateSession API 本身没有 `permission_mode` 顶层字段
2. 如果直接在 session 创建参数里塞，会被服务端忽略
3. 正确做法是：在初始事件序列里先写入一条 `control_request`
4. 这样容器一连上，就先读到模式变更，而不是先进入默认模式

这解决的是一个非常具体的竞态问题：

> 远程会话第一轮就必须处于 plan 模式，否则它可能先按默认模式走一轮，再切到 plan，导致行为错乱。

对于 Python 复现，这个点必须原样保留。

### 10.4 ULTRAPLAN 会话标题也会带标记

文件：`src/utils/teleport.tsx:1155-1157`

```ts
const requestBody = {
  title: options.ultraplan ? `ultraplan: ${sessionTitle}` : sessionTitle,
  events,
  session_context: sessionContext,
  environment_id: environmentId
};
```

这不是决定性机制，但有两个用处：

- 便于用户识别该远程会话是 ULTRAPLAN 会话
- 便于后台和分析系统区分会话类型

---

## 11. 远程会话状态同步：为什么还要同步 `is_ultraplan_mode`

### 11.1 协议层 schema

文件：`src/entrypoints/sdk/controlSchemas.ts:124-134`

```ts
export const SDKControlSetPermissionModeRequestSchema = lazySchema(() =>
  z
    .object({
      subtype: z.literal('set_permission_mode'),
      mode: PermissionModeSchema(),
      ultraplan: z
        .boolean()
        .optional()
        .describe('@internal CCR ultraplan session marker.'),
    })
```

说明：

- `ultraplan` 是 `set_permission_mode` 请求的一部分
- 不是任意 metadata，而是权限模式切换协议里的专用标记

### 11.2 AppState 到外部 metadata 的同步

文件：`src/state/onChangeAppState.ts:77-89`

```ts
const isUltraplan =
  newExternal === 'plan' &&
  newState.isUltraplanMode &&
  !oldState.isUltraplanMode
    ? true
    : null
notifySessionMetadataChanged({
  permission_mode: newExternal,
  is_ultraplan_mode: isUltraplan,
})
```

注释里写得很清楚：

- Ultraplan 只标记第一次进入 plan cycle
- 用 `null` 表示移除该 key

这说明作者不想让“普通 plan 模式”和“ULTRAPLAN 的第一轮 plan 模式”混淆。

### 11.3 元数据回灌到本地状态

文件：`src/state/onChangeAppState.ts:24-39`

```ts
export function externalMetadataToAppState(
  metadata: SessionExternalMetadata,
): (prev: AppState) => AppState {
  return prev => ({
    ...prev,
    ...(typeof metadata.permission_mode === 'string' ? { ... } : {}),
    ...(typeof metadata.is_ultraplan_mode === 'boolean'
      ? { isUltraplanMode: metadata.is_ultraplan_mode }
      : {}),
  })
}
```

这保证：

- 本地和远程对“当前是否处于 ultraplan 模式”认识一致
- UI 可以根据这个值显示对应状态

---

## 12. 任务与状态：ULTRAPLAN 在本地如何表示

文件：`src/state/AppStateStore.ts:428-445`

```ts
// Set synchronously in launchUltraplan before the detached flow starts.
// Prevents duplicate launches during the ~5s window before
// ultraplanSessionUrl is set by teleportToRemote.
ultraplanLaunching?: boolean

// Active ultraplan CCR session URL. Set while the RemoteAgentTask runs;
// truthy disables the keyword trigger + rainbow. Cleared when the poll
// reaches terminal state.
ultraplanSessionUrl?: string

// Approved ultraplan awaiting user choice (implement here vs fresh session).
ultraplanPendingChoice?: { plan: string; sessionId: string; taskId: string }

// Pre-launch permission dialog.
ultraplanLaunchPending?: { blurb: string }

// Remote-harness side: set via set_permission_mode control_request,
// pushed to CCR external_metadata.is_ultraplan_mode by onChangeAppState.
isUltraplanMode?: boolean
```

这些字段的职责分工很清晰：

- `ultraplanLaunching`：防重入
- `ultraplanSessionUrl`：标记活跃远程会话
- `ultraplanPendingChoice`：plan 已回到本地，等待用户决定去哪执行
- `ultraplanLaunchPending`：启动弹窗数据
- `isUltraplanMode`：远程 harness / metadata 同步标记

Python 复现时最好直接照着这个结构建一个状态对象。

---

## 13. 轮询层：为什么 ULTRAPLAN 不是简单地“等返回”

ULTRAPLAN 的重点不只是远程启动，而是本地如何知道远程已经产出 plan。

作者没有用“单次 await 直到结束”，而是自己写了一个事件流轮询器。

### 13.1 轮询间隔与失败容忍

文件：`src/utils/ultraplan/ccrSession.ts:21-24`

```ts
const POLL_INTERVAL_MS = 3000
const MAX_CONSECUTIVE_FAILURES = 5
```

这意味着：

- 每 3 秒轮询一次
- 短暂网络抖动不会立即让任务失败
- 连续 5 次失败才真正中止

这很适合远程网页会话场景。

### 13.2 轮询返回的数据结构

文件：`src/utils/teleport.tsx:621-626`

```ts
export type PollRemoteSessionResponse = {
  newEvents: SDKMessage[];
  lastEventId: string | null;
  branch?: string;
  sessionStatus?: 'idle' | 'running' | 'requires_action' | 'archived';
};
```

文件：`src/utils/teleport.tsx:633-714` 定义了 `pollRemoteSessionEvents()`。

核心行为：

- 增量读取远程 session events
- 维护 `after_id` 游标
- 过滤掉 `env_manager_log` 和 `control_response`
- 可选获取会话 metadata，包括 `sessionStatus`

这说明 ULTRAPLAN 的轮询不是简单抓日志，而是结构化抓事件流。

### 13.3 远程事件扫描器

文件：`src/utils/ultraplan/ccrSession.ts:80-180`

```ts
export class ExitPlanModeScanner {
  private exitPlanCalls: string[] = []
  private results = new Map<string, ToolResultBlockParam>()
  private rejectedIds = new Set<string>()
  private terminated: { subtype: string } | null = null
  private rescanAfterRejection = false
  everSeenPending = false
  ...
}
```

这个类的职责不是请求网络，而是：

- 接受一批批 `SDKMessage[]`
- 找出 `ExitPlanMode` 工具调用和它对应的 `tool_result`
- 判断当前 plan 的状态：待审批、被拒绝、已批准、远程已终止

这是个很好的分层：

- 网络轮询和状态判定分开
- 这样状态判定类可以独立做单元测试

源码也明确写了这一点。

文件：`src/utils/ultraplan/ccrSession.ts:68-79`

```ts
/**
 * Pure stateful classifier for the CCR event stream.
 * Ingests SDKMessage[] batches ... No I/O, no timers
 */
```

对于 Python 复现，这个分层必须保留。

---

## 14. 轮询层的核心逻辑：如何判断 plan 已经准备好

### 14.1 识别 ExitPlanMode tool_use

文件：`src/utils/ultraplan/ccrSession.ts:101-118`

```ts
if (m.type === 'assistant') {
  for (const block of m.message.content) {
    if (block.type !== 'tool_use') continue
    const tu = block as ToolUseBlock
    if (tu.name === EXIT_PLAN_MODE_V2_TOOL_NAME) {
      this.exitPlanCalls.push(tu.id)
    }
  }
} else if (m.type === 'user') {
  const content = m.message.content
  if (!Array.isArray(content)) continue
  for (const block of content) {
    if (block.type === 'tool_result') {
      this.results.set(block.tool_use_id, block)
    }
  }
}
```

关键事实：

- `ExitPlanMode` 是 assistant 发出的 tool_use
- 对应审批结果体现在 user 侧的 `tool_result`
- 本地通过 `tool_use_id` 把它们关联起来

### 14.2 状态优先级设计

文件：`src/utils/ultraplan/ccrSession.ts:74-79`

```ts
 * Precedence (approved > terminated > rejected > pending > unchanged)
```

这行注释非常重要。它解释了为什么同一批事件里可能同时包含多个状态，但最终要按固定优先级取结果。

比如：

- 同一批里既有 approved plan，又有后续远程报错
- 这时 approved plan 仍然有效，不能因为后面的报错把 plan 丢掉

这就是源码里写的：`approved > terminated`。

这条规则 Python 复现必须严格照搬。

---

## 15. Plan 提取机制：批准与传回本地是两条路径

这是 ULTRAPLAN 最有特点的部分。

### 15.1 远程继续执行路径

文件：`src/utils/ultraplan/ccrSession.ts:331-348`

```ts
// Plan is echoed in tool_result content as "## Approved Plan:\n<text>" or
// "## Approved Plan (edited by user):\n<text>" (ExitPlanModeV2Tool).
function extractApprovedPlan(content: ToolResultBlockParam['content']): string {
  const text = contentToText(content)
  const markers = [
    '## Approved Plan (edited by user):\n',
    '## Approved Plan:\n',
  ]
  for (const marker of markers) {
    const idx = text.indexOf(marker)
    if (idx !== -1) {
      return text.slice(idx + marker.length).trimEnd()
    }
  }
  throw new Error(...)
}
```

这里说明：

- 远程审批通过时，plan 会以文本块形式回显在 `tool_result` 中
- 本地并不是去抓某个 plan 文件，而是抓 `tool_result` 中的 marker 段
- 同时兼容“用户改过计划”和“用户没改计划”两种 marker

### 15.2 传回本地执行路径

文件：`src/utils/ultraplan/ccrSession.ts:48`

```ts
export const ULTRAPLAN_TELEPORT_SENTINEL = '__ULTRAPLAN_TELEPORT_LOCAL__'
```

文件：`src/utils/ultraplan/ccrSession.ts:318-329`

```ts
function extractTeleportPlan(
  content: ToolResultBlockParam['content'],
): string | null {
  const text = contentToText(content)
  const marker = `${ULTRAPLAN_TELEPORT_SENTINEL}\n`
  const idx = text.indexOf(marker)
  if (idx === -1) return null
  return text.slice(idx + marker.length).trimEnd()
}
```

这条路径的设计非常巧妙：

- 如果用户希望“把 plan 传回终端执行”
- 浏览器侧并不是发一个新的成功结果
- 而是通过 deny / reject 路径，把 plan 文本连同一个 sentinel 一起嵌入反馈
- 本地 scanner 看到 sentinel，就把它解释为“传回本地执行”，而不是普通拒绝

也就是说，源码把“拒绝当前远程执行”复用了为“把批准的计划传回本地”。

这让协议不需要额外新增一个新消息类型，只靠已有 `tool_result` 就能表达两种结果。

这是非常值得复现的设计。

---

## 16. 轮询结果如何转换为本地行为

文件：`src/utils/ultraplan/ccrSession.ts:253-265`

```ts
if (result.kind === 'approved') {
  return {
    plan: result.plan,
    rejectCount: scanner.rejectCount,
    executionTarget: 'remote',
  }
}
if (result.kind === 'teleport') {
  return {
    plan: result.plan,
    rejectCount: scanner.rejectCount,
    executionTarget: 'local',
  }
}
```

这一步把复杂的事件流最终压缩成简单结构：

- `plan`
- `rejectCount`
- `executionTarget`

这是业务层最需要的最小结果。

### 16.1 本地 `startDetachedPoll()` 的处理

文件：`src/commands/ultraplan.tsx:79-138`

```ts
const {
  plan,
  rejectCount,
  executionTarget
} = await pollForApprovedExitPlanMode(...)
...
if (executionTarget === 'remote') {
  ...
  status: 'completed'
  ...
  ultraplanSessionUrl: undefined
  ...
} else {
  setAppState(prev => {
    ...
    ultraplanPendingChoice: {
      plan,
      sessionId,
      taskId
    }
  })
}
```

即：

- 若 `executionTarget === 'remote'`，本地只做收尾和通知
- 若 `executionTarget === 'local'`，本地把 plan 放入 `ultraplanPendingChoice`，等待用户在本地选择下一步

---

## 17. 轮询阶段状态机：running、needs_input、plan_ready

文件：`src/utils/ultraplan/ccrSession.ts:58-66`

```ts
/**
 * Pill/detail-view state derived from the event stream. Transitions:
 *   running → (turn ends, no ExitPlanMode) → needs_input
 *   needs_input → (user replies in browser) → running
 *   running → (ExitPlanMode emitted, no result yet) → plan_ready
 *   plan_ready → (rejected) → running
 *   plan_ready → (approved) → poll resolves, pill removed
 */
export type UltraplanPhase = 'running' | 'needs_input' | 'plan_ready'
```

这说明 ULTRAPLAN 并不是二元状态，而是三态：

- `running`: 远程还在继续工作
- `needs_input`: 远程停下来等用户回答
- `plan_ready`: 远程已经调用 ExitPlanMode，正在等审批结果

### 17.1 阶段判定逻辑

文件：`src/utils/ultraplan/ccrSession.ts:274-295`

```ts
const quietIdle =
  (sessionStatus === 'idle' || sessionStatus === 'requires_action') &&
  newEvents.length === 0
const phase: UltraplanPhase = scanner.hasPendingPlan
  ? 'plan_ready'
  : quietIdle
    ? 'needs_input'
    : 'running'
if (phase !== lastPhase) {
  ...
  onPhaseChange?.(phase)
}
```

这里有两个实现细节值得特别注意：

1. `plan_ready` 优先于 `needs_input`
   - 因为一旦 ExitPlanMode 已发出，最重要的是 plan 正在等审批

2. `idle` 不是一看到就信，必须 `newEvents.length === 0`
   - 源码注释解释：会话可能在 tool turn 之间短暂显示 idle
   - 如果此时还有新事件流入，说明它其实还在工作，不能误判为等输入

这是一个非常成熟的远程状态判定细节。

---

## 18. 失败与停止：远程会话怎么收尾

### 18.1 归档而不是强删

文件：`src/utils/teleport.tsx:1193-1200`

```ts
 * Best-effort session archive. POST /v1/sessions/{id}/archive has no
 * running-status check (unlike DELETE which 409s on RUNNING), so it works
 * mid-implementation. Archived sessions reject new events (send_events.go),
 * so the remote stops on its next write. 409 (already archived) treated as
 * success.
export async function archiveRemoteSession(sessionId: string): Promise<void> {
```

这是另一个很重要的工程决策。

作者没有直接删除远程会话，而是选择 archive，原因很实际：

- DELETE 在运行中的会话上可能失败
- archive 可以中途执行
- 会话被 archive 后，后续新事件会被拒收，远程自然会停下来

这种做法比“硬杀”更适合远程规划任务。

### 18.2 归档请求实现

文件：`src/utils/teleport.tsx:1200-1218`

```ts
export async function archiveRemoteSession(sessionId: string): Promise<void> {
  const accessToken = getClaudeAIOAuthTokens()?.accessToken;
  if (!accessToken) return;
  ...
  const url = `${getOauthConfig().BASE_API_URL}/v1/sessions/${sessionId}/archive`;
  try {
    const resp = await axios.post(url, {}, {
      headers,
      timeout: 10000,
      validateStatus: s => s < 500
    });
    if (resp.status === 200 || resp.status === 409) {
      logForDebugging(`[archiveRemoteSession] archived ${sessionId}`);
    }
```

这里还说明：

- 409 也视为成功
- 因为它通常表示“已经归档过了”

### 18.3 用户主动停止

文件：`src/commands/ultraplan.tsx:196-223`

```ts
export async function stopUltraplan(taskId: string, sessionId: string, setAppState: ...): Promise<void> {
  await RemoteAgentTask.kill(taskId, setAppState);
  setAppState(prev => ... {
    ultraplanSessionUrl: undefined,
    ultraplanPendingChoice: undefined,
    ultraplanLaunching: undefined
  })
  const url = getRemoteSessionUrl(sessionId, process.env.SESSION_INGRESS_URL);
  enqueuePendingNotification({
    value: `Ultraplan stopped.\n\nSession: ${url}`,
    mode: 'task-notification'
  });
}
```

停止逻辑做了三件事：

- kill 本地任务
- 清理所有本地 ultraplan 状态
- 给用户留一个可查看的 session URL

这意味着停止并不一定马上把远端完全销毁，但本地会先解除绑定。

---

## 19. ULTRAPLAN 与普通远程任务的关系

从源码上看，ULTRAPLAN 并不是完全独立于 remote task 基础设施，而是在其上加了定制逻辑。

### 19.1 注册为 `RemoteAgentTask`

文件：`src/commands/ultraplan.tsx:364-382`

```ts
const { taskId } = registerRemoteAgentTask({
  remoteTaskType: 'ultraplan',
  session: {
    id: session.id,
    title: blurb || 'Ultraplan'
  },
  command: blurb,
  context: {
    abortController: new AbortController(),
    getAppState,
    setAppState
  },
  isUltraplan: true
});
startDetachedPoll(taskId, session.id, url, getAppState, setAppState);
```

因此：

- ULTRAPLAN 复用了远程任务基础设施
- 但 plan 提取、审批和状态机是专门写的，不是通用 remote task 流程

### 19.2 从日志提取计划

文件：`src/tasks/RemoteAgentTask/RemoteAgentTask.tsx:204-217`

```ts
/**
 * Extract the plan content from the remote session log.
 * Searches all assistant messages for <ultraplan>...</ultraplan> tags.
 */
export function extractPlanFromLog(log: SDKMessage[]): string | null {
  for (let i = log.length - 1; i >= 0; i--) {
    const msg = log[i];
    if (msg?.type !== 'assistant') continue;
    const fullText = extractTextContent(msg.message.content, '\n');
    const plan = extractTag(fullText, ULTRAPLAN_TAG);
    if (plan?.trim()) return plan.trim();
  }
  return null;
}
```

这说明在更通用的 remote task 系统里，也保留了对 `<ultraplan>` 标签的理解能力。

也就是说，ULTRAPLAN 的计划提取有两条通路：

- 从 `ExitPlanMode` 的 `tool_result` 提取正式 approved plan
- 从远程日志里的 `<ultraplan>` 标签提取计划文本

前者更接近“审批后的权威版本”，后者更接近“远程日志中的产物”。

---

## 20. Python 复现建议：建议按什么模块拆

如果要用 Python 复现一个同类特性，建议最少拆成以下模块。

### 20.1 `trigger.py`

职责：

- 检测用户输入中的 `ultraplan` 关键字
- 应用与源码等价的排除规则
- 在必要时把输入改写成 `/ultraplan ...`

建议接口：

```python
def find_ultraplan_trigger_positions(text: str) -> list[tuple[int, int]]: ...
def has_ultraplan_keyword(text: str) -> bool: ...
def replace_ultraplan_keyword(text: str) -> str: ...
```

### 20.2 `session_launcher.py`

职责：

- 统一处理 `/ultraplan` 的启动逻辑
- 防止重复启动
- 组装 prompt
- 调远程会话创建 API

建议状态：

```python
@dataclass
class UltraplanState:
    launching: bool = False
    session_url: str | None = None
    pending_choice: dict | None = None
    launch_pending: dict | None = None
    is_ultraplan_mode: bool | None = None
```

### 20.3 `remote_api.py`

职责：

- 创建远程会话
- 轮询远程事件
- 归档远程会话

关键点：

- 创建会话时不要把 `permission_mode` 直接放顶层
- 必须在初始 `events` 里 prepend 一个 `control_request`
- `request = { subtype: 'set_permission_mode', mode: 'plan', ultraplan: True }`

### 20.4 `scanner.py`

职责：

- 完全仿照 `ExitPlanModeScanner`
- 只做事件扫描，不做网络

建议接口：

```python
class ExitPlanModeScanner:
    def ingest(self, events: list[dict]) -> ScanResult: ...
    @property
    def has_pending_plan(self) -> bool: ...
    @property
    def reject_count(self) -> int: ...
```

### 20.5 `poller.py`

职责：

- 每 3 秒调用一次 `poll_remote_session_events`
- 维护 `after_id`
- 把 `newEvents` 喂给 scanner
- 根据 `session_status` 和 `scanner` 输出 phase

### 20.6 `ui_bridge.py`

职责：

- 在本地显示 launching / running / needs_input / plan_ready
- plan 准备好时显示 choice dialog
- 用户停止时清理本地状态

---

## 21. Python 复现建议：最小可用流程

下面给出一个按源码设计还原的最小流程。

### 步骤 1：接收触发

两种入口：

- `/ultraplan <prompt>`
- 普通输入里出现触发性 `ultraplan`

### 步骤 2：本地防重入

检查：

- `state.launching`
- `state.session_url`

任一为真则拒绝新的启动。

### 步骤 3：构造 prompt

按源码顺序拼接：

1. 可选 seed plan
2. 固定 instructions
3. 用户 blurb

注意：远程 prompt 里不要裸写 `ultraplan` 关键字。

### 步骤 4：创建远程会话

请求体中要包含：

```json
{
  "title": "ultraplan: <session title>",
  "events": [
    {
      "type": "event",
      "data": {
        "type": "control_request",
        "request_id": "set-mode-<uuid>",
        "request": {
          "subtype": "set_permission_mode",
          "mode": "plan",
          "ultraplan": true
        }
      }
    },
    {
      "type": "event",
      "data": {
        "type": "user",
        "message": {
          "role": "user",
          "content": "<prompt>"
        }
      }
    }
  ]
}
```

### 步骤 5：注册本地远程任务

保存：

- session id
- session url
- task id
- phase = running

### 步骤 6：开始轮询

每 3 秒：

- 拉取 `/sessions/{id}/events?after_id=...`
- 解析出新的 SDKMessage 列表
- 用 scanner 判定状态

### 步骤 7：处理三种阶段

- `running`: 远程还在工作
- `needs_input`: 网页端需要用户补充输入
- `plan_ready`: 远程已经发出 ExitPlanMode，等待审批结果

### 步骤 8：处理两种成功结果

- `approved` -> `executionTarget = remote`
- `teleport` -> `executionTarget = local`

### 步骤 9：plan 文本提取

- 远程继续执行：从 `## Approved Plan:` 或 `## Approved Plan (edited by user):` 后面提取
- 传回本地执行：从 `__ULTRAPLAN_TELEPORT_LOCAL__\n` 后面提取

### 步骤 10：结束或归档

- 用户选择远程继续执行：本地任务结束，清掉 URL
- 用户选择传回本地：填充 `pending_choice`
- 异常或取消：调用 archive API

---

## 22. Python 复现时最容易漏掉的细节

### 22.1 不要把远程模式设置延后

必须在创建会话时就把 `set_permission_mode(plan, ultraplan=true)` 作为首个事件写入。否则第一轮行为可能跑偏。

### 22.2 不要把关键词检测写得太宽松

源码专门排除了路径、引号、文件名、问题句等上下文。若你只写 `if 'ultraplan' in text`，误触发会非常多。

### 22.3 不要把轮询器和扫描器写成一个类

源码把“拉事件”和“判状态”明确分开，这样：

- 扫描器可测试
- 轮询器可替换
- 错误定位更清楚

### 22.4 不要把 `idle` 直接等同于“等用户输入”

源码要求 `idle/requires_action` 且 `newEvents.length == 0` 才视为 `needs_input`。这是为了避免 session 在短暂 idle 窗口中被误判。

### 22.5 不要把远程批准和本地传回设计成两套完全不同协议

源码复用已有 `tool_result` 机制，只用 sentinel 做分流。这比另起一个 API 轻得多。

### 22.6 停止远程任务时优先 archive，而不是强删

archive 的好处是：

- 对正在运行的会话可用
- 远程下一次写事件时自然停止
- 比硬删除更稳

### 22.7 需要防止孤儿 session

源码在 `launchDetached()` 的异常分支里特地处理了“session 已创建，但本地后续抛错”的情况，并调用 `archiveRemoteSession(sessionId)`，避免远程白跑 30 分钟。

文件：`src/commands/ultraplan.tsx:392-401`

```ts
if (sessionId) {
  void archiveRemoteSession(sessionId).catch(...)
  setAppState(prev => prev.ultraplanSessionUrl ? {
    ...prev,
    ultraplanSessionUrl: undefined
  } : prev);
}
```

这个细节在 Python 实现里也必须有。

---

## 23. 一个适合 Python 的最小伪代码框架

```python
class UltraplanService:
    def __init__(self, remote_api, state_store):
        self.remote_api = remote_api
        self.state = state_store

    async def launch(self, blurb: str, seed_plan: str | None = None):
        if self.state.launching or self.state.session_url:
            return {"status": "already_active"}

        self.state.launching = True
        try:
            prompt = build_ultraplan_prompt(blurb, seed_plan)
            session = await self.remote_api.create_session(
                initial_message=prompt,
                description=blurb or "Refine local plan",
                permission_mode="plan",
                ultraplan=True,
            )
            self.state.session_url = session.url
            self.state.launching = False

            task_id = self.state.register_remote_task(session.id, "ultraplan")
            asyncio.create_task(self.poll_until_plan(task_id, session.id, session.url))
            return {"status": "launching", "url": session.url}
        except Exception:
            self.state.launching = False
            raise

    async def poll_until_plan(self, task_id: str, session_id: str, url: str):
        scanner = ExitPlanModeScanner()
        after_id = None
        failures = 0

        while True:
            try:
                resp = await self.remote_api.poll_events(session_id, after_id)
                after_id = resp.last_event_id
                failures = 0
            except TransientNetworkError:
                failures += 1
                if failures >= 5:
                    await self.remote_api.archive_session(session_id)
                    raise
                await asyncio.sleep(3)
                continue

            result = scanner.ingest(resp.new_events)

            if result.kind == "approved":
                self.state.complete_remote_task(task_id)
                self.state.session_url = None
                return {"execution_target": "remote", "plan": result.plan}

            if result.kind == "teleport":
                self.state.pending_choice = {
                    "task_id": task_id,
                    "session_id": session_id,
                    "plan": result.plan,
                }
                return {"execution_target": "local", "plan": result.plan}

            phase = derive_phase(scanner, resp.session_status, resp.new_events)
            self.state.update_task_phase(task_id, phase)
            await asyncio.sleep(3)
```

这个框架已经覆盖了源码最核心的机制。

---

## 24. 最终总结

ULTRAPLAN 的实现并不神秘，但它解决的问题非常具体：

1. 复杂规划时间长，不适合阻塞本地终端
2. 规划和执行应该拆开
3. 远程规划需要用户审批
4. 本地只需要维持状态、通知和结果承接

从源码上看，它的关键机制有五个：

1. 关键字或 slash 命令触发
2. 远程会话创建时注入 `set_permission_mode(plan, ultraplan=true)`
3. 本地后台轮询远程事件流
4. 通过 `ExitPlanMode` 的 `tool_result` 提取正式 plan
5. 用 sentinel 区分“远程继续执行”和“传回本地执行”

如果用 Python 复现，最重要的不是 UI，而是以下三点必须做对：

- 会话初始化的 control_request 注入
- 事件流扫描器与轮询器分层
- approved 与 teleport 两条 plan 提取路径

只要这三点对了，ULTRAPLAN 的核心机制就已经复现出来了。

---

## 25. 参考源码定位清单

- 命令注册：`src/commands.ts:104-106,239`
- 命令入口：`src/commands/ultraplan.tsx:225-410`
- slash 命令壳：`src/commands/ultraplan.tsx:411-470`
- prompt 构造：`src/commands/ultraplan.tsx:36-72`
- 关键字识别：`src/utils/ultraplan/keyword.ts:13-127`
- 输入重写：`src/utils/processUserInput/processUserInput.ts:455-493`
- 输入框高亮：`src/components/PromptInput/PromptInput.tsx:520-523`
- 启动前对话框按钮隐藏条件：`src/components/permissions/ExitPlanModePermissionRequest/ExitPlanModePermissionRequest.tsx:138-158`
- REPL 对话框挂载：`src/screens/REPL.tsx:2017-2038,4850-4890`
- AppState 字段：`src/state/AppStateStore.ts:428-445`
- metadata 同步：`src/state/onChangeAppState.ts:24-40,65-92`
- schema：`src/entrypoints/sdk/controlSchemas.ts:124-134`
- 远程会话创建：`src/utils/teleport.tsx:730-795,1117-1160`
- 远程事件轮询：`src/utils/teleport.tsx:621-714`
- 远程会话归档：`src/utils/teleport.tsx:1193-1218`
- 轮询与扫描器：`src/utils/ultraplan/ccrSession.ts:21-349`
- plan 标签常量：`src/constants/xml.ts:40-41`
- 从远程日志提取 plan：`src/tasks/RemoteAgentTask/RemoteAgentTask.tsx:204-217`
