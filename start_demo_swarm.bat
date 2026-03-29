@echo off
setlocal enabledelayedexpansion

:: ==========================================
:: 演示配置区域
:: ==========================================
set LEADER_PORT=8000
set WORKER_COUNT=4
set START_PORT=8001
set MODULE_PATH=src.adk_agent.main_web_start_steering
:: 集群协调目录（所有节点共享，存放任务队列和邮箱文件）
:: 留空则自动使用项目根目录下的 coordination/ 子目录
set ADK_COORDINATION_DIR=D:\test123
:: ==========================================

:: 切换到脚本所在目录，防止路径错误
cd /d %~dp0

:: 1. 清理环境 (防止僵尸节点)
echo [System] Cleaning up old registry for a fresh demo...
if exist sqlite_db/swarm_registry.db del sqlite_db/swarm_registry.db
if not exist logs mkdir logs

:: 清理团队成员注册表（config.json 记录上次节点端口，不清会导致 Leader 向死端口广播任务）
:: 保留 tasks/ 目录，历史任务记录不影响新任务认领
set TEAM_ID=swarm_team
set COORD_CONFIG=%ADK_COORDINATION_DIR%\%TEAM_ID%\coordination\config.json
if exist "%COORD_CONFIG%" (
    del "%COORD_CONFIG%"
    echo [System] Cleared stale team config: %COORD_CONFIG%
)

echo.
echo ========================================================
echo      ADK Agent Swarm - Demo Mode (Visible Windows)
echo ========================================================
echo.

:: 2. 启动 Leader (保留窗口 cmd /k 用于调试)
echo [Leader] Launching Orchestrator Node (Port %LEADER_PORT%)...
start "LEADER AGENT (Port %LEADER_PORT%)" cmd /k "set PYTHONIOENCODING=utf8 && set ADK_COORDINATION_DIR=%ADK_COORDINATION_DIR% && python -m %MODULE_PATH% --port %LEADER_PORT%"

:: 等待 Leader 初始化数据库
timeout /t 3 /nobreak >nul

:: 3. 循环启动 Workers (弹出多个独立窗口)
echo [Workers] Launching %WORKER_COUNT% Worker Nodes...

for /L %%i in (0, 1, 3) do (
    set /a CURRENT_PORT=%START_PORT% + %%i
    
    echo    -> Spawning Worker on Port !CURRENT_PORT!...
    
    :: 启动独立窗口 (保留窗口 cmd /k 用于调试)
    start "WORKER - Port !CURRENT_PORT!" cmd /k "set PYTHONIOENCODING=utf8 && set ADK_COORDINATION_DIR=%ADK_COORDINATION_DIR% && python -m %MODULE_PATH% --port !CURRENT_PORT!"
    
    :: 稍微错开启动时间
    timeout /t 1 /nobreak >nul
)

echo.
echo ========================================================
echo    Swarm Cluster Startup Sequence Completed.
echo.
echo    If windows close immediately, check the error message above.
echo    Leader Dashboard: http://localhost:%LEADER_PORT%
echo ========================================================
pause
