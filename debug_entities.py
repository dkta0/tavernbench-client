"""Debug - see what entities are in the tavern."""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'sdk'))
from tavernbench.websocket import Client

c = Client('ws://localhost:4100', api_key='dev-key')
c.connect()
c.join('tavern')
time.sleep(0.8)

s = c.state
print(f"zone={s.zone_id} pos={s.position} steps={s.steps}")
print("Entities:")
for e in s.entities:
    print(f"  {e.type:8s} {e.id:30s} {e.name:25s} pos={e.position} dist={e.distance:.1f}")

# Try move north and check
print()
print("Moving north 5 times (may need to walk to exit)")
for i in range(6):
    r = c.move('north')
    time.sleep(0.8)
    print(f"  step {i+1}: zone={c.state.zone_id} pos={c.state.position} steps={c.state.steps}")

c.disconnect()
