@echo off
echo Stopping all Swarm Agents...
:: 强制杀死所有 python 进程 (演示专用，简单粗暴)
taskkill /F /IM python.exe
echo All agents stopped.
pause
