"""Create or join a XIANG room over a WebRTC data channel on Zero."""

import asyncio
from concurrent.futures import TimeoutError
import json
import os
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from lan import Room, RoomError

ROOM_CODE_LENGTH = 6
SIGNAL_URL = os.environ.get("XIANG_SIGNAL_URL",
    "https://wmoaxlrncbfcsyqtfbku.supabase.co/functions/v1/xiang-pair")


def signal(action, timeout=8, **data):
    message = Request(SIGNAL_URL, json.dumps({"action": action, **data}).encode(),
                      {"Content-Type": "application/json"})
    try:
        with urlopen(message, timeout=timeout) as response:
            return json.loads(response.read(16384))
    except HTTPError as error:
        with error:
            try:
                result = json.loads(error.read(2048))
            except ValueError:
                result = {}
        raise RoomError(result.get("error", "pair_unavailable")) from error


class RtcPeer:
    def __init__(self, options=None):
        self.loop = None
        self.thread = None
        self.pc = None
        self.channel = None
        self.pending = {}
        self.sequence = 0
        self.closed = False
        self.error = ""
        self.room = Room(**options) if options is not None else None
        self.receipt = None
        self.pairing = None
        self.guest_token = None

    def __call__(self, action, **body):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            self.thread = Thread(target=self.loop.run_forever, daemon=True)
            self.thread.start()
        if action == "create":
            operation = self.host()
        elif action == "join":
            operation = self.join(body["code"])
        else:
            operation = self.send(action, body)
        starting = action in ("create", "join")
        task = asyncio.run_coroutine_threadsafe(operation, self.loop)
        try:
            return task.result(timeout=38 if starting else 4)
        except TimeoutError as error:
            task.cancel()
            raise RoomError("pair_failed") if starting else OSError("Peer timeout") from error
        except RoomError:
            raise
        except Exception as error:
            raise RoomError("pair_failed") if starting else OSError("Peer disconnected") from error

    def open_connection(self):
        try:
            from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        except ImportError as error:
            raise RoomError("rtc_missing") from error

        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.opened = asyncio.Event()

        @self.pc.on("connectionstatechange")
        def connection_changed():
            if self.pc.connectionState == "failed":
                self.mark_closed("pair_failed")

        return RTCSessionDescription

    def attach(self, channel):
        if channel.label != "xiang":
            channel.close()
            return
        self.channel = channel
        if channel.readyState == "open":
            self.channel_opened()
        channel.on("open", self.channel_opened)
        channel.on("message", self.receive)
        channel.on("close", self.mark_closed)

    def channel_opened(self):
        if self.room is not None and self.guest_token is None:
            self.guest_token = self.room.add_player()["token"]
        self.opened.set()

    async def host(self):
        description = self.open_connection()
        self.attach(self.pc.createDataChannel("xiang"))
        await self.pc.setLocalDescription(await self.pc.createOffer())
        self.receipt = await asyncio.to_thread(signal, "offer", sdp=self.pc.localDescription.sdp)
        seat = self.room.add_player()
        self.pairing = self.loop.create_task(self.wait_for_answer(description))
        return {**seat, "code": self.receipt["code"]}

    async def wait_for_answer(self, description):
        start = self.loop.time()
        try:
            while not self.closed:
                try:
                    answer = await asyncio.to_thread(signal, "status", **self.receipt)
                except RoomError as error:
                    if error.code == "room_closed":
                        self.mark_closed("pair_expired")
                        return
                    if error.code != "pair_unavailable":
                        raise
                except OSError:
                    pass
                else:
                    if answer["sdp"]:
                        await self.pc.setRemoteDescription(description(sdp=answer["sdp"], type="answer"))
                        await asyncio.wait_for(self.opened.wait(), timeout=16)
                        return
                if self.loop.time() - start >= 300:
                    self.mark_closed("pair_expired")
                    return
                await asyncio.sleep(1.5 if self.loop.time() - start < 30 else 3.5)
        except Exception:
            self.mark_closed("pair_failed")
        finally:
            await self.clear_receipt()

    async def clear_receipt(self):
        if self.receipt is not None:
            receipt, self.receipt = self.receipt, None
            try:
                await asyncio.to_thread(signal, "close", timeout=2, **receipt)
            except (OSError, RoomError):
                pass

    async def join(self, code):
        if len(code) != ROOM_CODE_LENGTH or any(char not in "0123456789" for char in code):
            raise RoomError("wrong_code")
        description = self.open_connection()
        self.pc.on("datachannel", self.attach)

        try:
            offer = await asyncio.to_thread(signal, "lookup", code=code)
            await self.pc.setRemoteDescription(description(sdp=offer["sdp"], type="offer"))
            await self.pc.setLocalDescription(await self.pc.createAnswer())
            await asyncio.to_thread(signal, "answer", code=code, key=str(uuid4()), sdp=self.pc.localDescription.sdp)
            await asyncio.wait_for(self.opened.wait(), timeout=16)
            result = await self.send("join", {"rematch": True})
            return {**result, "token": "peer"}
        except RoomError:
            raise
        except (OSError, ValueError, KeyError, asyncio.TimeoutError) as error:
            raise RoomError("pair_failed") from error

    def mark_closed(self, error="room_closed"):
        if self.closed:
            return
        self.closed = True
        self.error = error
        for request in self.pending.values():
            if not request.done():
                request.set_exception(RoomError(error))

    def receive(self, message):
        if not isinstance(message, str) or len(message) > 65536:
            return
        try:
            reply = json.loads(message)
        except ValueError:
            return
        if not isinstance(reply, dict):
            return
        if self.room is not None:
            request_id, data = reply.get("id"), reply.get("body")
            if type(request_id) is not int or self.guest_token is None:
                return
            response = {"id": request_id}
            try:
                response["result"] = self.room.call(reply.get("action"),
                                                     data if isinstance(data, dict) else {}, self.guest_token)
            except RoomError as error:
                response["error"] = error.code
            self.channel.send(json.dumps(response))
            return
        if reply.get("closed"):
            self.mark_closed()
            return
        request_id = reply.get("id")
        result = self.pending.get(request_id) if type(request_id) is int else None
        if result is not None and not result.done():
            if "error" in reply:
                result.set_exception(RoomError(reply["error"]))
            else:
                result.set_result(reply.get("result"))

    async def send(self, action, data):
        if self.closed:
            raise RoomError(self.error)
        if self.room is not None:
            result = self.room.call(action, data, data.get("token"))
            if action == "leave" and self.channel.readyState == "open":
                self.channel.send(json.dumps({"closed": True}))
            return result
        if self.channel is None or self.channel.readyState != "open":
            raise OSError("Peer disconnected")
        self.sequence += 1
        request_id = self.sequence
        future = self.pending[request_id] = self.loop.create_future()
        try:
            self.channel.send(json.dumps({"id": request_id, "action": action, "body": data}))
            return await asyncio.wait_for(future, timeout=3)
        finally:
            self.pending.pop(request_id, None)

    def close(self):
        if self.loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.shutdown(), self.loop).result(timeout=6)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=2)
            if not self.thread.is_alive():
                self.loop.close()

    async def shutdown(self):
        self.mark_closed()
        if self.pairing is not None and not self.pairing.done():
            self.pairing.cancel()
            await asyncio.gather(self.pairing, return_exceptions=True)
        await self.clear_receipt()
        if self.pc is not None:
            await self.pc.close()
