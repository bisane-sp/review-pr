.PHONY: run renew bot

# Renew the Chat subscription, then start the bot (foreground).
run: renew bot

# Renew (or create) the Workspace Events subscription for the space in .env.
renew:
	poetry run python scripts/manage_subscription.py ensure

# Start the Pub/Sub subscriber (the app entrypoint).
bot:
	poetry run review-pr-bot
