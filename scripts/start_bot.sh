#!/bin/zsh
# Starts the review-pr-bot in a detached tmux session named "prbot".
# Re-running KILLS any existing bot — the tmux session plus any stale/duplicate review-pr-bot
# processes — and starts a single fresh instance, so there is never more than one subscriber on the
# Pub/Sub subscription.
# Attach with:  tmux attach -t prbot   (detach again with Ctrl-b then d)
# Stop with:    tmux kill-session -t prbot
SESSION=prbot
PROJECT_DIR=/Users/bisane.s/office_work/projects/review-pr

# Tear down any existing session first (this also stops the bot it was running).
if tmux kill-session -t "$SESSION" 2>/dev/null; then
  echo "Killed existing '$SESSION' tmux session."
fi

# Kill any stray review-pr-bot processes launched outside tmux. The [r] bracket keeps pkill from
# matching its own command line.
if pkill -f "[r]eview-pr-bot"; then
  echo "Killed stale/duplicate review-pr-bot process(es)."
  sleep 1  # let the OS reap them so the lock is released before the fresh start
fi

# `make run` renews (or creates) the Workspace Events subscription, then starts the bot,
# so the session always launches with a live subscription.
tmux new-session -d -s "$SESSION" -c "$PROJECT_DIR" 'make run'
echo "Started '$SESSION'. Attach with: tmux attach -t $SESSION"
