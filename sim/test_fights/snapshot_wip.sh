#!/bin/bash
# Save the agents' unmerged worktree commits as patches in the repo and push them, so nothing is lost if a session
# stops. Usage: sim/test_fights/snapshot_wip.sh [loop]   (with "loop": again every 10 minutes)
cd "$(dirname "$0")/../.." || exit 1
BR=claude/kind-bell-r5ehx4
while true; do
    changed=0
    for b in $(git for-each-ref --format='%(refname:short)' refs/heads/worktree-agent-*); do
        out=sim/test_fights/wip_patches/$b
        n=$(git rev-list --count "$BR..$b" 2>/dev/null)
        [ "${n:-0}" -gt 0 ] || continue
        rm -rf "$out" && mkdir -p "$out"
        git format-patch -q -o "$out" "$BR..$b" && changed=1
    done
    if [ $changed = 1 ]; then
        for i in 1 2 3 4 5; do     # (the index may be busy with another commit: try again)
            git add sim/test_fights/wip_patches 2>/dev/null &&
            git commit -q -m "WIP snapshot of agent branches" -- sim/test_fights/wip_patches 2>/dev/null && break
            sleep 5
        done
        for d in 2 4 8 16; do git push -q origin "$BR" 2>/dev/null && break; sleep $d; done
    fi
    [ "$1" = loop ] || break
    sleep 600
done
