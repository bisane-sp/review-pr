#!/bin/zsh
# Starts the review-pr-bot in a detached tmux session named "prbot".
# Safe to re-run: if the session already exists, it is left untouched.
# Attach with:  tmux attach -t prbot   (detach again with Ctrl-b then d)
# Stop with:    tmux kill-session -t prbot
SESSION=prbot
PROJECT_DIR=/Users/bisane.s/office_work/projects/review-pr

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' is already running. Attach with: tmux attach -t $SESSION"
  exit 0
fi

# `make run` renews (or creates) the Workspace Events subscription, then starts the bot,
# so the session always launches with a live subscription.
tmux new-session -d -s "$SESSION" -c "$PROJECT_DIR" 'make run'
echo "Started '$SESSION'. Attach with: tmux attach -t $SESSION"
