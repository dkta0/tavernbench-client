"""
TavernBench end-to-end test: heuristic agent drives 'The Missing Apprentice'.

No ANTHROPIC_API_KEY required. The agent uses game-state logic based on
the optimal path from priv/scenarios/missing_apprentice.yaml.

Usage:
    cd /home/hermes/tavernbench-client
    python test_hermes.py

SDK BUGS discovered (listed in report at end):
  BUG-1: Session default zone='lobby' doesn't match scenario start_zone='tavern'.
  BUG-2: Tick broadcast does not include player-specific fields (steps, inventory,
         quest_log). state.steps and state.inventory in session.state always read 0/[]
         unless a dedicated inventory/quests action is called first. This makes
         session.state unreliable as a sole source of truth for score/steps.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "sdk"))

from tavernbench import Session

SDK_BUGS = [
    "BUG-1: Session default zone='lobby' doesn't match scenario start_zone='tavern'. "
    "Callers must pass zone='tavern' explicitly.",

    "BUG-2: server tick broadcast omits player-specific fields (steps, inventory, "
    "quest_log, score). session.state['steps'] is always 0. "
    "Only quest_complete event carries the authoritative final score and step count.",
]

TICK = 0.7   # seconds — just over 500ms server tick

# ── Connect ────────────────────────────────────────────────────────────────────
print("Connecting (zone=tavern)...")
session = Session(api_key="dev-key", server="ws://localhost:4100", zone="tavern")
time.sleep(TICK)
init = session.state
print(f"Connected: zone={init.get('zone')} score={init.get('score')} "
      f"visible={len(init.get('visible',[]))} entities")
print()

# ── Helpers ───────────────────────────────────────────────────────────────────
MAX_TURNS = 80
tool_calls_log = []
step = 0


def do(tool_name, wait=None, **kwargs):
    global step
    if session.complete or step >= MAX_TURNS:
        return None
    step += 1
    result = session.call({"name": tool_name, "input": kwargs})
    time.sleep(wait if wait is not None else TICK)
    state = session.state

    tool_calls_log.append({
        "step": step, "tool": tool_name, "input": kwargs, "result": result,
    })

    args_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    event = result.get("event")
    msg = result.get("message", "")
    ok = result.get("success", False)
    print(f"[{step:02d}] {tool_name}({args_str})")
    print(f"     ok={ok}  zone={state.get('zone','')}  score={state.get('score',0)}")
    if msg and msg not in ("ok", ""):
        print(f"     msg: {msg}")
    if event:
        print(f"     event: {event}")
    print()
    return result


def move_to_zone(direction, target_zone, max_moves=12):
    for _ in range(max_moves):
        if session.complete:
            return
        do("move", direction=direction)
        if session.state.get("zone") == target_zone:
            return
    current = session.state.get("zone", "?")
    if current != target_zone:
        print(f"  !! WARNING: expected zone {target_zone}, got {current}")


def get_entity(entity_id):
    """Return entity from current state visible list."""
    for e in session.state.get("visible", []):
        if e.get("id") == entity_id:
            return e
    return None


def attack_until_dead(enemy_id, max_attacks=8):
    """Keep attacking enemy until it disappears from entities."""
    for i in range(max_attacks):
        if session.complete:
            break
        enemy = get_entity(enemy_id)
        if enemy is None:
            print(f"  -> {enemy_id} is dead (not in entities)")
            break
        hp = enemy.get("health", "?")
        print(f"  (attack {i+1}: {enemy_id} HP={hp})")
        do("attack", target_id=enemy_id, wait=TICK)


# ── Optimal path for The Missing Apprentice ───────────────────────────────────
print("=== HEURISTIC AGENT: The Missing Apprentice ===")
print(f"Tools: {[t['name'] for t in session.tools_anthropic]}")
print()

# --- TAVERN: get barkeep clue ---
do("look")
do("speak", target_id="npc_barkeep")
do("reply", choice=1)        # "Where did the apprentice go?" → clue_north flag

# Walk north: spawn (3,3), exit at (3,0) → 3 steps
move_to_zone("north", "village_square")

# --- VILLAGE SQUARE: dismiss elder red herring ---
do("look")
do("speak", target_id="npc_village_elder")
do("reply", choice=3)        # "Thanks, I'll look around." — no red herring, no penalty

# Walk north to forest_path: spawn (3,6), exit at (3,0) → 6 steps
move_to_zone("north", "forest_path")

# --- FOREST PATH: get woodcutter clue ---
do("speak", target_id="npc_woodcutter")
do("reply", choice=1)        # confirms clearing + wolf → clue_clearing, clue_wolf_danger

# Walk north to forest_clearing: spawn (3,6), exit at (3,0) → 6 steps
move_to_zone("north", "forest_clearing")

# --- FOREST CLEARING: pickup satchel, defeat wolf ---
do("look")                               # spot wolf and satchel
do("pickup", target_id="item_satchel")  # bonus +10 → has_satchel flag
attack_until_dead("enemy_wolf")          # kills wolf → killed_wolf flag

if not session.complete:
    # Return to tavern to trigger quest_complete
    # completion_trigger: zone=tavern + killed_wolf flag
    print("--- Returning to tavern for quest completion ---")
    move_to_zone("south", "forest_path")
    move_to_zone("south", "village_square")
    move_to_zone("south", "tavern")
    time.sleep(1.5)  # wait for quest_complete event

# ── Report ────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("BENCHMARK REPORT")
print("=" * 60)
final_state = session.state
print(f"Quest completed:   {'YES' if session.complete else 'NO'}")
final_score = session.score if session.score is not None else final_state.get("score", "N/A")
print(f"Final score:       {final_score}")
print(f"Steps (server):    {final_state.get('steps', '?')}")
print(f"Turns in script:   {step}")
print()

print("First 10 tool calls:")
for tc in tool_calls_log[:10]:
    args_str = ", ".join(f"{k}={v}" for k, v in tc["input"].items())
    ok = tc["result"].get("success", False)
    print(f"  [{tc['step']:02d}] {tc['tool']}({args_str})  -> success={ok}")

print()
print("SDK CHECKS:")
print(f"  system_prompt present:         {'YES' if session.system_prompt else 'NO'} ({len(session.system_prompt)} chars)")
print(f"  tools (OpenAI) count:          {len(session.tools)}")
print(f"  tools_anthropic count:         {len(session.tools_anthropic)}")
anthropic_valid = all("name" in t and "description" in t and "input_schema" in t for t in session.tools_anthropic)
print(f"  tools_anthropic format valid:  {'YES' if anthropic_valid else 'NO'}")
print(f"  session.complete is bool:      {isinstance(session.complete, bool)}")
print(f"  session.score type:            {type(session.score).__name__}")
r0 = tool_calls_log[0]["result"] if tool_calls_log else {}
print(f"  call() return keys:            {sorted(r0.keys())}")
print(f"  state keys:                    {sorted(final_state.keys())}")
print()

print("SDK BUGS FOUND:")
for bug in SDK_BUGS:
    print(f"  {bug}")
    print()

session.close()
print("Done.")
