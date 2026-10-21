"""Ripples vs Nerine, scene 15, a three-tap submission match (each tap from a new body part). The engine decides:
each beat's actions are /simulate's dice-driven stand-in choices (simulate._pick_action), played through the real
game, so every beat's screen output and the narrator's notes are written to bNN.txt. SEED picks the fight."""
import sys, os, random
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/user/FightSim/sim")
import harness as H
import simulate as S
from director import resolve_many  # noqa: F401  (loaded the same way the game does)

SETTINGS = ["/set finish.submission.enabled true", "/set finish.submission.taps.enabled true",
            "/set finish.submission.taps.needed 3", "/set finish.submission.taps.different_parts 100",
            "/set finish.knockout_only false"]


def choose(eng, rng, last):
    """One beat's actions, as simulate.one_fight picks them."""
    active = eng.active()
    movers = [f for f in active if not any(eng.has(f, st) for st in ("asleep", "frozen", "flinched"))] or active
    pool = [f for f in movers if f.name != last] if last and rng.random() < 0.65 else movers
    f = rng.choice(pool or movers)
    takers = [x for x in movers if not eng.has(x, "airborne") and not eng.sub_caught(x) and any(
        (getattr(eng, "sub_window", None) or {}).get(o.name) and (x.name not in eng.downed or eng.ground_lock_ok(x.name, o.name))
        for o in active if o is not x)]
    if takers and f not in takers and rng.random() < S.SUB_TAKE:
        f = rng.choice(takers)
    d = rng.choice([x for x in active if x is not f])
    act = S._pick_action(eng, rng, f, d)
    acts = [act]
    if act.get("action") == "strike" and not act.get("count") and not act.get("carry") and not act.get("launch") \
            and not (eng.find_move(f.name, act["move"]) or {}).get("charge") and rng.random() < S.CHAIN_CHANCE:
        acts += S._chain_links(eng, rng, f, d, act)
    for a in acts:
        a.pop("_sim", None)
    return f.name, acts


def run(seed, write=True, max_beats=200, quiet=False):
    s = H.session(seed, scene="15", fighters="Ripples,Nerine", settings=SETTINGS)
    eng, rng, last = s.eng, random.Random(seed * 7919 + 1), None
    for i in range(1, max_beats + 1):
        if s.over or eng.winner():
            break
        eng.roll_pin_windows()
        last, acts = choose(eng, rng, last)
        try:
            out, prompts = H.beat(s, acts, [], roll=False)
        except Exception as e:
            out, prompts = H.beat(s, [{"attacker": last, "defender": acts[0]["defender"], "action": "breather",
                                       "flavor": ""}], [], roll=False)
            out = f"(REFUSED: {e!r})\n" + out
        if write:
            with open(os.path.join(OUT, f"b{i:02d}.txt"), "w") as fh:
                fh.write("##### ACTIONS\n" + repr(acts) + "\n##### STDOUT\n" + out + "\n")
                for j, p in enumerate(prompts):
                    for m in p:
                        fh.write(f"\n##### PROMPT {j} {m.get('role')}\n{m.get('content')}\n")
        if not quiet:
            st = "; ".join(f"{x.name} {eng.strength(x):.0f}% taps {len(eng.taps_given(x))}"
                           f"{' DOWN' if x.name in eng.downed else ''}" for x in eng.active())
            print(f"=== {i}: {st} | {[(h.attacker, h.part, h.sub) for h in eng.holds.values()]}", flush=True)
    return s, eng


if __name__ == "__main__":
    s, eng = run(int(sys.argv[1]) if len(sys.argv) > 1 else 1, write="--dry" not in sys.argv,
                 quiet="--quiet" in sys.argv)
    print("WINNER", eng.winner(), "beats", eng.turn, {f.name: eng.taps_given(f) for f in eng.fighters.values()})
