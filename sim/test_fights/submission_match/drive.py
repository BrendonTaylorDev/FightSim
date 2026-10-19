"""Ripples vs Nerine, scene 15, a submission match. Plan in plan.py (entries may be functions of the engine)."""
import sys, os, json, re
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/user/FightSim/sim")
import harness as H
R, N = "Ripples", "Nerine"
def A(att, action, **k):
    k["attacker"] = att; k["action"] = action
    k.setdefault("defender", R if att == N else N); k.setdefault("flavor", "")
    return k
exec(open(os.path.join(OUT, "plan.py")).read())
SETTINGS = ["/set finish.submission.enabled true"]
def run(narrate=None, quiet=False):
    s = H.session(int(os.environ.get("SEED", "5")), scene="15", fighters="Ripples,Nerine", settings=SETTINGS)
    if narrate:
        s.narrator.narrate = narrate
    eng = s.eng
    for i, acts in enumerate(PLAN, 1):
        if s.over or eng.winner():
            print("FIGHT OVER before beat", i); break
        eng.roll_pin_windows(); eng.roll_sub_windows()
        if callable(acts):
            acts = acts(eng)
        RUN["beat"] = i
        try:
            out, prompts = H.beat(s, acts, [], roll=False)
        except Exception as e:
            print(f"=== BEAT {i} REFUSED: {e!r} -> breather")
            acts = [A(acts[0]["attacker"], "breather", flavor="she backs off a step and drags in air")]
            out, prompts = H.beat(s, acts, [], roll=False)
        if not narrate:
            with open(os.path.join(OUT, f"b{i:02d}.txt"), "w") as f:
                f.write("##### STDOUT\n" + out + "\n")
                for j, p in enumerate(prompts):
                    for m in p:
                        f.write(f"\n##### PROMPT {j} {m.get('role')}\n{m.get('content')}\n")
        if not quiet:
            st = "; ".join(f"{x.name} {eng.strength(x):.0f}% en{x.energy:.0f}{' DOWN' if x.name in eng.downed else ''}"
                           f"{' PINNED' if eng.pinned_by(x.name) else ''}" for x in eng.active())
            holds = "; ".join(f"{h.attacker}>{h.defender} {h.part} {h.sub or h.locked or ('coil' if h.coil else 'hold')} t{h.turns_active}" for h in eng.holds.values())
            print(f"=== BEAT {i}: {st} | subwin {eng.__dict__.get('sub_window')} | pinwin {getattr(eng,'pin_window',None)} | {holds}")
    print("over:", s.over, eng.winner())
    return s
RUN = {"beat": 0}
if __name__ == "__main__":
    run()
