.PHONY: run renew bot

# Start the bot (foreground). It renews the Chat subscription on start and every 3h itself.
run: bot

# Renew (or create) the Workspace Events subscription for the space in .env.
renew:
	poetry run python scripts/manage_subscription.py ensure

# Start the Pub/Sub subscriber (the app entrypoint).
bot:
	poetry run review-pr-bot
