# ADK Dynamic Skills Agent

基于 Google Agent Development Kit 的动态技能加载智能体框架。

## 特性

- **两阶段懒加载**: 初始化只加载技能的 name 和 description，完整 Instructions 按需加载
- **动态工具管理**: 运行时挂载/卸载工具函数
- **增强提示词**: 包含 ReAct 推理、错误恢复、多轮对话策略
- **结构化日志**: 详细的执行跟踪和工具调用记录
- **Agentic RAG**: 基于 ripgrep 的智能代码搜索

## 快速开始

### 1. 安装依赖

```bash
cd skills/adk_agent
pip install -r requirements.txt
```

### 2. 配置 API 密钥

推荐使用 `private_key.yaml` 进行配置（位于项目根目录）：

```yaml
api_key: "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

或者使用环境变量：

```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY="your-api-key"
$env:DASHSCOPE_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"

# Linux/macOS
export DASHSCOPE_API_KEY="your-api-key"
export DASHSCOPE_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

### 3. 运行

```bash
# 演示模式
python main.py

# 交互模式
python main.py -i

# 执行指定任务
python main.py "分析 data.csv 的数据"

# 帮助
python main.py -h
```

## 项目结构

```
adk_agent/
├── .claude/skills/               # 技能定义目录
│   ├── codebase_search/          # 代码搜索 (ripgrep)
│   │   ├── SKILL.md
│   │   └── tools.py
│   ├── data_analyst/             # 数据分析
│   │   ├── SKILL.md
│   │   └── tools.py
│   ├── compactor/                # 上下文压缩
│   │   ├── SKILL.md
│   │   └── tools.py
│   └── web_search/               # 网络搜索
│       ├── SKILL.md
│       └── tools.py
├── core/
├── config.py                     # 配置和提示词模板 (支持 YAML 加载)
├── main.py                       # 主入口
├── requirements.txt
└── README.md
```

## 已实现的技能

| 技能 ID           | 名称           | 描述                             |
| ----------------- | -------------- | -------------------------------- |
| `codebase_search` | 代码库搜索专家 | 基于 ripgrep 的精确代码搜索      |
| `data_analyst`    | 数据分析专家   | CSV 分析、统计计算、图表生成     |
| `compactor`       | 上下文压缩器   | 智能截断历史、卸载工具、释放资源 |
| `web_search`      | 网络搜索助手   | Google Search API 集成           |

## 交互式命令

进入交互模式后 (`python main.py -i`)，可使用以下命令：

| 命令            | 说明                             |
| --------------- | -------------------------------- |
| `skills`        | 查看所有可用技能                 |
| `tools`         | 查看已加载的工具                 |
| `reset`         | 重置 Agent 状态 (触发 compactor) |
| `verbose`       | 切换详细输出模式                 |
| `quit` / `exit` | 退出程序                         |

## 添加新技能

1. 在 `.claude/skills/` 下创建新目录

2. 创建 `SKILL.md` (技能元信息和 Instructions):
```markdown
---
name: "技能名称"
description: "简短描述"
---

# 执行 Instructions
详细的执行步骤...

## 示例
User: "用户请求"
Action: tool_function(args)
```

3. 创建 `tools.py` (工具函数):
```python
def my_tool(param: str) -> str:
    """工具描述"""
    return "结果"

def get_tools():
    return [my_tool]
```

## 配置选项

在 `config.py` 中可以自定义：

```python
@dataclass
class AgentConfig:
    name: str = "Dynamic_Expert"
    model: str = "openai/qwen3-32b"  # 默认使用 Qwen
    skills_path: str = "./.claude/skills"
    
    # API 配置 (优先读取 private_key.yaml)
    api_key: Optional[str] = ...
    api_base: Optional[str] = ...
    
    max_retries: int = 3
    verbose: bool = True
```

## 系统提示词设计

Agent 使用增强的系统提示词，包含：

1. **技能加载策略** - 何时以及如何加载技能
2. **ReAct 推理模式** - Thought → Action → Observation 循环
3. **错误处理策略** - 自动重试和降级方案
4. **搜索策略** - 针对代码搜索的多轮迭代指导
5. **输出格式** - 简洁、引用文件路径、代码高亮

## 相关文档

- [Google ADK 技能开发指南](../google_adk_skills_guide.md)
- [Ripgrep Agentic RAG 指南](../ripgrep_agentic_rag_guide.md)
