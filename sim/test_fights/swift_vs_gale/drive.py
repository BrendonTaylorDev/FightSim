"""Swift vs Gale, two Swellows in the clock tower (scene 10). Pins on, so a pin can end it (by the choke or the pain).
Plan in plan.py: a list of beats, each a list of options (the first the engine accepts is played)."""
import sys, os, json, re
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/user/FightSim/sim")
import harness as H
S, G = "Swift", "Gale"
def A(att, action, **k):
    k["attacker"] = att; k["action"] = action
    k.setdefault("defender", G if att == S else S); k.setdefault("flavor", "")
    return k
exec(open(os.path.join(OUT, "plan.py")).read())
SETTINGS = ["/set finish.knockout_only false", "/set finish.no_pins false"] + [x for x in os.environ.get("EXTRA", "").split(";") if x]
def state(eng):
    st = "; ".join(f"{x.name} {eng.strength(x):.0f}% en{x.energy:.0f}{' DOWN' if x.name in eng.downed else ''}"
                   f"{' AIR' if eng.has(x, 'airborne') else ''}"
                   f"{' PINNED' if eng.pinned_by(x.name) else ''}" for x in eng.active())
    holds = "; ".join(f"{h.attacker}>{h.defender} {h.part} [{h.with_part}] t{h.turns_active}" for h in eng.holds.values())
    return f"{st} | {holds}"
def run():
    s = H.session(int(os.environ.get("SEED", "3")), scene="10", fighters="Swift,Gale", settings=SETTINGS)
    eng = s.eng
    i = 0
    for step in PLAN:
        if s.over:
            print("FIGHT OVER"); break
        eng.roll_pin_windows()
        opts = step(eng) if callable(step) else step
        if opts and isinstance(opts[0], dict):
            opts = [opts]
        done = False
        for acts in opts:
            try:
                out, prompts = H.beat(s, acts, [], roll=False)
                done = True; break
            except Exception as e:
                print(f"   refused {acts[0]['action']} {acts[0].get('move','')}: {e!r}"[:300])
        if not done:
            continue
        i += 1
        with open(os.path.join(OUT, f"b{i:02d}.txt"), "w") as f:
            f.write("##### STDOUT\n" + out + "\n")
            for j, p in enumerate(prompts):
                for m in p:
                    f.write(f"\n##### PROMPT {j} {m.get('role')}\n{m.get('content')}\n")
        print(f"=== BEAT {i} [{acts[0]['attacker']} {acts[0]['action']} {acts[0].get('move','')}]: {state(eng)}")
    print("over:", s.over, eng.winner(), "beats", i, "|", getattr(eng, "out_reason", {}))
    return s
if __name__ == "__main__":
    run()
