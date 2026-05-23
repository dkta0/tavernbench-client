"""Debug tick timing - figure out when state updates arrive."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'sdk'))
from tavernbench.websocket import Client

c = Client('ws://localhost:4100', api_key='dev-key')
c.connect()
c.join('tavern')
time.sleep(0.8)  # wait for first tick

print(f"t=0 zone={c.state.zone_id} entities={len(c.state.entities)} steps={c.state.steps}")

# Send move north
c.look()  # clear buffer
t0 = time.time()
c.move('north')
print(f"move sent at t={time.time()-t0:.3f}")

# Poll state every 100ms
for i in range(25):
    time.sleep(0.1)
    elapsed = time.time() - t0
    z = c.state.zone_id
    s = c.state.steps
    print(f"  t={elapsed:.2f}s zone={z} steps={s}")
    if z != 'tavern':
        print(f"  -> Zone changed after {elapsed:.2f}s!")
        break

c.disconnect()
