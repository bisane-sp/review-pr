"""Application configuration loaded from environment / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the Google Chat PR bot. The only place env vars are read."""

    google_chat_space_id: str
    google_chat_webhook_url: str
    pubsub_subscription: str
    github_account_1: str
    github_token_1: str
    github_account_2: str
    github_token_2: str
    gh_timeout_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def github_accounts(self) -> list[tuple[str, str]]:
        """The configured (account login, token) pairs, in priority order."""
        return [
            (self.github_account_1, self.github_token_1),
            (self.github_account_2, self.github_token_2),
        ]


settings = Settings()
