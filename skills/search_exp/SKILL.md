---
name: "search_experience"
description: "检索本地经验库，获取历史 Agent 解决过的报错方案和配置经验。"
---

# Execution Instructions

## 核心能力

此技能让你拥有访问【本地集体智慧库】的能力。

这个库由 `agent_experiences/` 目录驱动，自动收录了历史 Agent 在执行任务时踩过的坑和经过验证的解决方案。通过分层索引检索，可以在几毫秒内找到最相关的历史经验。

## 工具说明

### `search_experience(query)`

**使用原则：遇到报错必须第一时间调用，不要先尝试靠猜测修复。**

| 参数    | 说明                                     |
| ------- | ---------------------------------------- |
| `query` | 完整的报错信息，或问题描述。越精确越好。 |

**返回值结构**：
- 【历史问题】：Agent 当时想做什么，在哪里卡住了
- 【报错特征】：原始报错信息摘要
- 【已验证的解决方案】：JSON 格式的命令/代码
- 【原理分析】：为什么会出错，为什么这样修复有效

## 使用时机

1. **遇到报错时（MUST）**：执行代码出现 Traceback、Error Code、Permission Denied 等，第一步就是调用此工具
2. **环境配置时**：需要配置 git proxy、docker、内网工具等不熟悉的命令时
3. **重复失败时**：已经尝试了 2 次以上仍然失败，查库看有没有历史解法

## 最佳实践

1. **把完整报错粘进去**：`search_experience("SSL certificate problem: unable to get local issuer certificate")` 比 `search_experience("git 报错")` 好 10 倍
2. **理解后适配**：库里的路径、参数名可能与当前任务不同，请阅读【原理分析】后自行适配，不要生搬硬套
3. **置信度判断**：返回的置信度分数越高（100 分为最高），说明与历史问题的匹配程度越精确

## 检索原理（分层设计）

```
L0 索引层 (< 1ms)
  index_manifest.json  <-- 只有 KB 级别，常驻检索
  |
  +-- 报错特征精确匹配   权重 100
  +-- 标题语义相似       权重  50
  +-- 关键词交集         权重  10/个

  命中 & 置信度 >= 15?
       |
       YES --> L2 懒加载层
               直接读取 agent_experiences/{category}/{gene_id}.json
               返回完整解决方案
       |
       NO  --> 返回"未找到"提示，自行分析
```

## 示例

### 示例 1：精准匹配报错

**场景**：执行脚本报错 `[ERROR] 命令执行超时(超过 60 秒)`

```python
search_experience("[ERROR] 命令执行超时(超过 60 秒)")
```

**预期输出**：
```
[search_exp] 已匹配到历史经验 (置信度: 100)
分类: python  |  时间: 2026-02-22  |  ID: gene_b03d793e
...
【已验证的解决方案】:
["python script.py arg1", "python script.py arg2"]

【原理分析】: 一开始使用 echo 管道输入交互模式，但 input() 无法处理
管道输入导致超时。后来改为命令行参数调用绕过了交互模式。
```

### 示例 2：关键词语义匹配

**场景**：不确定当前环境 git 代理如何配置

```python
search_experience("git proxy 配置 内网 ssl error")
```
