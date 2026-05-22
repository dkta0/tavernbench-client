"""
TavernBench Python SDK

High-level:
    from tavernbench import Session

Low-level (legacy):
    from tavernbench import AsyncClient, Client
"""

from .session import Session
from .websocket import (
    AsyncClient,
    Client,
    GameState,
    Position,
    Entity,
    InventoryItem,
    QuestObjective,
    Quest,
    Zone,
    TavernBenchError,
    AuthError,
    ChannelError,
    ActionError,
)
from .tools import TOOLS_OPENAI, TOOLS_ANTHROPIC
from .prompts import DEFAULT_SYSTEM_PROMPT

__all__ = [
    "Session",
    # low-level
    "AsyncClient",
    "Client",
    "GameState",
    "Position",
    "Entity",
    "InventoryItem",
    "QuestObjective",
    "Quest",
    "Zone",
    "TavernBenchError",
    "AuthError",
    "ChannelError",
    "ActionError",
    # tool defs
    "TOOLS_OPENAI",
    "TOOLS_ANTHROPIC",
    "DEFAULT_SYSTEM_PROMPT",
]
