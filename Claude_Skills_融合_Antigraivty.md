# 将 Claude Skills 融入 Antigravity：技术集成指南

本文档详细记录了如何将 Claude 的 Skill 机制（一种模块化、可扩展的 Agent 能力定义方式）集成到 Antigravity 开发环境中。

## 核心集成要点

要让 Antigravity 成功集成 Claude Skills，请务必关注以下 4 点：

1.  **Skills 目录位置**  
    必须位于 `C:\Users\drago\.gemini\skills\skills`。

2.  **启用 Slash (/) 命令**  
    必须在 `C:\Users\drago\.gemini\antigravity\global_workflows\antigravity\global_workflows` 目录下创建 `xx_skill.md` 文件。

3.  **提高唤起率**  
    必须在 `C:\Users\drago\.gemini\GEMINI.md` 中添加相应的 Prompt 提示。

4.  **Python 执行规范**  
    必须设置编码并使用绝对路径：
    ```cmd
    cmd /c set PYTHONIOENCODING=utf-8 && python C:/Users/drago/.gemini/skills/skills/xxxx.py
    ```


> [!IMPORTANT]
> **全局 Skills 核心路径**
> 
> 请务必注意，所有全局 Skills（包括 Skill Creator）都必须部署在以下路径：
> 
> **`C:\Users\drago\.gemini\skills\skills`**
> 
> *注意：路径中包含双层 `skills` 目录 (`.../skills/skills/`)，这是由于仓库结构决定的，配置时请格外小心。*

## 1. 核心概念

**Claude Skills** 是 Anthropic 提出的一种标准化 Agent 能力扩展格式。一个 Skill 通常包含：
*   `SKILL.md`: 核心定义文件，包含 Prompt 指令、用法示例和元数据。
*   `scripts/`: 可执行代码（Python/Bash 等），Agent 通过调用这些脚本来执行具体任务。
*   `requirements.txt`: 依赖声明。

**Antigravity** 通过 **Global Workflows** 和 **Global Rules** 来原生支持这种 Skill 创建和使用流程。

## 2. 环境准备

为了在 Antigravity 中高效创建 Skills，我们需要配置全局工具链。

### 2.1 部署 Skill Creator
我们将官方的 `skill-creator` 工具部署在全局目录，以便所有项目复用。

*   **全局部署路径**: `C:\Users\drago\.gemini\skills\skills\skill-creator`
*   **核心脚本**: `scripts/init_skill.py` (用于初始化 Skill 结构)

> **再次强调**: 脚本的完整绝对路径为 `C:\Users\drago\.gemini\skills\skills\skill-creator\scripts\init_skill.py`。

### 2.2 配置 Global Workflow
为了简化创建流程，我们在 Antigravity 的全局工作流目录中定义了 `/create_skill` 命令。*只有这样才能在 Antigravity 中使用 Slash (/) 命令。*

**文件位置**: `C:\Users\drago\.gemini\antigravity\global_workflows\create_skill.md`

**关键配置**:
```markdown
---
description: Create a new Claude Skill using the official Skill Creator (Global)
---

1. **Ask for Name**: 获取 Skill 名称。
2. **Run Initialization**: 调用全局脚本。
   ```bash
   # 注意：此处使用了双层 skills 路径
   cmd /c set PYTHONIOENCODING=utf-8 && python C:/Users/drago/.gemini/skills/skills/skill-creator/scripts/init_skill.py [SKILL_NAME] --path skills
   ```
```

> **技术细节**: 
> *   **Windows 兼容性**: 使用 `cmd /c set PYTHONIOENCODING=utf-8` 是为了解决 Python 在 Windows 终端打印 Emoji 时可能出现的 `UnicodeEncodeError`。
> *   **路径规范**: 统一使用正斜杠 `/`，避免转义问题。

### 2.3 配置 Global Rules (GEMINI.md)
为了让 Agent 在自然语言交互中也能正确创建 Skill，我们在 `GEMINI.md` 中添加了明确的规则。

**文件位置**: `C:\Users\drago\.gemini\GEMINI.md`

```markdown
## Skill Creation Capability
When the user asks to create a new Claude Skill... ALWAYS use the official `skill-creator` script...
Usage:
# 务必使用正确的全局路径
`cmd /c set PYTHONIOENCODING=utf-8 && python C:/Users/drago/.gemini/skills/skills/skill-creator/scripts/init_skill.py [skill-name] --path skills`
```

## 3. 实践案例：Web Search Skill

我们以创建一个基于 Tavily API 的搜索技能为例。

### 3.1 创建流程
1.  用户输入 `/create_skill` 或指令 "创建一个 web-search skill"。
2.  Agent 自动执行 `init_skill.py`，在 `skills/adk_agent/.claude/skills/web-search` 生成标准结构。

### 3.2 最佳实践：配置管理
在实现 `scripts/search.py` 时，我们遵循了**配置与代码分离**的原则。

*   **问题**: API Key 不应硬编码在脚本中，也不应强依赖环境变量（开发环境复杂）。
*   **方案**: 脚本自动向上查找项目根目录的 `private_key.yaml`。

```python
def load_api_key():
    # 自动向上递归查找 private_key.yaml
    current_dir = Path(__file__).parent
    while current_dir != current_dir.parent:
        config_path = current_dir / "private_key.yaml"
        if config_path.exists():
            # 读取 yaml 配置
            return yaml.safe_load(f).get("tavily_api_key")
        current_dir = current_dir.parent
```

### 3.3 验证
使用 `quick_validate.py` 确保 Skill 符合 Claude 的规范：
```bash
# 同样注意使用全局路径
python C:/Users/drago/.gemini/skills/skills/skill-creator/scripts/quick_validate.py skills/adk_agent/.claude/skills/web-search
```

## 4. 总结

通过上述配置，我们实现了：
1.  **标准化**: 所有 Skill 遵循统一的目录结构和文档规范。
2.  **自动化**: 通过 Workflow 一键生成骨架代码。
3.  **健壮性**: 解决了 Windows 编码和路径问题。
4.  **安全性**: 敏感配置（API Key）统一管理。
5.  **全局复用**: 明确了 `C:\Users\drago\.gemini\skills\skills` 为核心组件库。
 



