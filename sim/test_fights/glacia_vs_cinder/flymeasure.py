"""How much two flyers are up, and how often a hit knocks one down, by overall strength (Glacia vs Cinder)."""
import sys, json, collections
sys.path.insert(0, "/home/user/FightSim")
import engine, simulate
rules = json.load(open("/home/user/FightSim/rules.json"))
if len(sys.argv) > 2:  # VIG
    for k, v in json.loads(sys.argv[2]).items():
        rules["flight"]["vigour"][k].update(v)
if len(sys.argv) > 1:
    rules["flight"]["knock_from_air"].update(json.loads(sys.argv[1]))
rolls = collections.defaultdict(lambda: [0, 0, 0.0])   # band -> [rolls, falls, sum chance]
up = [0, 0]
band_up = collections.defaultdict(lambda: [0, 0, 0])
knocked, landed, prev, ends = set(), set(), {}, collections.Counter()
orig = engine.Engine._chance
def spy(self, p, what, yes, no, *a, **k):
    r = orig(self, p, what, yes, no, *a, **k)
    if "knocked out of the air" in what:
        n = what.split(" knocked")[0]
        h = self._health_pct(self.get(n))
        b = "90+" if h >= 90 else "70-90" if h >= 70 else "50-70" if h >= 50 else "30-50" if h >= 30 else "<30"
        rolls[b][0] += 1; rolls[b][1] += bool(r); rolls[b][2] += p
        if r: knocked.add(n)
    if "climbing back up" in what and not r:
        landed.add(what.split(" climbing")[0])
    return r
engine.Engine._chance = spy
orig_tick = engine.Engine.get_up_tick
def tick(self):
    for f in self.fighters.values():
        if not f.eliminated:
            up[0] += 1; up[1] += self.has(f, "airborne")
            h = self._health_pct(f); bb = "90+" if h >= 90 else "70-90" if h >= 70 else "50-70" if h >= 50 else "<50"
            band_up[bb][0] += 1; band_up[bb][1] += self.has(f, "airborne"); band_up[bb][2] += f.name in self.downed
            now = self.has(f, "airborne")
            if prev.get((id(self), f.name)) and not now:
                ends["knocked down" if f.name in knocked else "came down after a dive" if f.name in landed
                     else "timer ran out" if prev[(id(self), f.name)] == 1 else "other (chose to land, dragged...)"] += 1
            prev[(id(self), f.name)] = f.status.get("airborne", 0) if now else 0
    knocked.clear(); landed.clear()
    return orig_tick(self)
engine.Engine.get_up_tick = tick
lens = []
for s in range(40):
    r = simulate.one_fight(["Glacia", "Cinder"], json.loads(json.dumps(rules)), "13", 1000 + s)
    lens.append(r.get("beats", 0) if isinstance(r, dict) else 0)
print(f"airborne share of fighter-beats: {up[1] / max(1, up[0]):.0%}")
for b in ("90+", "70-90", "50-70", "30-50", "<30"):
    n, f, c = rolls[b]
    if n:
        print(f"  {b:6}: {n:4} air hits, fell {f / n:.0%} (mean chance {c / n:.0%})")
print("flights ended by:", dict(ends))
for bb in ("90+", "70-90", "50-70", "<50"):
    n, u, dn = band_up[bb]
    print(f"  at {bb}: {n} fighter-beats, in the air {u / max(1, n):.0%}, on the ground down {dn / max(1, n):.0%}")
