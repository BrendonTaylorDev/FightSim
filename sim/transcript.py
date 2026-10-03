"""Build a full console transcript (everything the program prints: headers, stat blocks, rolls) for a scripted fight,
with the prose written by a stand-in narrator put where the model's prose goes.
Usage: python sim/transcript.py SEED narration.md out.txt
narration.md: '## opening' then '## beat 1', '## beat 2'... (beat N = the Nth played beat), each followed by its prose."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import long_fight
import play

DROP = re.compile(r"^\s*\[(checking the draft|something is missing|still wrong|the beat came out short|big moment: writing|"
                  r"writing \d+ paragraphs? again|the passage never showed|narrator is writing more|.* adding the moment|trimmed older story context)|"
                  r"^⏱ This beat took")


def prose_sections(path):
    text = open(path, encoding="utf-8").read()
    parts = re.split(r"^## (opening|beat \d+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def splice(out, prose):
    """The beat's console output with the stand-in's prose in place of the placeholder (and its rewrite notes gone)."""
    lines = [l for l in out.split("\n") if not DROP.search(l)]
    marks = [i for i, l in enumerate(lines) if "Placeholder prose" in l or l.startswith(("Ripples' struggles faded",))]
    if not marks:
        # the placeholder was cut by the checks: the prose goes where the program prints it, just above the stats
        cut = next((i for i, l in enumerate(lines) if l.strip() == "-" * 40), len(lines))
        while cut > 0 and not lines[cut - 1].strip():
            cut -= 1
        return "\n".join(lines[:cut] + ["", prose or "(no prose)", ""] + lines[cut:])
    a, b = marks[0], marks[-1]
    return "\n".join(lines[:a] + [prose or "(no prose)"] + lines[b + 1:])


def main(seed, narration, dest):
    s, log, caps, tags = long_fight.run(seed)
    prose = prose_sections(narration) if narration and os.path.exists(narration) else {}
    head = (f"STAND-IN FIGHT, build 113, seed {seed}. Sleek Ripples vs Nocturne, sea cave.\n"
            f"Settings: {', '.join(long_fight.SETTINGS[1:])}.\n"
            f"Director and narrator: Claude standing in for the local model. Every roll is the engine's; the prose "
            f"is written from the narrator's real notes for each beat.\n\n"
            f"[stand-in fight, seed {seed}, {play.VERSION.split(' (')[0]}]\n")
    fresh = long_fight.session(seed, settings=long_fight.SETTINGS)
    body = [head + fresh.display.status(fresh.eng), ""]
    body.append(f"{'=' * 30} beat 1 {'=' * 30}\n  [narrator is setting the scene]\n\n{prose.get('opening', '(opening)')}\n")
    for n, (out, tag) in enumerate(zip(log, tags), start=2):
        body.append(f"{'=' * 30} beat {n} {'=' * 30}\n  [director is choosing the next beat]\n"
                    + splice(out, prose.get(f"beat {n - 1}", "")))
    open(dest, "w", encoding="utf-8").write("\n".join(body) + "\n")
    print(f"wrote {dest}: {len(tags)} beats after the opening; winner {s.eng.winner()}")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "", sys.argv[3] if len(sys.argv) > 3 else "transcript.txt")
