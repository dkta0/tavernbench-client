"""
TavernBench Session — high-level LLM-friendly wrapper around the low-level Client.

Usage:
    from tavernbench import Session

    session = Session(api_key="tb-xxx", server="ws://localhost:4100")

    while not session.complete:
        response = your_llm(
            system=session.system_prompt,
            tools=session.tools,
            messages=your_context,
        )
        result = session.call(response.tool_call)
        # result is a dict to feed back into context

    session.close()
    print(f"Score: {session.score}")
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .websocket import Client, ActionError
from .tools import TOOLS_OPENAI, TOOLS_ANTHROPIC
from .prompts import DEFAULT_SYSTEM_PROMPT


class Session:
    """
    Synchronous TavernBench session wrapping Client.

    Parameters
    ----------
    api_key:
        Your TavernBench API key (e.g. "tb-xxx").
    server:
        WebSocket base URL (default: "ws://localhost:4100").
    zone:
        Zone / channel to join on connect (default: "lobby").
    system_prompt:
        Override the default agent system prompt.
    """

    def __init__(
        self,
        api_key: str,
        server: str = "ws://localhost:4100",
        zone: str = "lobby",
        system_prompt: Optional[str] = None,
    ):
        self._client = Client(host=server, api_key=api_key)
        self._zone = zone
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._complete = False
        self._score: Optional[int] = None
        self._last_event: Optional[Dict[str, Any]] = None

        # Wire quest_complete callback
        self._client._async._on_quest_complete = self._handle_quest_complete
        self._client._async._on_event = self._handle_event

        # Connect and join
        self._client.connect()
        self._client.join(zone)

    # ---- properties -------------------------------------------------------

    @property
    def tools(self) -> List[Dict[str, Any]]:
        """Tool definitions in OpenAI function-calling format."""
        return TOOLS_OPENAI

    @property
    def tools_anthropic(self) -> List[Dict[str, Any]]:
        """Tool definitions in Anthropic function-calling format."""
        return TOOLS_ANTHROPIC

    @property
    def system_prompt(self) -> str:
        """Default system prompt for LLM agents."""
        return self._system_prompt

    @property
    def state(self) -> Dict[str, Any]:
        """Current game state as a plain dict."""
        s = self._client.state
        return {
            "zone": s.zone_id,
            "position": {"x": s.position.x, "y": s.position.y} if s.position else None,
            "visible": [
                {
                    "type": e.type,
                    "id": e.id,
                    "name": e.name,
                    "distance": e.distance,
                    "health": e.health,
                    "max_health": e.max_health,
                }
                for e in s.entities
            ],
            "inventory": [
                {"id": i.id, "name": i.name, "quantity": i.quantity}
                for i in s.inventory
            ],
            "quests": [
                {
                    "id": q.id,
                    "name": q.name,
                    "description": q.description,
                    "complete": q.complete,
                    "objectives": [
                        {"id": o.id, "description": o.description, "complete": o.complete}
                        for o in q.objectives
                    ],
                }
                for q in s.quest_log
            ],
            "score": s.score,
            "steps": s.steps,
        }

    @property
    def complete(self) -> bool:
        """True once the server fires quest_complete."""
        return self._complete

    @property
    def score(self) -> Optional[int]:
        """Final score — None until quest_complete is received."""
        return self._score

    # ---- main API ---------------------------------------------------------

    def call(self, tool_call: Any) -> Dict[str, Any]:
        """
        Execute a tool call returned by an LLM.

        Accepts either:
        - An object with .function.name / .function.arguments (OpenAI ChatCompletionMessageToolCall)
        - A dict with {"name": ..., "input": ...} (Anthropic ToolUseBlock style)
        - A dict with {"name": ..., "arguments": ...}

        Returns a structured result dict:
            success: bool
            state:   updated game state
            event:   last event dict (or None)
            message: human-readable description
        """
        name, args = self._parse_tool_call(tool_call)
        self._last_event = None
        try:
            raw = self._dispatch(name, args)
            return self._make_result(True, raw, None)
        except ActionError as exc:
            return self._make_result(False, None, exc.code)
        except Exception as exc:
            return self._make_result(False, None, str(exc))

    def close(self):
        """Disconnect from the server."""
        self._client.disconnect()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ---- internals --------------------------------------------------------

    def _handle_quest_complete(self, final_score: int, steps_taken: int):
        self._complete = True
        self._score = final_score
        self._last_event = {"type": "quest_complete", "final_score": final_score, "steps_taken": steps_taken}

    def _handle_event(self, event_type: str, payload: dict):
        self._last_event = {"type": event_type, **payload}

    @staticmethod
    def _parse_tool_call(tool_call: Any):
        """Return (name, args_dict) from any common LLM tool call shape."""
        import json

        # OpenAI ChatCompletionMessageToolCall object
        if hasattr(tool_call, "function"):
            fn = tool_call.function
            name = fn.name
            args = fn.arguments
            if isinstance(args, str):
                args = json.loads(args) if args else {}
            return name, args

        # dict shapes
        if isinstance(tool_call, dict):
            name = tool_call.get("name") or tool_call.get("tool_name", "")
            # Anthropic: {"input": {...}}
            args = tool_call.get("input") or tool_call.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args) if args else {}
            return name, args

        raise ValueError(f"Unrecognised tool_call shape: {type(tool_call)}")

    def _dispatch(self, name: str, args: dict) -> dict:
        c = self._client
        if name == "move":
            return c.move(args["direction"])
        if name == "look":
            return c.look()
        if name == "speak":
            return c.speak(args["target_id"])
        if name == "reply":
            return c.reply(int(args["choice"]))
        if name == "examine":
            return c.examine(args["target_id"])
        if name == "pickup":
            return c.pickup(args["target_id"])
        if name == "drop":
            return c.drop(args["target_id"])
        if name == "use":
            return c.use(args["item_id"], args.get("on"))
        if name == "attack":
            return c.attack(args["target_id"])
        if name == "flee":
            return c.flee()
        if name == "inventory":
            return c.inventory()
        if name == "quests":
            return c.quests()
        if name == "wait":
            return c.wait_turn()
        raise ValueError(f"Unknown tool: {name}")

    def _make_result(
        self, success: bool, raw_reply: Optional[dict], error: Optional[str]
    ) -> Dict[str, Any]:
        if not success:
            return {
                "success": False,
                "state": self.state,
                "event": self._last_event,
                "message": f"Action failed: {error}",
            }
        # raw_reply is the Phoenix channel reply payload
        response = raw_reply.get("response", {}) if raw_reply else {}
        message = response.get("message") or response.get("reason") or "ok"
        event = self._last_event or response.get("event")
        return {
            "success": True,
            "state": self.state,
            "event": event,
            "message": message,
        }
