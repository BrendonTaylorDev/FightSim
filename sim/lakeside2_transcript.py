"""Full console transcript of lakeside test fight 2 (the throat-pin finish) with a stand-in narrator's prose spliced in where the model's
prose goes, plus the narrator's notes for every beat (to write that prose from).
Usage: python sim/lakeside2_transcript.py SEED notes_dir            (writes the notes: what each beat's narrator saw)
       python sim/lakeside2_transcript.py SEED notes_dir narration.md out.txt"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lakeside2_fight as lf
import play
from transcript import prose_sections, splice


def notes(caps, folder):
    """For each beat: the narrator's first prompt (the beat's facts) and each part's focus and building blocks."""
    os.makedirs(folder, exist_ok=True)
    for n, (tag, cap) in enumerate(caps, 1):
        users = [m["content"] for msgs in cap for m in msgs if m.get("role") == "user"]
        if not users:
            continue
        first = users[0]
        i = first.find("CURRENT CONDITION")
        facts = first[i:] if i >= 0 else first
        parts = []
        for u in users:
            m = re.search(r"Write PART (\d+) of (\d+).*?(?=\n\n|$)", u, re.S)
            if m and not any(p.startswith(f"PART {m.group(1)} ") for p in parts):
                b = u.find("BUILDING BLOCKS")
                parts.append(f"PART {m.group(1)} of {m.group(2)}: " + m.group(0)[:900]
                             + ("\n" + u[b:b + 1500] if b >= 0 else ""))
        with open(os.path.join(folder, f"beat{n + 1:02d}_{tag.replace(' ', '_')}.txt"), "w", encoding="utf-8") as fh:
            fh.write(facts + "\n\n" + "\n\n".join(parts))


def build(seed, narration, dest):
    s, log, caps, tags = lf.run(seed)
    prose = prose_sections(narration) if narration and os.path.exists(narration) else {}
    head = (f"STAND-IN FIGHT 2, seed {seed}: Nocturne vs the sleek Ripples in the lakeside clearing (warm, sunny with "
            f"clouds, a gentle breeze off the lake).\n"
            f"Settings: {', '.join(lf.SETTINGS[1:5])}. Lent for this fight: Nocturne Sunny Day and Counter; Ripples "
            f"Rain Dance, Protect and Mirror Coat.\n"
            f"Director and narrator: Claude standing in for the local models. Every roll is the engine's; the prose is "
            f"written from the narrator's real notes for each beat.\n\n[{play.VERSION.split(' (')[0]}]\n")
    fresh = lf.session(seed, scene=lf.SCENE, settings=lf.SETTINGS)
    body = [head + fresh.display.status(fresh.eng), ""]
    body.append(f"{'=' * 30} beat 1 {'=' * 30}\n  [narrator is setting the scene]\n\n{prose.get('opening', '(opening)')}\n")
    for n, (out, tag) in enumerate(zip(log, tags), start=2):
        body.append(f"{'=' * 30} beat {n} {'=' * 30}\n  [director is choosing the next beat]\n"
                    + splice(out, prose.get(f"beat {n}", "")))
    text = "\n".join(body) + "\n"
    open(dest, "w", encoding="utf-8").write(text)
    head, *rest = re.split(r"(?=^=+ beat \d+ =+$)", text, flags=re.M)
    per = 10
    chunks = [rest[i:i + per] for i in range(0, len(rest), per)]
    stem = dest[:-4] if dest.endswith(".txt") else dest
    for k, chunk in enumerate(chunks, 1):
        first = re.match(r"=+ beat (\d+)", chunk[0]).group(1)
        last = re.match(r"=+ beat (\d+)", chunk[-1]).group(1)
        top = head if k == 1 else f"(Part {k} of {len(chunks)}: beats {first}-{last}.)\n\n"
        open(f"{stem}_part{k}.txt", "w", encoding="utf-8").write(top + "".join(chunk))
    print(f"wrote {dest} ({len(tags) + 1} beats) and {len(chunks)} parts; winner {s.eng.winner()}")
    return s, log, caps, tags


if __name__ == "__main__":
    seed, folder = int(sys.argv[1]), sys.argv[2]
    if len(sys.argv) > 4:
        build(seed, sys.argv[3], sys.argv[4])
    else:
        s, log, caps, tags = build(seed, "", os.path.join(folder, "raw.txt"))
        notes(caps, folder)
