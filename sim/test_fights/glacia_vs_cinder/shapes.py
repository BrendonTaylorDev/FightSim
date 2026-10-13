"""Replay script.json silently, then list the pin shapes Glacia/Cinder could use now."""
import sys, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/user/FightSim/sim")
import harness as H, director
s = H.session(202, scene="13", fighters="Glacia,Cinder", settings=["/scale 4"])
s.narrator.narrate = lambda *a, **k: "(skipped)"
for b in json.load(open(os.path.join(HERE, "script.json"))):
    H.beat(s, b, [])
a, d = s.eng.get(sys.argv[1]), s.eng.get(sys.argv[2])
for k, (look, contacts) in director.pin_shapes(s.eng, a, d).items():
    print(k, "|", look[:90], "|", contacts)
