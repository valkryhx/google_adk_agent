# 仓库指南

## 项目结构与模块组织
- `src/adk_agent/`：核心运行时代码（FastAPI 入口、steering/session 逻辑、Kairos 模块，以及 `src/adk_agent/static/` 中的前端资源）。
- `src/shared/db/`：共享持久化服务（重点文件：`custom_table_db_service.py`）。
- `skills/<skill_id>/`：按需懒加载的技能包。每个技能目录应包含 `SKILL.md` 和 `tools.py`，并提供 `get_tools(*args, **kwargs)`。
- `tests/`：自动化测试目录，按子系统拆分（如 `tests/kairos/`、`tests/dex/`）。
- `docs/`、`MISC/`、`.planning/`：设计与规划文档目录，不应放置运行时核心逻辑。

## 构建、测试与开发命令
- `pip install -r requirements.txt`：安装项目依赖。
- PowerShell（Windows）：`$env:PYTHONIOENCODING='utf-8'; python -m src.adk_agent.main_web_start_steering --port 8000`，启动主服务。
- `$env:PYTHONIOENCODING='utf-8'; python -m src.adk_agent.main_web_start_steering_single_agent`：启动单智能体模式。
- `.\start_demo_swarm.bat`：在 Windows 启动演示用 leader/worker 集群。
- `pytest`：运行 Python 测试（`pytest.ini` 已将测试路径配置为 `tests/`）。
- `node tests/stream_dedup_frontend.test.cjs`：运行前端 stream dedup 回归测试。

## 代码风格与命名约定
- Python 代码遵循 4 空格缩进，文件编码统一为 UTF-8。
- 命名遵循现有约定：模块/函数使用 `snake_case`，类使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。
- 技能模块应保持轻量导入，重量级初始化放在 `get_tools` 内执行。
- 仓库未强制统一 formatter 配置；请保持与周边代码风格一致，避免无关重构。

## 测试指南
- 测试框架为 `pytest`，默认参数包含 `--import-mode=importlib`（见 `pytest.ini`）。
- 测试文件命名使用 `test_*.py`，并按子系统放在对应目录（如 `tests/kairos/`、`tests/dex/`）。
- Bug 修复或行为变更（路由、流式输出、技能加载）需补充回归测试。
- 修改 `src/adk_agent/static/` 下前端工具逻辑时，应同步更新或新增 `.cjs` 断言测试。

## 提交与 Pull Request 规范
- 建议沿用历史中的 Conventional Commit 风格，例如 `feat(scope): ...`、`fix(scope): ...`。
- 提交信息保持简洁、祈使语气，并使用明确作用域（如 `ui`、`swarm`、`dag`、`prompt`、`chat`）。
- PR 建议包含：变更目的、关键修改路径、验证步骤与结果；涉及 UI 时附截图。

## 安全与配置提示
- 密钥配置放在本地 `private_key.yaml`，严禁提交 API Key。
- Windows 下运行可能输出中文或 emoji 的脚本/服务时，请设置 `PYTHONIOENCODING=utf-8`。

## Agent 专项说明
- 使用中文交互。
