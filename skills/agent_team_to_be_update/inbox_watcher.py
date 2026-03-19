#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InboxWatcher - HTTP Callback Server for Agent Team (去中心化自协调架构)

A lightweight HTTP webhook service that runs alongside each Worker.
- Runs on agent_port + 1000 (e.g., Worker on 8001 runs watcher on 9001)
- Provides immediate wake notifications via POST /wake
- Receives messages via POST /message
- Health check via GET /health

This complements the PollingDaemon's 2-second polling with immediate callbacks.
"""

import asyncio
import json
import os
import sys
from typing import Optional

# Check for aiohttp availability
AIOHTTP_AVAILABLE = False
try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    pass

if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


class InboxWatcher:
    """
    HTTP callback server for agent coordination.

    Each worker runs an InboxWatcher on port agent_port + 1000.
    Other agents can POST to /wake to immediately notify this worker,
    or POST to /message to send a message directly.
    """

    def __init__(
        self,
        agent_id: str,
        agent_port: int,
        coordination_dir: str,
    ):
        """
        Initialize the InboxWatcher.

        Args:
            agent_id: Unique identifier for this agent
            agent_port: The agent's main port (watcher runs on port + 1000)
            coordination_dir: Directory for coordination files
        """
        self.agent_id = agent_id
        self.agent_port = agent_port
        self.watcher_port = agent_port + 1000
        self.coordination_dir = coordination_dir
        self._mailbox = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    def _get_mailbox(self):
        """Lazy initialization of Mailbox."""
        if self._mailbox is None:
            try:
                from .mailbox import Mailbox
            except ImportError:
                from mailbox import Mailbox
            self._mailbox = Mailbox(
                agent_id=self.agent_id,
                coordination_dir=self.coordination_dir,
            )
        return self._mailbox

    def _get_wake_flag_path(self, target_agent_id: str) -> str:
        """Get the path for a wake flag file."""
        wake_dir = os.path.join(
            self.coordination_dir,
            "coordination",
            "_wake_flags",
        )
        return os.path.join(wake_dir, f"{target_agent_id}.wake")

    def _write_wake_flag(self, target_agent_id: str) -> bool:
        """
        Write a wake flag file for the target agent.

        Args:
            target_agent_id: The agent to wake up

        Returns:
            True if successful, False otherwise
        """
        try:
            wake_path = self._get_wake_flag_path(target_agent_id)
            wake_dir = os.path.dirname(wake_path)
            os.makedirs(wake_dir, exist_ok=True)

            # Write timestamp to wake flag
            import time
            with open(wake_path, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
            return True
        except Exception:
            return False

    async def _handle_wake(self, request: web.Request) -> web.Response:
        """
        Handle POST /wake?agent_id=xxx

        Writes a wake flag file for the specified agent.
        """
        try:
            target_agent_id = request.query.get("agent_id", self.agent_id)
            success = self._write_wake_flag(target_agent_id)

            if success:
                return web.json_response({"status": "ok"})
            else:
                return web.json_response(
                    {"status": "error", "message": "Failed to write wake flag"},
                    status=500,
                )
        except Exception as e:
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500,
            )

    async def _handle_message(self, request: web.Request) -> web.Response:
        """
        Handle POST /message

        Reads JSON body with message data and stores it via mailbox.
        Also triggers wake flag for the recipient.
        """
        try:
            data = await request.json()

            # Validate required fields
            required = ["from", "to", "content", "type"]
            for field in required:
                if field not in data:
                    return web.json_response(
                        {"status": "error", "message": f"Missing field: {field}"},
                        status=400,
                    )

            # Get mailbox and send message
            mailbox = self._get_mailbox()
            message_id = mailbox.send_message(
                to_agent=data["to"],
                message_type=data["type"],
                content=data["content"],
                metadata=data.get("metadata", {}),
            )

            # Trigger wake flag for recipient
            self._write_wake_flag(data["to"])

            return web.json_response({
                "status": "ok",
                "message_id": message_id,
            })

        except json.JSONDecodeError:
            return web.json_response(
                {"status": "error", "message": "Invalid JSON"},
                status=400,
            )
        except Exception as e:
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500,
            )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """
        Handle GET /health

        Returns health status and agent information.
        """
        return web.json_response({
            "status": "ok",
            "agent_id": self.agent_id,
            "port": self.agent_port,
            "watcher_port": self.watcher_port,
        })

    def _setup_routes(self, app: web.Application):
        """Setup HTTP routes."""
        app.router.add_post("/wake", self._handle_wake)
        app.router.add_post("/message", self._handle_message)
        app.router.add_get("/health", self._handle_health)

    async def start(self):
        """
        Start the HTTP server.

        Runs on host='127.0.0.1', port=self.agent_port + 1000
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError(
                "aiohttp not available, install with: pip install aiohttp"
            )

        app = web.Application()
        self._setup_routes(app)

        self._runner = web.AppRunner(app)
        await self._runner.setup()

        self._site = web.TCPSite(
            self._runner,
            host="127.0.0.1",
            port=self.watcher_port,
        )
        await self._site.start()

        print(f"[InboxWatcher] {self.agent_id} listening on port {self.watcher_port}")

    async def stop(self):
        """Stop the HTTP server and cleanup resources."""
        if self._site:
            await self._site.stop()
            self._site = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        print(f"[InboxWatcher] {self.agent_id} stopped")


# Convenience function for running standalone
async def run_watcher(agent_id: str, agent_port: int, coordination_dir: str):
    """
    Run an InboxWatcher instance.

    Args:
        agent_id: Unique identifier for this agent
        agent_port: The agent's main port
        coordination_dir: Directory for coordination files
    """
    watcher = InboxWatcher(agent_id, agent_port, coordination_dir)
    await watcher.start()

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        await watcher.stop()
        raise


if __name__ == "__main__":
    # Example usage
    import argparse

    parser = argparse.ArgumentParser(description="InboxWatcher HTTP Callback Server")
    parser.add_argument("--agent-id", required=True, help="Agent ID")
    parser.add_argument("--agent-port", type=int, required=True, help="Agent port")
    parser.add_argument(
        "--coordination-dir",
        required=True,
        help="Coordination directory",
    )

    args = parser.parse_args()

    if not AIOHTTP_AVAILABLE:
        print("Error: aiohttp not available, install with: pip install aiohttp")
        sys.exit(1)

    try:
        asyncio.run(
            run_watcher(args.agent_id, args.agent_port, args.coordination_dir)
        )
    except KeyboardInterrupt:
        print("\nShutting down...")
