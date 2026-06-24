#!/bin/zsh
# Renews the Workspace Events subscription for the Chat space so message events keep flowing.
# Intended to be invoked by a scheduler (e.g. launchd) every few hours; logs to temp/renew.log.
cd /Users/bisane.s/office_work/projects/review-pr || exit 1
/Users/bisane.s/.local/bin/poetry run python scripts/manage_subscription.py ensure >> temp/renew.log 2>&1
