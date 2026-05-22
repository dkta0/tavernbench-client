"""
example.py — Simple TavernBench agent loop using the Python SDK.

This agent:
1. Connects and joins the tavern_hall zone
2. Moves north a few times
3. Speaks to any visible NPC
4. Waits for dialogue and picks the first choice
5. Reports final score on quest_complete

Run:
    cd clients/python
    pip install websockets
    python example.py
"""

import asyncio
import tavernbench as tb

HOST = "ws://localhost:4100"
API_KEY = "test-key"
ZONE = "tavern_hall"


async def main():
    final_score = None
    final_steps = None

    def on_dialogue(npc_id, npc_name, text, choices):
        print(f"\n[DIALOGUE] {npc_name}: {text}")
        for c in choices:
            print(f"  [{c['id']}] {c['text']}")

    def on_quest_complete(score, steps):
        nonlocal final_score, final_steps
        final_score = score
        final_steps = steps
        print(f"\n[QUEST COMPLETE] Score: {score}, Steps: {steps}")

    def on_event(etype, payload):
        if etype == "npc_spoke":
            print(f"[NPC] {payload.get('npc')}: {payload.get('text')}")
        elif etype == "combat":
            print(f"[COMBAT] {payload.get('attacker')} -> {payload.get('target')}: {payload.get('damage')} dmg")
        elif etype == "entity_died":
            print(f"[DIED] {payload.get('entity_name')}")
        elif etype == "zone_entered":
            print(f"[ZONE] {payload.get('from_zone')} -> {payload.get('to_zone')}")
        else:
            print(f"[EVENT] {etype}: {payload}")

    async with tb.AsyncClient(
        HOST,
        api_key=API_KEY,
        on_dialogue=on_dialogue,
        on_quest_complete=on_quest_complete,
        on_event=on_event,
    ) as client:
        print(f"Connected to {HOST}")

        # Join zone
        await client.join(ZONE)
        print(f"Joined zone: {ZONE}")

        # Wait for first tick so state is populated
        await client.wait_tick()
        s = client.state
        print(f"Position: {s.position}  Entities visible: {len(s.entities)}  Score: {s.score}")

        # Simple agent loop: up to 30 steps
        for step in range(30):
            s = client.state

            # If there's an NPC nearby, speak to it
            npc = s.nearest("npc")
            if npc and npc.distance <= 2.0:
                print(f"[ACTION] speak -> {npc.id}")
                try:
                    await client.speak(npc.id)
                    await client.wait_tick()
                    # Reply with choice 1
                    await client.reply(1)
                    await client.wait_tick()
                    continue
                except tb.ActionError as e:
                    print(f"  speak error: {e.code}")

            # If there's an exit nearby, enter it
            exit_ent = s.nearest("exit")
            if exit_ent and exit_ent.distance <= 2.0:
                print(f"[ACTION] enter -> {exit_ent.id}")
                try:
                    await client.enter(exit_ent.id)
                    await client.wait_tick()
                    continue
                except tb.ActionError as e:
                    print(f"  enter error: {e.code}")

            # If there's an enemy, attack
            enemy = s.nearest("enemy")
            if enemy:
                print(f"[ACTION] attack -> {enemy.id}")
                try:
                    await client.attack(enemy.id)
                    await client.wait_tick()
                    continue
                except tb.ActionError as e:
                    print(f"  attack error: {e.code}")

            # Otherwise move north toward exits/npcs
            print("[ACTION] move north")
            try:
                await client.move("north")
            except tb.ActionError as e:
                print(f"  move error: {e.code} — trying east")
                try:
                    await client.move("east")
                except tb.ActionError:
                    await client.wait_turn()

            await client.wait_tick()

            if final_score is not None:
                print(f"\nDone! Final score: {final_score} in {final_steps} steps.")
                break

        # Final state summary
        s = client.state
        print(f"\n--- Final state ---")
        print(f"  Zone:     {s.zone_id}")
        print(f"  Position: {s.position}")
        print(f"  Score:    {s.score}")
        print(f"  Steps:    {s.steps}")
        print(f"  Inventory: {[i.name for i in s.inventory]}")


if __name__ == "__main__":
    asyncio.run(main())
