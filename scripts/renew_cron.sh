#!/bin/zsh
# Renews the Workspace Events subscription for the Chat space so message events keep flowing.
# Intended to be invoked by a scheduler (e.g. launchd) every few hours; logs to temp/renew.log.
cd /Users/bisane.s/office_work/projects/review-pr || exit 1
# launchd runs with a minimal PATH; add poetry's dir so the `make renew` recipe can find it.
export PATH="/Users/bisane.s/.local/bin:$PATH"
make renew >> temp/renew.log 2>&1
