---
name: use_external_skills
description: 从外部 skills 库（~/.agents/skills）中查找、匹配并加载最合适的 skill 指令。注意：本 skill 专门用于操作外部 skill 库，加载本项目内置 skill 请使用 skill_load
---

# Use External Skills

> **重要区分**
> - 加载**本项目内置** skill（`skills/` 目录）→ 使用 `skill_load <id>`
> - 加载**外部** skill（`C:\Users\drago\.agents\skills`）→ 使用本 skill 提供的工具

本 skill 从 `C:\Users\drago\.agents\skills` 目录中动态发现并加载外部 skill 的 Instructions 及脚本资产。

## 工具一览

| 工具名 | 用途 |
|--------|------|
| `list_external_skills()` | 列出全部可用外部 skill 及其描述 |
| `search_external_skill(query)` | 按意图关键词搜索最匹配的外部 skill（返回 top-3）|
| `load_external_skill(skill_id)` | 加载指定外部 skill 的完整 Instructions + 所有附加 .md 文档 |
| `list_external_skill_assets(skill_id)` | 列出该外部 skill 目录下的全部资产（脚本/文档/引用文件）|
| `run_external_skill_script(skill_id, script_path, args)` | 执行该外部 skill 中的脚本（支持 .sh/.js/.ts/.py）|

## 标准使用流程

1. **发现**：调用 `search_external_skill(query)` 描述你的意图，获取推荐 skill
2. **了解**：调用 `load_external_skill(skill_id)` 获取完整 Instructions，**加载后必须严格遵循其中指令**
3. **查看资产**（可选）：调用 `list_external_skill_assets(skill_id)` 查看是否有可执行脚本
4. **执行脚本**（可选）：调用 `run_external_skill_script(skill_id, "scripts/start-server.sh")` 运行脚本

## 示例

```
# 查找调试相关的外部 skill
search_external_skill("调试代码 bug 根因分析")
→ 推荐: systematic-debugging

# 加载并遵循其 Instructions
load_external_skill("systematic-debugging")

# 查看 brainstorming 的脚本资产
list_external_skill_assets("brainstorming")
→ [script] scripts/start-server.sh
→ [script] scripts/server.js

# 启动 brainstorming 预览服务器
run_external_skill_script("brainstorming", "scripts/start-server.sh", "--project-dir /tmp/demo")
```

## 注意事项

- 外部 skill 加载后，其 Instructions 具有与本项目内置 skill 同等的执行优先级
- 若外部 skill 的 Instructions 要求执行 shell 命令，通过已加载的 `bash` skill 工具完成
- 若无完全匹配，`search_external_skill` 会返回相关度最高的候选，由 agent 自行判断是否合适
