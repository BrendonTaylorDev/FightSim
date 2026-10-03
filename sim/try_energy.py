import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import session, beat
s = session(5, settings=["/variant Ripples sleek", "/scale 5", "/resscale 0.75", "/healthloss 0.2", "/numb off"])
log = []
for i in range(3):
    try:
        out, _ = beat(s, [{"action": "strike", "attacker": "Ripples", "defender": "Nocturne", "move": "Aqua Jet",
                           "part": ["Chest", "Belly", "Left Shoulder"][i], "charge_into": "a stalagmite", "flavor": "Aqua Jet"}], log)
        print(f"use {i+1}: Ripples energy {s.eng.get('Ripples').energy:.0f}", "| winded (dodges worse)" if s.eng.get('Ripples').energy < 25 else "")
    except ValueError as e:
        print(f"use {i+1}: refused: {e}")
    beat(s, [{"action": "breather", "attacker": "Nocturne", "flavor": "circles"}], log)
    print(f"  after a beat of circling: {s.eng.get('Ripples').energy:.0f}")
