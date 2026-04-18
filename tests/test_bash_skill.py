from pathlib import Path
import asyncio
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skills.bash.tools import bash, validate_command


def test_validate_command_blocks_ctrl_c_event_teardown():
    is_safe, reason = validate_command(
        'python -c "import signal; proc.send_signal(signal.CTRL_C_EVENT)"'
    )

    assert is_safe is False
    assert "CTRL_C_EVENT" in reason


def test_validate_command_blocks_name_based_python_kill():
    is_safe, reason = validate_command(
        'powershell -Command "Stop-Process -Name python -Force"'
    )

    assert is_safe is False
    assert "Stop-Process -Name python" in reason


class _FakeStream:
    async def read(self, _size: int) -> bytes:
        await asyncio.sleep(10)
        return b""


class _FakeProcess:
    def __init__(self):
        self.returncode = None
        self.stdout = _FakeStream()
        self.stderr = _FakeStream()
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode

    async def communicate(self):
        return b"", b""


def test_bash_cancellation_terminates_subprocess(monkeypatch):
    fake_process = _FakeProcess()

    async def fake_create_subprocess_shell(*args, **kwargs):
        return fake_process

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_shell",
        fake_create_subprocess_shell,
    )

    async def run_test():
        task = asyncio.create_task(
            bash("python -c \"import time; time.sleep(30)\"", timeout=30)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_test())

    assert fake_process.terminated is True
    assert fake_process.killed is False
