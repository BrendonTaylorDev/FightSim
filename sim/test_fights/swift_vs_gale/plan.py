# Swift: quick, cocky, fights in passes. Gale: patient, waits, takes hold with her talons and works the throat.
T = "her talons"
PLAN = [
 [A(S, "strike", move="Quick Attack", part="Chest", reposition="take off",
    flavor="Swift does not wait for the tick to finish: she comes off the bell frame in a blue streak, straight across the room into the older bird's breast")],
 [A(G, "strike", move="Aerial Ace", part="Left Wing", reposition="take off",
    flavor="Gale lets the blow rock her, drops off the beam, turns once under the pendulum and cuts back across the young one's left wing")],
 [A(S, "strike", move="Wing Attack", part="Head",
    flavor="Swift wheels tight round the swinging weight and clubs her wing across Gale's head as she passes")],
 [A(G, "strike", move="Air Slash", hits=[{"part": "Chest", "severity": "solid"}, {"part": "Forked Tail", "severity": "light"}],
    flavor="Gale fans her wings once, hard, and a blade of air goes humming after the young bird")],
 [A(S, "strike", move="Steel Wing", part="Upper Back",
    flavor="Swift comes over the top of her with her wings gone hard and grey and rakes one down across Gale's back")],
 [A(G, "strike", move="Pluck", part="Head Plumes",
    flavor="Gale turns her head as the young one goes by and snatches at her head plumes with her beak, wrenching")],
 [A(S, "strike", move="Aerial Ace", part="Neck",
    flavor="Swift flicks round the pendulum rod and slices low across the side of Gale's neck")],
 # Gale takes hold in the air
 [[A(G, "grapple", part="Right Wing", hits=[{"part": "Right Wing", "with": "her talons, clamped on it", "severity": "firm"}],
     flavor="Gale rises under her as she turns and sinks both feet into the young bird's right wing")],
  [A(G, "hold_start", part="Right Wing", hits=[{"part": "Right Wing", "with": "her talons, clamped on it", "severity": "firm"}],
     flavor="Gale rises under her as she turns and sinks both feet into the young bird's right wing")]],
 [A(G, "slam", landing=[{"surface": "the oak planking", "parts": ["Upper Back", "Right Wing"], "severity": "heavy"}],
    flavor="with the wing in her feet she folds and drops, and drives the young bird down onto the planking under her")],
 [[A(S, "struggle", defender="", flavor="Swift thrashes on her back, beating her free wing against the boards and snapping at Gale's feet")],
  [A(S, "strike", move="Peck", part="Left Talon", flavor="from her back Swift jabs her beak at the foot that holds her")]],
 [A(S, "strike", move="Quick Attack", part="Chest", reposition="take off",
    flavor="Swift wrenches free, rolls and is off the boards in a blur, straight up into Gale's breast")],
 [A(G, "strike", move="Steel Wing", part="Left Wing", reposition="take off",
    flavor="Gale goes up after her, turns inside her, and brings a steel-hard wing down across the young bird's left wing")],
 [A(S, "strike", move="Brave Bird", part="Chest",
    flavor="Swift climbs to the beams, folds and throws her whole body down at Gale in a blaze of blue light")],
 [[A(G, "breather", reposition="land", flavor="Gale drops to the gear housing and perches there, beak open, clicking it once, watching")],
  [A(G, "breather", flavor="Gale hangs back by the gear housing, beak open, clicking it once, watching")]],
 [A(S, "strike", move="Facade", part="Head",
    flavor="Swift, hurt and angry and showing it, dives straight at Gale's head")],
 [[A(G, "strike", move="Endeavor", part="Chest", reposition="take off", launch="knocked down",
     landing=[{"surface": "the oak planking", "parts": ["Upper Back", "Left Wing"], "severity": "heavy"}],
     flavor="Gale comes up off the housing into her, all of it at once, and smashes her down out of the air onto the planks")]],
]
def endgame(eng):
    """Swift fights the pin; Gale gets her down and pins her with a foot round the throat."""
    sw, ga = eng.get(S), eng.get(G)
    if eng.pinned_by(S):
        return [[A(S, "struggle", defender="", flavor="")]]
    if any(h.attacker == G and h.defender == S for h in eng.holds.values()):
        if S not in eng.downed:
            return [[A(G, "slam", landing=[{"surface": "the oak planking", "parts": ["Upper Back", "Head"], "severity": "heavy"}],
                       flavor="she drives her down onto the boards with the grip")]]
    if S in eng.downed:
        return [[A(G, "pin", hits=[{"part": "Throat", "severity": "firm", "with": "her talons, closed round the throat"},
                                   {"part": "Chest", "severity": "firm", "with": "her other foot and her full weight, on her breast"}],
                   flavor="Gale drops onto her before she can rise, one foot closing round her throat, the other planted on her breast")],
                [A(G, "strike", move="Pluck", part="Head", flavor="")]]
    if eng.has(sw, "airborne"):
        if not eng.has(ga, "airborne"):
            return [[A(G, "strike", move="Wing Attack", part="Chest", reposition="take off", flavor="")],
                    [A(G, "breather", reposition="take off", flavor="")]]
        return [[A(G, "grapple", part="Neck", hits=[{"part": "Neck", "with": "her talons, clamped on it", "severity": "firm"}],
                   flavor="Gale drops on her from above and locks both feet on her")],
                [A(G, "strike", move="Air Slash", hits=[{"part": "Chest", "severity": "solid"}], flavor="")]]
    if G in eng.downed and sw.energy < 25:
        return [[A(S, "breather", flavor="")]]
    return [[A(S, "strike", move="Quick Attack", part="Head", reposition="take off", flavor="")],
            [A(S, "strike", move="Wing Attack", part="Head", flavor="")],
            [A(S, "strike", move="Steel Wing", part="Neck", flavor="")],
            [A(S, "breather", flavor="")]]
PLAN += [endgame] * 40
