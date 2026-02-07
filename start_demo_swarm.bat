@echo off
setlocal enabledelayedexpansion

:: ==========================================
:: 演示配置区域
:: ==========================================
set LEADER_PORT=8000
set WORKER_COUNT=4
set START_PORT=8001
set MODULE_PATH=skills.adk_agent.main_web_start_steering
:: ==========================================

:: 切换到脚本所在目录，防止路径错误
cd /d %~dp0

:: 1. 清理环境 (防止僵尸节点)
echo [System] Cleaning up old registry for a fresh demo...
if exist swarm_registry.db del swarm_registry.db
if not exist logs mkdir logs

echo.
echo ========================================================
echo      ADK Agent Swarm - Demo Mode (Visible Windows)
echo ========================================================
echo.

:: 2. 启动 Leader (保留窗口 cmd /k 用于调试)
echo [Leader] Launching Orchestrator Node (Port %LEADER_PORT%)...
start "LEADER AGENT (Port %LEADER_PORT%)" cmd /k "set PYTHONIOENCODING=utf8 && python -m %MODULE_PATH% --port %LEADER_PORT%"

:: 等待 Leader 初始化数据库
timeout /t 3 /nobreak >nul

:: 3. 循环启动 Workers (弹出多个独立窗口)
echo [Workers] Launching %WORKER_COUNT% Worker Nodes...

for /L %%i in (0, 1, 3) do (
    set /a CURRENT_PORT=%START_PORT% + %%i
    
    echo    -> Spawning Worker on Port !CURRENT_PORT!...
    
    :: 启动独立窗口 (保留窗口 cmd /k 用于调试)
    start "WORKER - Port !CURRENT_PORT!" cmd /k "set PYTHONIOENCODING=utf8 && python -m %MODULE_PATH% --port !CURRENT_PORT!"
    
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
