"""Drive Ripples vs Nerine, scene 15, knockouts only, no pins. Plan in plan.py; dumps per beat."""
import sys, os, json, re, traceback
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/user/FightSim/sim")
import harness as H
G, W = "Glacia", "Swift"
def A(att, action, **k):
    k["attacker"] = att; k["action"] = action
    k.setdefault("defender", W if att == G else G); k.setdefault("flavor", "")
    return k
exec(open(os.path.join(OUT, "plan.py")).read())
s = H.session(int(os.environ.get("SEED", "7")), scene="13", fighters="Glacia,Swift",
              settings=["/set finish.knockout_only true", "/set finish.no_pins true"])
eng = s.eng
only = int(sys.argv[1]) if len(sys.argv) > 1 else 0
for i, acts in enumerate(PLAN, 1):
    if s.over:
        print("FIGHT OVER before beat", i); break
    try:
        out, prompts = H.beat(s, acts, [])
    except Exception as e:
        print(f"=== BEAT {i} REFUSED/ERR: {e!r} -> breather")
        acts = [A(acts[0]["attacker"], "breather", flavor="she has nothing left for that: she hangs back and drags in air")]
        out, prompts = H.beat(s, acts, [])
    with open(os.path.join(OUT, f"b{i:02d}.txt"), "w") as f:
        f.write("##### STDOUT\n" + out + "\n")
        for j, p in enumerate(prompts):
            for m in p:
                f.write(f"\n##### PROMPT {j} {m.get('role')}\n{m.get('content')}\n")
    if not only or i >= only:
        st = "; ".join(f"{x.name} {eng.strength(x):.0f}% en{x.energy:.0f}{' DOWN' if x.name in eng.downed else ''}" for x in eng.active())
        print(f"=== BEAT {i}: {st} | prompts {len(prompts)}")
print("over:", s.over, getattr(s, "winner", None))
