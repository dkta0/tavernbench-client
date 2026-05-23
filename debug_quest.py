"""Debug quest/flags after wolf kill."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'sdk'))
from tavernbench.websocket import Client

c = Client('ws://localhost:4100', api_key='dev-key')
c.connect()
c.join('tavern')
time.sleep(0.8)

TICK = 0.7

def move_to(direction, target_zone, max_moves=10):
    for _ in range(max_moves):
        c.move(direction)
        time.sleep(TICK)
        if c.state.zone_id == target_zone:
            print(f"  -> arrived at {target_zone}")
            return True
    print(f"  !! stuck at {c.state.zone_id}, wanted {target_zone}")
    return False

print("tavern: speaking to barkeep...")
c.speak("npc_barkeep")
time.sleep(TICK)

print("tavern: reply choice 1...")
c.reply(1)
time.sleep(TICK)

print("moving to village_square...")
move_to("north", "village_square")

print("moving to forest_path...")
move_to("north", "forest_path")

print("speaking to woodcutter...")
c.speak("npc_woodcutter")
time.sleep(TICK)
c.reply(1)
time.sleep(TICK)

print("moving to forest_clearing...")
move_to("north", "forest_clearing")

# check what's here
time.sleep(0.5)
print(f"forest_clearing entities: {[(e.type, e.id, e.name, e.health) for e in c.state.entities]}")

print("picking up satchel...")
r = c.pickup("item_satchel")
time.sleep(TICK)
print(f"  pickup result: {r}")

print("attacking wolf...")
r = c.attack("enemy_wolf")
time.sleep(TICK * 2)  # wait longer for combat resolution
print(f"  attack result: {r}")
print(f"  entities after attack: {[(e.type, e.id, e.name, e.health) for e in c.state.entities]}")

print("requesting quests...")
c.quests()
time.sleep(TICK)

# Check quest_complete callback  
quest_complete_received = [False]
score_received = [None]

original_callback = c._async._on_quest_complete

def track_quest_complete(final_score, steps_taken):
    quest_complete_received[0] = True
    score_received[0] = final_score
    print(f"  *** QUEST COMPLETE! score={final_score} steps={steps_taken}")

c._async._on_quest_complete = track_quest_complete

print("moving back to tavern...")
move_to("south", "forest_path")
move_to("south", "village_square")
move_to("south", "tavern")

time.sleep(2.0)
print(f"\nQuest complete received: {quest_complete_received[0]}")
print(f"Score: {score_received[0]}")
print(f"state.score: {c.state.score}")

c.disconnect()
