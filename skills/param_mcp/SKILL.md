---
name: "参数 MCP 工具集成专家"
description: "集成参数 Model Context Protocol (MCP) 工具，通过 HTTP 连接与外部参数 MCP 服务交互，提供参数管理、工单生成等功能。"
---

# Execution Instructions

## 基本说明

参数 MCP (Model Context Protocol) 工具集成技能，允许智能体通过 HTTP 协议连接到外部参数 MCP 服务，并使用服务提供的工具。

## 使用前提

1. **MCP 服务运行**: 确保 MCP 服务已启动并运行在配置的 URL 上（默认：`http://localhost:9014/mcp`）
2. **服务可用性**: 在加载此技能前，系统会尝试连接 MCP 服务，如果服务不可用，将使用占位工具

## 可用工具（精确参数签名）

加载此技能后，MCP 服务提供的所有工具将自动注册到智能体工具列表。以下是核心工具的精确签名，其他工具请参考 MCP 服务文档：

### tool_param_modify_draft（生成参数修改草稿）

```
tool_param_modify_draft(
    cgi: str,                   # 网元 CGI 标识，如 "460-00-2303087-1"
    unclear_param: str,         # 参数模糊名称，如 "4-5迟滞"（支持中文模糊匹配）
    param_group_id_value: str,  # 参数组 ID 值，如 "M10"
    new_value: str              # 新的参数值，如 "-11"
) -> dict
```

### tool_param_create_order（生成完整参数工单）

```
tool_param_create_order(
    city: str,                  # 所属地市，如 "大同"
    vendor: str,                # 设备厂商，如 "华为"
    net_type: str,              # 网络类型，如 "NR" 或 "LTE"
    param_level: str,           # 参数级别，如 "小区级"
    ne_name: str,               # 网元名称/CGI，如 "460-00-2303087-1"
    param_object: str,          # 参数对象，如 "NRCELLINTERFHOMEAGRP"
    param_name: str,            # 参数英文名称，如 "InterFreqA4A5TimeToTrig"
    param_group_id_name: str,   # 参数组 ID 名称，无则填 "无"
    param_group_id_value: str,  # 参数组 ID 值，如 "M10"
    new_value: str,             # 参数修改值，如 "-11"
    current_value: str,         # 现网参数值（可为空字符串）
    start_time: str,            # 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
    end_time: str               # 结束时间，格式 "YYYY-MM-DD HH:MM:SS"
) -> dict
```

### tool_query_order_history（查询工单参数修改记录）

```
tool_query_order_history(
    order_id: str               # 工单 ID，如 "HN-HN-20251222-1627"
) -> dict
```

> **参数命名注意**：`tool_param_modify_draft` 使用 `cgi` 和 `unclear_param`，
> 而 `tool_param_create_order` 使用 `ne_name` 和 `param_name`（精确英文名）。
> 两者语义不同，注意区分，**切勿混用**。

## 使用流程

1. **加载技能**: 调用 `skill_load("param_mcp")` 加载参数 MCP 集成技能
2. **自动发现工具**: ADK 会自动识别 MCP 服务提供的所有工具，并将它们添加到工具列表
3. **使用工具**: 根据用户需求，直接调用相应的 MCP 工具

**重要提示**: 无需手动查询可用工具列表，ADK 框架会自动处理工具发现和注册。

## 配置

MCP 服务的 URL 可以通过环境变量 `MCP_URL` 配置，默认值为 `http://localhost:9014/mcp`。

## 错误处理

- 如果 MCP 服务不可用，将使用占位工具，返回友好的错误提示（含 URL 和排查步骤）
- 工具调用失败时，会返回详细的错误信息
- **初始化失败后不会重复尝试**，避免每次調用都產生連接超时

## Windows 环境注意事项

在 Windows 控制台或脚本中调用 MCP 工具时，务必设置 UTF-8 编码，否则中文参数可能导致**静默失败（无输出）**：

```bat
cmd /c set PYTHONIOENCODING=utf-8 && python your_script.py
```

或在 Python 脚本开头添加：

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
```

## 注意事项

1. **服务依赖**: 此技能依赖于外部 MCP 服务，确保服务正常运行
2. **网络连接**: 确保能够访问 MCP 服务的 URL
3. **工具命名**: MCP 工具的名称由服务定义，可能与本地工具名称冲突（系统会自动处理）

## 示例

### 示例 1: 查询工单参数修改记录

**用户问题**: "查看工单 HN-HN-20251222-1627 的参数修改记录"

**执行流程**:
```
1. 加载技能: skill_load("param_mcp")
2. ADK 自动发现并注册 MCP 工具到智能体工具列表
3. 调用工具:
   tool_query_order_history(order_id="HN-HN-20251222-1627")
4. 返回结果: 显示工单的参数修改记录
```

### 示例 2: 生成参数修改草稿

**用户问题**: "生成参数修改草稿: 460-00-538402-107 参数组为M10 4-5迟滞修改为-11"

**执行流程**:
```
1. 确保技能已加载 (如果未加载，先调用 skill_load("param_mcp"))
2. 调用 MCP 草稿生成工具，传入参数信息（注意参数名称）:
   tool_param_modify_draft(
       cgi="460-00-538402-107",         # 网元 CGI
       unclear_param="4-5迟滞",          # 模糊参数名，支持中文
       param_group_id_value="M10",       # 参数组
       new_value="-11"                   # 新值
   )
3. 返回生成的草稿内容，包含匹配到的精确参数名、网元信息等
```

### 示例 3: 生成完整工单（结合时间工具）

**用户问题**: "生成参数修改工单，设备 460-00-538402-107，城市娄底，厂商华为，LTE网络，小区级参数，参数对象CELLSEL，参数名QRxLevMin，参数组N10，新值-110，开始时间2025年12月24号12点23分"

**执行流程**:
```
1. 确保技能已加载
2. 如果需要当前时间或时间计算，先调用时间工具（如 get_current_time）
3. 调用 MCP 工单生成工具:
   tool_param_create_order(
       city="娄底",
       vendor="华为",
       net_type="LTE",
       param_level="小区级",
       ne_name="460-00-538402-107",
       param_object="CELLSEL",
       param_name="QRxLevMin",           # 精确英文参数名
       param_group_id_name="无",
       param_group_id_value="N10",
       new_value="-110",
       current_value="",
       start_time="2025-12-24 12:23:00",
       end_time=""                       # 如需要可通过时间工具计算
   )
4. 返回生成的工单信息
```

### 示例 4: 查询工单并获取当前时间

**用户问题**: "查看工单 HN-HN-20251222-1627 的参数修改记录，并告诉我当前时间"

**执行流程**:
```
1. 加载技能: skill_load("param_mcp")
2. 并行调用两个工具：
   - tool_query_order_history(order_id="HN-HN-20251222-1627")
   - get_current_time()
3. 整合两个工具的结果，返回给用户
```

## 工具发现说明

**ADK 自动工具发现机制**:
- 当 `McpToolset` 对象被添加到智能体的工具列表时，ADK 框架会自动调用 `get_tools()` 方法
- ADK 会解析每个工具的名称、描述、参数定义等信息
- 这些信息会自动提供给 LLM，智能体可以根据工具描述智能选择和使用工具
- **无需手动查询工具列表**，智能体可以直接根据用户需求调用相应的工具

**工具使用建议**:
- 查看 `## 可用工具（精确参数签名）` 章节了解准确的参数名称
- 根据用户问题的语义，选择最合适的工具
- 草稿生成（`tool_param_modify_draft`）和工单生成（`tool_param_create_order`）参数名不同，注意区分
- 可以组合使用多个工具来完成复杂任务
