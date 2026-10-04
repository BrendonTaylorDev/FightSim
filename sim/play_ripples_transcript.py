"""Full console transcript of the play-as test (the user's seat: Ripples; /play dice fair) with the stand-in
narrator's prose spliced in where the model's prose goes, and the narrator's notes for every beat (to write it from).
Usage: python sim/play_ripples_transcript.py SEED notes_dir                         (the notes for every beat)
       python sim/play_ripples_transcript.py SEED notes_dir narration.md out.txt  (the transcript)"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import play_ripples_fight as pf
import play
from transcript import prose_sections, splice
from lakeside3_transcript import notes


def build(seed, narration, dest):
    s, log, caps, tags = pf.run(seed)
    prose = prose_sections(narration) if narration and os.path.exists(narration) else {}
    head = (f"PLAY-AS TEST, seed {seed}: the user's seat is RIPPLES (/play Ripples, /play dice fair) against Nocturne, "
            f"in the lakeside clearing.\n"
            f"Settings: {', '.join(pf.SETTINGS[1:5])}. Lent for this fight: Nocturne Sunny Day and Counter; Ripples "
            f"Rain Dance, Protect and Mirror Coat.\n"
            f"Ripples: played by Claude, typing orders at the 'Ripples >' prompt. Nocturne: the director's stand-in "
            f"(the /simulate dice-driven chooser). Narrator: Claude standing in for the local model, writing from the "
            f"narrator's real notes for each beat. Every roll is the engine's.\n\n[{play.VERSION.split(' (')[0]}]\n")
    fresh = pf.session(seed, scene=pf.SCENE, settings=pf.SETTINGS)
    body = [head + fresh.display.status(fresh.eng), ""]
    body.append(f"{'=' * 30} the opening {'=' * 30}\n  [narrator is setting the scene]\n\n{prose.get('opening', '(opening)')}\n")
    for n, out in enumerate(log, start=1):
        body.append(f"{'=' * 30} beat {n} {'=' * 30}\n" + splice(out, prose.get(f"beat {n}", "")))
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
    print(f"wrote {dest} ({len(log)} beats) and {len(chunks)} parts; winner {s.eng.winner()}")


if __name__ == "__main__":
    seed = int(sys.argv[1])
    if len(sys.argv) <= 3:
        s, log, caps, tags = pf.run(seed)
        notes(caps, sys.argv[2])
        print(f"notes for {len(caps)} beats in {sys.argv[2]}; winner {s.eng.winner()}")
    else:
        build(seed, sys.argv[3], sys.argv[4])
