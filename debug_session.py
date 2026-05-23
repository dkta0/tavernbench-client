import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'sdk'))
from tavernbench.websocket import Client

c = Client('ws://localhost:4100', api_key='dev-key')
c.connect()
r = c.join('tavern')
print('join reply:', json.dumps(r, default=str)[:300])
time.sleep(1.0)  # let first tick arrive
print('state zone_id:', c.state.zone_id)
print('state entities:', len(c.state.entities))
print('state score:', c.state.score)
print('state steps:', c.state.steps)
r = c.look()
time.sleep(0.5)
print('after look zone_id:', c.state.zone_id, 'entities:', len(c.state.entities))
print('look reply:', json.dumps(r, default=str)[:300])
c.disconnect()
