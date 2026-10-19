# Work in progress (build 220): narration ideas from Claude's own test-fight narration

Done, not yet committed as a numbered build:
- narration.hold_tries (narrator.py HOLD_TRIES, _hold_try, _hold_try_line, _under_blow_line): what she tries each
  beat in a hold, by hold kind, thought-out -> wild -> spent, never the same try twice; the hold stays under a blow.
- director.game_plan (engine.game_plan, director.game_plan_hint) + narration.plan_notes (narrator._plan_lines,
  play.sync_narrator sets narrator.game_plans): each fighter's plan, a zone of the other to take apart.

Still to do: regress (ALL PASSED), bump VERSION in play.py to build 220, README "## Build 220" section, one commit.
Test: scratchpad nr216, SEED=11 SWITCH=27 python3 drive.py; grep the b*.txt prompts for "TRIES THIS BEAT".
