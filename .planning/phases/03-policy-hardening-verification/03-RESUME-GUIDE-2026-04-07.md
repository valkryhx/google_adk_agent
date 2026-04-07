# Phase 3 继续工作指引（2026-04-07）

> 用途：在清理当前上下文后，帮助下一次会话快速恢复到正确的 GSD 主线。
> 当前主仓库：`D:\git_codes\google_adk_helloworld_git`
> 当前主分支：`main`
> 当前 Phase：`03-policy-hardening-verification`

---

## 1. 先读哪些文件

下次恢复时，先按这个顺序读：

1. `.planning/phases/03-policy-hardening-verification/03-CONTEXT.md`
2. `.planning/phases/03-policy-hardening-verification/.continue-here.md`
3. `docs/superpowers/plans/2026-04-07-kairos-phase-3-assistant-mode-runtime.md`
4. `docs/实现phase-3的kairos/2026-04-07-KAIROS-phase-3-基于-ClaudeCode-源码分析的再定位与推进结论.md`
5. `.planning/STATE.md`
6. `.planning/REQUIREMENTS.md`

如果需要回顾 Claude Code Kairos 定位，再读：

7. `docs/探讨claudecode/KAIROS-特性源码分析报告.md`

---

## 2. 当前已经完成的关键里程碑

### 2.1 主线 planning 已校准
已经完成：

- `03-CONTEXT.md` 已创建并提交
- `STATE.md` / `.continue-here.md` 已同步到“ready for planning”状态
- `REQUIREMENTS.md` 已把已有证据覆盖的条目标为完成：
  - `KAI-04`
  - `RPT-01`
  - `RPT-02`
  - `RPT-03`
  - `VER-01`

### 2.2 Phase 3 新方向已经确定
当前统一结论是：

> Phase 3 不再只是“增强 continuation”或“补几个 policy 点”，而是要把 KAIROS 推进成一个在规则护栏约束下、能够持续扫描 unfinished work、主动选择下一步、主动 brief / ask-user / sleep 的长期自治 assistant-mode runtime。

### 2.3 当前强证据链已经具备
main 上已经有：

- richer todo boss demo flow
- verification gating
- blocked-state handling
- host follow-up creation
- live HTTP regression 已补验证

已实测：

- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q` 在本地 8000 端口服务下 **4 passed**

---

## 3. 最近相关提交（主仓库）

恢复时可参考这些提交：

- `61493fe` `test(kairos): fix worktree-relative baseline paths`
- `74500fc` `docs(requirements): sync validated kairos progress`
- `79d1135` `docs(phase3): capture assistant-mode direction and context`
- `fe3c999` `docs(planning): reconcile phase 3 status and live regression proof`
- `ad81d55` `docs(planning): sync richer todo demo progress into gsd state`
- `ff84968` `docs(plan): record todo boss demo progress checkpoint`

---

## 4. 当前已存在的 Phase 3 执行计划

计划文件已经写好并提交：

- `docs/superpowers/plans/2026-04-07-kairos-phase-3-assistant-mode-runtime.md`

它当前把 Phase 3 拆成：

1. proactive state model
2. deterministic unfinished-work scanning + guardrails
3. runtime tick loop proactive refresh
4. assistant-mode tick prompt contract
5. API / UI observability
6. live HTTP proactive field regression
7. verification closure

---

## 5. 当前 worktree 状态

已经创建过隔离 worktree：

- `D:\git_codes\google_adk_helloworld_git\.worktrees\kairos-phase3-assistant-mode`
- worktree branch: `feature/kairos-phase3-assistant-mode`

### worktree 已完成的事情
- 修复了 worktree 基线里写死旧绝对路径的问题
- 已提交到 worktree：
  - `61493fe` `test(kairos): fix worktree-relative baseline paths`
- 这个提交已经 fast-forward 合并回 `main`

### 注意
worktree 里现在存在很多运行产物/缓存目录，**不要提交**：

- `.dex/`
- `demo_delivery/`
- `logs/`
- `sqlite_db/`
- `__pycache__/`
- 各种 `skills/**/__pycache__/`

如果下次继续在 worktree 中工作，先看 `git status --short`，只提交真正的源码/测试改动。

---

## 6. 当前最重要的未完成事项

### 6.1 真正还没开始的是 Phase 3 代码执行
虽然计划和上下文已经齐了，但 **Phase 3 assistant-mode runtime 的正式实现还没开始**。

### 6.2 下一步最该做的是计划执行的 Task 1
优先从：

- `docs/superpowers/plans/2026-04-07-kairos-phase-3-assistant-mode-runtime.md`
- **Task 1: Lock Phase 3 state model for proactive unfinished-work scanning**

开始。

### 6.3 如果继续走 subagent-driven-development
当前正确顺序是：

1. 在 worktree 中确认基线
2. 从 Task 1 开始执行
3. 每个 task 保持：实现 -> spec review -> quality review -> 再进入下一个 task

---

## 7. 基线与环境注意事项

### 7.1 Python / 中文输出
Windows 下涉及中文或 emoji 输出时，继续遵守：

```bash
PYTHONIOENCODING=utf-8 ...
```

### 7.2 测试运行路径
运行测试时必须从目标仓库根目录启动，并在需要时带：

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=.
```

否则容易：
- 导入错源码树
- 找不到 `src/` / `skills/`
- 误连旧路径

### 7.3 live HTTP 测试
主仓库里 8000 端口服务已验证可用；
如果在 worktree 继续做 Phase 3，建议用独立端口，比如：

```bash
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8011
```

并配套：

```bash
KAIROS_BASE_URL=http://127.0.0.1:8011
```

避免误连主仓库服务。

---

## 8. 下次继续工作的最短提示词

如果你下次要快速恢复，可以直接对 Claude 说：

```markdown
继续 Phase 3。先读：
- .planning/phases/03-policy-hardening-verification/03-CONTEXT.md
- .planning/phases/03-policy-hardening-verification/.continue-here.md
- docs/superpowers/plans/2026-04-07-kairos-phase-3-assistant-mode-runtime.md
然后在 worktree `D:/git_codes/google_adk_helloworld_git/.worktrees/kairos-phase3-assistant-mode` 中继续执行 Task 1。
```

---

## 9. 一句话恢复结论

> 当前 Phase 3 的 planning 已完成校准，核心方向已从“自动续推 demo”升级为“assistant-mode 下的长期自治 runtime”；下次恢复时，直接在 worktree 中按 `2026-04-07-kairos-phase-3-assistant-mode-runtime.md` 从 Task 1 开始执行即可。
