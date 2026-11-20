from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import websockets
from websockets.exceptions import ConnectionClosed


class AuthError(RuntimeError):
    pass


def websocket_url(server: str) -> str:
    value = server.strip()
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    scheme = "wss" if parsed.scheme in {"https", "wss"} else "ws"
    path = parsed.path.rstrip("/")
    if not path.endswith("/api/connector"):
        path = f"{path}/api/connector" if path else "/api/connector"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def normalize_base(url: str) -> str:
    base = url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/")


class Relay:
    def __init__(
        self,
        server: str,
        code: str | None,
        lm_studio_url: str,
    ) -> None:
        self.server = server
        self.code = code
        self.token: str | None = None
        self.lm_studio_url = normalize_base(lm_studio_url)
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=10.0)
        )
        self.send_lock = asyncio.Lock()
        self.request_tasks: dict[str, asyncio.Task[None]] = {}
        self.semaphore = asyncio.Semaphore(4)
        self.connected = False
        self.last_status: dict[str, Any] = {
            "lm_studio": False,
            "models": [],
            "error": None,
        }

    async def send(self, websocket: Any, message: dict[str, Any]) -> None:
        async with self.send_lock:
            await websocket.send(json.dumps(message))

    async def local_status(self) -> dict[str, Any]:
        try:
            response = await self.http.get(
                f"{self.lm_studio_url}/v1/models", timeout=5.0
            )
            response.raise_for_status()
            data = response.json()
            models = [
                item.get("id", "")
                for item in data.get("data", [])
                if item.get("id")
            ]
            status = {"lm_studio": True, "models": models, "error": None}
        except Exception as exc:
            status = {
                "lm_studio": False,
                "models": [],
                "error": f"LM Studio is not reachable: {exc}",
            }
        self.last_status = status
        return status

    async def run(self) -> int:
        backoff = 1.0
        try:
            while True:
                try:
                    await self.session()
                    backoff = 1.0
                except AuthError as exc:
                    print(f"\n{exc}", file=sys.stderr)
                    print(
                        "Open the Source Overlap site and generate a new "
                        "pairing code, then run this command again.",
                        file=sys.stderr,
                    )
                    return 1
                except KeyboardInterrupt:
                    return 0
                except Exception as exc:
                    print(
                        f"\nDisconnected from Source Overlap ({exc}). "
                        f"Reconnecting in {backoff:.0f}s...",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
        finally:
            await self.http.aclose()

    async def session(self) -> None:
        status = await self.local_status()
        auth: dict[str, Any] = (
            {"type": "pair", "code": self.code}
            if self.code and not self.token
            else {"type": "resume", "token": self.token}
        )
        auth.update(status)

        url = websocket_url(self.server)
        try:
            async with websockets.connect(
                url,
                open_timeout=20,
                ping_interval=20,
                ping_timeout=20,
                max_size=16 * 1024 * 1024,
            ) as websocket:
                await self.send(websocket, auth)
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=15)
                except asyncio.TimeoutError as exc:
                    raise AuthError("The hosted app did not answer the pairing request.") from exc
                ready = json.loads(raw)
                if ready.get("type") != "ready":
                    raise AuthError(
                        str(ready.get("message") or "Pairing was rejected.")
                    )

                self.token = str(ready.get("token") or "")
                interval = max(10, int(ready.get("heartbeat_seconds") or 25))
                self.connected = True
                print("Connected to Source Overlap.")
                print(f"LM Studio: {self.lm_studio_url}/v1")
                if status.get("models"):
                    print("Models: " + ", ".join(status["models"]))
                else:
                    print(
                        "No model is loaded yet. Start LM Studio and load a "
                        "model; this connector will pick it up automatically."
                    )
                print("Leave this window open while using the app. Ctrl+C to stop.")

                heartbeat = asyncio.create_task(
                    self.heartbeat(websocket, interval)
                )
                try:
                    async for raw in websocket:
                        try:
                            message = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(message, dict):
                            continue
                        message_type = message.get("type")
                        if message_type == "http":
                            self.start_request(websocket, message)
                        elif message_type == "cancel":
                            request_id = str(message.get("id") or "")
                            task = self.request_tasks.pop(request_id, None)
                            if task:
                                task.cancel()
                        elif message_type == "refresh":
                            asyncio.create_task(
                                self.refresh(websocket, message)
                            )
                finally:
                    heartbeat.cancel()
                    pending = list(self.request_tasks.values())
                    for task in pending:
                        task.cancel()
                    self.request_tasks.clear()
                    await asyncio.gather(
                        heartbeat, *pending, return_exceptions=True
                    )
                    self.connected = False
        except ConnectionClosed as exc:
            if exc.code == 4401:
                raise AuthError(
                    "The pairing session expired on the hosted app."
                ) from exc
            raise

    async def heartbeat(self, websocket: Any, interval: int) -> None:
        while True:
            await asyncio.sleep(interval)
            status = (
                dict(self.last_status)
                if self.request_tasks
                else await self.local_status()
            )
            await self.send(websocket, {"type": "heartbeat", **status})

    async def refresh(self, websocket: Any, message: dict[str, Any]) -> None:
        try:
            status = await self.local_status()
            await self.send(
                websocket,
                {"type": "status", "id": message.get("id"), **status},
            )
        except Exception:
            pass

    def start_request(self, websocket: Any, message: dict[str, Any]) -> None:
        request_id = str(message.get("id") or "")
        if not request_id:
            return
        task = asyncio.create_task(self.handle_request(websocket, message))
        self.request_tasks[request_id] = task

        def done(_: asyncio.Task[None]) -> None:
            self.request_tasks.pop(request_id, None)

        task.add_done_callback(done)

    async def handle_request(
        self, websocket: Any, message: dict[str, Any]
    ) -> None:
        request_id = str(message.get("id") or "")
        path = str(message.get("path") or "")
        method = str(message.get("method") or "POST").upper()
        if path not in {"/v1/models", "/v1/chat/completions"}:
            await self.send(
                websocket,
                {
                    "type": "error",
                    "id": request_id,
                    "status": 400,
                    "message": "Unsupported LM Studio endpoint.",
                },
            )
            return

        url = f"{self.lm_studio_url}{path}"
        body = message.get("body")
        try:
            async with self.semaphore:
                async with self.http.stream(
                    method,
                    url,
                    json=body if method == "POST" else None,
                    timeout=(
                        httpx.Timeout(10.0, connect=5.0)
                        if path == "/v1/models"
                        else httpx.Timeout(600.0, connect=10.0)
                    ),
                ) as response:
                    if response.status_code >= 400:
                        raw = (await response.aread())[:500]
                        text = raw.decode("utf-8", "replace")
                        await self.send(
                            websocket,
                            {
                                "type": "error",
                                "id": request_id,
                                "status": response.status_code,
                                "body": text,
                                "message": (
                                    f"LM Studio returned HTTP "
                                    f"{response.status_code}."
                                ),
                            },
                        )
                        return

                    await self.send(
                        websocket,
                        {
                            "type": "start",
                            "id": request_id,
                            "status": response.status_code,
                            "content_type": response.headers.get(
                                "content-type", ""
                            ),
                        },
                    )
                    async for chunk in response.aiter_text():
                        await self.send(
                            websocket,
                            {
                                "type": "chunk",
                                "id": request_id,
                                "data": chunk,
                            },
                        )
                    await self.send(
                        websocket, {"type": "end", "id": request_id}
                    )
        except asyncio.CancelledError:
            raise
        except httpx.TimeoutException:
            await self.safe_error(
                websocket,
                request_id,
                504,
                "LM Studio did not respond in time.",
            )
        except Exception as exc:
            await self.safe_error(
                websocket,
                request_id,
                502,
                f"Could not reach LM Studio: {exc}",
            )

    async def safe_error(
        self, websocket: Any, request_id: str, status: int, message: str
    ) -> None:
        try:
            await self.send(
                websocket,
                {
                    "type": "error",
                    "id": request_id,
                    "status": status,
                    "message": message,
                },
            )
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="source-overlap-connect",
        description=(
            "Connect a local LM Studio server to the hosted Source Overlap app."
        ),
    )
    parser.add_argument(
        "--server",
        required=True,
        help="Hosted app URL, for example https://source-overlap.onrender.com",
    )
    parser.add_argument(
        "--code",
        required=True,
        help="Pairing code shown by the hosted app",
    )
    parser.add_argument(
        "--lm-studio-url",
        default="http://127.0.0.1:1234/v1",
        help="Local LM Studio OpenAI-compatible base URL",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    relay = Relay(args.server, args.code, args.lm_studio_url)
    try:
        return asyncio.run(relay.run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
