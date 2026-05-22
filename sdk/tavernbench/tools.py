"""
TavernBench tool definitions — OpenAI and Anthropic function-calling formats.
"""
from __future__ import annotations
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# OpenAI format: {type: "function", function: {name, description, parameters}}
# ---------------------------------------------------------------------------

TOOLS_OPENAI: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": "Move your character one step in a cardinal direction. Returns updated game state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["north", "south", "east", "west"],
                        "description": "Direction to move.",
                    }
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look",
            "description": "Re-broadcast current zone state — useful to refresh what entities are visible around you.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "speak",
            "description": "Initiate dialogue with an NPC or entity. Use the entity's id from the visible entities list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "The id of the NPC or entity to speak with.",
                    }
                },
                "required": ["target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reply",
            "description": "Select a numbered dialogue choice during an active conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "choice": {
                        "type": "integer",
                        "description": "The 1-based dialogue choice number to select.",
                    }
                },
                "required": ["choice"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "examine",
            "description": "Examine an entity for more detail — items reveal their use, NPCs may give hints.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "The id of the entity to examine.",
                    }
                },
                "required": ["target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pickup",
            "description": "Pick up an item from the ground and add it to your inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "The id of the item to pick up.",
                    }
                },
                "required": ["target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drop",
            "description": "Drop an inventory item onto the ground.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "The id of the inventory item to drop.",
                    }
                },
                "required": ["target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "use",
            "description": "Use an item from your inventory, optionally on a target entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "The id of the inventory item to use.",
                    },
                    "on": {
                        "type": "string",
                        "description": "Optional target entity id to use the item on.",
                    },
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attack",
            "description": "Attack a visible enemy or hostile entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "The id of the enemy to attack.",
                    }
                },
                "required": ["target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flee",
            "description": "Flee from combat. Moves you away from the current fight but may incur a score penalty.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inventory",
            "description": "List everything currently in your inventory.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quests",
            "description": "Show your active quests and their current objectives.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Do nothing this turn — skip your action tick.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Anthropic format: {name, description, input_schema}
# ---------------------------------------------------------------------------

def _to_anthropic(tool: Dict[str, Any]) -> Dict[str, Any]:
    fn = tool["function"]
    return {
        "name": fn["name"],
        "description": fn["description"],
        "input_schema": fn["parameters"],
    }


TOOLS_ANTHROPIC: List[Dict[str, Any]] = [_to_anthropic(t) for t in TOOLS_OPENAI]
