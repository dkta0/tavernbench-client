"""
TavernBench Python SDK — Phoenix Channels client over raw WebSocket.
Protocol: /docs/protocol.md
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# State model
# ---------------------------------------------------------------------------

@dataclass
class Position:
    x: int
    y: int

    def __repr__(self):
        return f"({self.x}, {self.y})"


@dataclass
class Entity:
    type: str          # player | npc | enemy | item | exit
    id: str
    name: str
    position: Position
    distance: float
    health: Optional[int] = None
    max_health: Optional[int] = None


@dataclass
class InventoryItem:
    id: str
    name: str
    quantity: int


@dataclass
class QuestObjective:
    id: str
    description: str
    complete: bool


@dataclass
class Quest:
    id: str
    name: str
    description: str
    objectives: List[QuestObjective]
    complete: bool


@dataclass
class Zone:
    id: str
    width: int
    height: int


@dataclass
class GameState:
    """Updated on every tick broadcast."""
    tick: int = 0
    timestamp_ms: int = 0
    zone_id: str = ""
    zone: Optional[Zone] = None
    position: Optional[Position] = None
    entities: List[Entity] = field(default_factory=list)
    inventory: List[InventoryItem] = field(default_factory=list)
    quest_log: List[Quest] = field(default_factory=list)
    score: int = 0
    steps: int = 0
    acked_seqs: List[int] = field(default_factory=list)

    # helpers
    def visible(self, type_filter: Optional[str] = None) -> List[Entity]:
        if type_filter:
            return [e for e in self.entities if e.type == type_filter]
        return list(self.entities)

    def nearest(self, type_filter: Optional[str] = None) -> Optional[Entity]:
        candidates = self.visible(type_filter)
        if not candidates:
            return None
        return min(candidates, key=lambda e: e.distance)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return next((e for e in self.entities if e.id == entity_id), None)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class TavernBenchError(Exception):
    """Base SDK exception."""


class AuthError(TavernBenchError):
    """Raised when authentication fails (HTTP 403 before WS upgrade)."""


class ChannelError(TavernBenchError):
    """Raised when a channel join/action returns status='error'."""
    def __init__(self, code: str, response: dict):
        self.code = code
        self.response = response
        super().__init__(f"Channel error: {code} — {response}")


class ActionError(TavernBenchError):
    """Raised when an action reply comes back with status='error'."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Action error: {code}")


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

class AsyncClient:
    """
    Async TavernBench client.

    Usage::

        async with AsyncClient("ws://localhost:4100", api_key="test-key") as tb:
            await tb.join("tavern_hall")
            await tb.move("north")
            print(tb.state.position)
    """

    PROTOCOL_VERSION = "1.0"

    def __init__(
        self,
        host: str = "ws://localhost:4100",
        api_key: str = "",
        *,
        heartbeat_interval: float = 30.0,
        on_dialogue: Optional[Callable[[str, str, str, list], Any]] = None,
        on_quest_complete: Optional[Callable[[int, int], Any]] = None,
        on_event: Optional[Callable[[str, dict], Any]] = None,
    ):
        """
        Args:
            host: WebSocket base URL (ws:// or wss://).
            api_key: API key passed as query param on connect.
            heartbeat_interval: Seconds between heartbeat pings (default 30).
            on_dialogue: callback(npc_id, npc_name, text, choices)
            on_quest_complete: callback(final_score, steps_taken)
            on_event: callback(event_type, payload_dict)
        """
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.heartbeat_interval = heartbeat_interval
        self.state = GameState()

        # callbacks
        self._on_dialogue = on_dialogue
        self._on_quest_complete = on_quest_complete
        self._on_event = on_event

        self._ws = None
        self._ref = 0
        self._join_ref = None
        self._topic: Optional[str] = None
        self._player_id: Optional[str] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._recv_task: Optional[asyncio.Task] = None
        self._hb_task: Optional[asyncio.Task] = None
        self._connected = False
        self._tick_event: Optional[asyncio.Event] = None

    # ---- lifecycle --------------------------------------------------------

    async def connect(self):
        """Open the WebSocket connection. Called automatically by __aenter__."""
        import websockets
        uri = f"{self.host}/socket/websocket?api_key={self.api_key}&protocol_version={self.PROTOCOL_VERSION}&vsn=2.0.0"
        try:
            self._ws = await websockets.connect(uri)
        except Exception as exc:
            if "403" in str(exc) or "Forbidden" in str(exc):
                raise AuthError(f"Server rejected API key (403): {exc}") from exc
            raise
        self._connected = True
        self._recv_task = asyncio.create_task(self._recv_loop())
        self._hb_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(self):
        """Close the WebSocket and cancel background tasks."""
        if self._recv_task:
            self._recv_task.cancel()
        if self._hb_task:
            self._hb_task.cancel()
        if self._ws:
            await self._ws.close()
        self._connected = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()

    # ---- channel management -----------------------------------------------

    async def join(self, zone_id: str) -> dict:
        """
        Join a zone channel. Must be called before sending actions.

        Args:
            zone_id: Zone identifier, e.g. "tavern_hall".

        Returns:
            Server join reply payload.

        Raises:
            ChannelError: If the server rejects the join.
        """
        self._topic = f"zone:{zone_id}"
        self._join_ref = self._next_ref()
        fut = self._make_future(self._join_ref)
        msg = [self._join_ref, self._join_ref, self._topic, "phx_join",
               {"protocol_version": self.PROTOCOL_VERSION}]
        await self._send(msg)
        reply = await fut
        if reply.get("status") != "ok":
            raise ChannelError(
                reply.get("response", {}).get("reason", "join_failed"),
                reply.get("response", {}),
            )
        self._player_id = reply.get("response", {}).get("player_id")
        initial_score = reply.get("response", {}).get("score")
        if initial_score is not None:
            self.state.score = initial_score
        return reply

    async def leave(self):
        """Leave the current zone channel."""
        if not self._topic:
            return
        ref = self._next_ref()
        msg = [self._join_ref, ref, self._topic, "phx_leave", {}]
        await self._send(msg)
        self._topic = None

    # ---- actions ----------------------------------------------------------

    async def move(self, direction: str, seq: Optional[int] = None) -> dict:
        """Move in a cardinal/intercardinal direction."""
        payload: dict = {"direction": direction}
        if seq is not None:
            payload["seq"] = seq
        return await self._action("action:move", payload)

    async def enter(self, target: str) -> dict:
        """Enter an exit/portal (zone transition)."""
        return await self._action("action:enter", {"target": target})

    async def speak(self, target: str) -> dict:
        """Initiate dialogue with an NPC."""
        return await self._action("action:speak", {"target": target})

    async def reply(self, choice: int) -> dict:
        """Select a dialogue choice."""
        return await self._action("action:reply", {"choice": choice})

    async def examine(self, target: str) -> dict:
        """Examine an entity."""
        return await self._action("action:examine", {"target": target})

    async def pickup(self, target: str) -> dict:
        """Pick up an item."""
        return await self._action("action:pickup", {"target": target})

    async def drop(self, item: str) -> dict:
        """Drop an inventory item."""
        return await self._action("action:drop", {"item": item})

    async def use(self, item: str, target: Optional[str] = None) -> dict:
        """Use an inventory item, optionally on a target."""
        payload: dict = {"item": item}
        if target is not None:
            payload["target"] = target
        return await self._action("action:use", payload)

    async def attack(self, target: str) -> dict:
        """Attack an enemy."""
        return await self._action("action:attack", {"target": target})

    async def flee(self) -> dict:
        """Flee from combat."""
        return await self._action("action:flee", {})

    async def inventory(self) -> dict:
        """Request inventory list (triggers 'inventory' event push)."""
        return await self._action("action:inventory", {})

    async def quests(self) -> dict:
        """Request quest log (triggers 'quests' event push)."""
        return await self._action("action:quests", {})

    async def look(self) -> dict:
        """Request immediate state broadcast."""
        return await self._action("action:look", {})

    async def wait_turn(self) -> dict:
        """Do nothing for this tick."""
        return await self._action("action:wait", {})

    async def wait_tick(self, n: int = 1):
        """Await n tick broadcasts from the server."""
        for _ in range(n):
            await self._wait_for_tick()

    # ---- internals --------------------------------------------------------

    def _next_ref(self) -> str:
        self._ref += 1
        return str(self._ref)

    def _make_future(self, ref: str) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[ref] = fut
        return fut

    async def _send(self, msg: list):
        await self._ws.send(json.dumps(msg))

    async def _action(self, event: str, payload: dict) -> dict:
        if not self._topic:
            raise TavernBenchError("Not joined to any zone. Call join() first.")
        ref = self._next_ref()
        fut = self._make_future(ref)
        msg = [self._join_ref, ref, self._topic, event, payload]
        await self._send(msg)
        reply = await asyncio.wait_for(fut, timeout=10.0)
        if reply.get("status") == "error":
            code = reply.get("response", {}).get("code", "UNKNOWN_ERROR")
            raise ActionError(code)
        return reply

    async def _recv_loop(self):
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                    await self._dispatch(msg)
                except Exception:
                    pass
        except Exception:
            pass

    async def _dispatch(self, msg: list):
        if not isinstance(msg, list) or len(msg) != 5:
            return
        join_ref, ref, topic, event, payload = msg

        # resolve pending futures
        if event == "phx_reply" and ref and ref in self._pending:
            fut = self._pending.pop(ref)
            if not fut.done():
                fut.set_result(payload)
            return

        # state tick
        if event == "tick":
            self._apply_tick(payload)
            if self._tick_event is not None:
                self._tick_event.set()
                self._tick_event = None
            return

        # dialogue push
        if event == "dialogue":
            if self._on_dialogue:
                asyncio.ensure_future(
                    self._call_async_or_sync(
                        self._on_dialogue,
                        payload.get("npc_id", ""),
                        payload.get("npc", ""),
                        payload.get("text", ""),
                        payload.get("choices", []),
                    )
                )
            return

        # quest_complete push
        if event == "quest_complete":
            if self._on_quest_complete:
                asyncio.ensure_future(
                    self._call_async_or_sync(
                        self._on_quest_complete,
                        payload.get("final_score", 0),
                        payload.get("steps_taken", 0),
                    )
                )
            return

        # generic event push
        if event == "event":
            etype = payload.get("type", "")
            if etype == "zone_change":
                # The Phoenix channel server re-subscribes to the new zone's PubSub
                # and updates socket.assigns.zone_id server-side. We do NOT change
                # self._topic here — all actions continue going to the original joined
                # topic; the channel process routes them to the correct zone.
                new_zone = payload.get("to_zone") or payload.get("zone_id")
                if new_zone:
                    self.state.zone_id = new_zone
            elif etype == "score_update":
                score = payload.get("score")
                if score is not None:
                    self.state.score = score
            if self._on_event:
                asyncio.ensure_future(
                    self._call_async_or_sync(self._on_event, etype, payload)
                )
            return

    async def _call_async_or_sync(self, fn, *args):
        result = fn(*args)
        if asyncio.iscoroutine(result):
            await result

    def _apply_tick(self, p: dict):
        s = self.state
        s.tick = p.get("tick", s.tick)
        s.timestamp_ms = p.get("timestamp_ms", s.timestamp_ms)
        s.zone_id = p.get("zone_id", s.zone_id)
        if "zone" in p:
            z = p["zone"]
            s.zone = Zone(id=z["id"], width=z["width"], height=z["height"])
        if "position" in p:
            pos = p["position"]
            s.position = Position(x=pos["x"], y=pos["y"])
        if "entities" in p:
            s.entities = [
                Entity(
                    type=e["type"],
                    id=e["id"],
                    name=e["name"],
                    position=Position(x=e["position"]["x"], y=e["position"]["y"]),
                    distance=e.get("distance", 0.0),
                    health=e.get("health"),
                    max_health=e.get("max_health"),
                )
                for e in p["entities"]
            ]
            # Extract own position from the player entity matching our player_id
            if "position" not in p:
                for e in p["entities"]:
                    is_self = (
                        self._player_id and e.get("id") == f"player_{self._player_id}"
                    ) or (
                        e.get("type") == "player" and float(e.get("distance", -1)) == 0.0
                        and not self._player_id
                    )
                    if is_self:
                        s.position = Position(x=e["position"]["x"], y=e["position"]["y"])
                        break
        if "inventory" in p:
            s.inventory = [
                InventoryItem(id=i["id"], name=i["name"], quantity=i["quantity"])
                for i in p["inventory"]
            ]
        if "quest_log" in p:
            s.quest_log = [
                Quest(
                    id=q["id"],
                    name=q["name"],
                    description=q.get("description", ""),
                    objectives=[
                        QuestObjective(id=o["id"], description=o["description"], complete=o["complete"])
                        for o in q.get("objectives", [])
                    ],
                    complete=q.get("complete", False),
                )
                for q in p["quest_log"]
            ]
        if "score" in p:
            s.score = p["score"]
        if "steps" in p:
            s.steps = p["steps"]
        if "acked_seqs" in p:
            s.acked_seqs = p["acked_seqs"]

    async def _wait_for_tick(self):
        self._tick_event = asyncio.Event()
        await asyncio.wait_for(self._tick_event.wait(), timeout=5.0)

    async def _heartbeat_loop(self):
        hb_ref = 0
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            hb_ref += 1
            msg = [None, f"hb-{hb_ref}", "phoenix", "heartbeat", {}]
            try:
                await self._send(msg)
            except Exception:
                break


# ---------------------------------------------------------------------------
# Blocking (sync) wrapper
# ---------------------------------------------------------------------------

class Client:
    """
    Blocking TavernBench client. Wraps AsyncClient and runs an event loop
    in a background thread.

    Usage::

        with Client("ws://localhost:4100", api_key="test-key") as tb:
            tb.join("tavern_hall")
            tb.move("north")
            print(tb.state.position)
    """

    def __init__(self, host: str = "ws://localhost:4100", api_key: str = "", **kwargs):
        self._async = AsyncClient(host, api_key, **kwargs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def state(self) -> GameState:
        return self._async.state

    def connect(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._run(self._async.connect())

    def disconnect(self):
        self._run(self._async.disconnect())
        self._loop.call_soon_threadsafe(self._loop.stop)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=15)

    def join(self, zone_id: str) -> dict:
        return self._run(self._async.join(zone_id))

    def leave(self):
        return self._run(self._async.leave())

    def move(self, direction: str, seq: Optional[int] = None) -> dict:
        return self._run(self._async.move(direction, seq))

    def enter(self, target: str) -> dict:
        return self._run(self._async.enter(target))

    def speak(self, target: str) -> dict:
        return self._run(self._async.speak(target))

    def reply(self, choice: int) -> dict:
        return self._run(self._async.reply(choice))

    def examine(self, target: str) -> dict:
        return self._run(self._async.examine(target))

    def pickup(self, target: str) -> dict:
        return self._run(self._async.pickup(target))

    def drop(self, item: str) -> dict:
        return self._run(self._async.drop(item))

    def use(self, item: str, target: Optional[str] = None) -> dict:
        return self._run(self._async.use(item, target))

    def attack(self, target: str) -> dict:
        return self._run(self._async.attack(target))

    def flee(self) -> dict:
        return self._run(self._async.flee())

    def inventory(self) -> dict:
        return self._run(self._async.inventory())

    def quests(self) -> dict:
        return self._run(self._async.quests())

    def look(self) -> dict:
        return self._run(self._async.look())

    def wait_turn(self) -> dict:
        return self._run(self._async.wait_turn())

    def wait_tick(self, n: int = 1):
        return self._run(self._async.wait_tick(n))
