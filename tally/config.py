from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationError


class Config(BaseModel):
    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    mercury_api_token: str = Field(alias="MERCURY_API_TOKEN")
    public_api_token: str = Field(alias="PUBLIC_API_TOKEN")
    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_user_id: int = Field(alias="TELEGRAM_USER_ID")
    mercury_referral_url: str = Field(alias="MERCURY_REFERRAL_URL")
    public_referral_url: str = Field(alias="PUBLIC_REFERRAL_URL")


def home_dir() -> Path:
    return Path.home() / ".tally"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def env_path() -> Path | None:
    home_env = home_dir() / ".env"
    repo_env = repo_root() / ".env"
    if home_env.exists():
        return home_env
    if repo_env.exists():
        return repo_env
    return None


def _load_env_values() -> dict[str, str]:
    path = env_path()
    values = dotenv_values(path) if path else {}
    return {key: value for key, value in values.items() if value}


@lru_cache
def get_config() -> Config:
    values = _load_env_values()
    try:
        return Config.model_validate(values)
    except ValidationError as error:
        missing = [
            ".".join(str(part) for part in item["loc"])
            for item in error.errors()
            if item["type"] == "missing"
        ]
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise RuntimeError(f"Missing required config keys: {missing_text}") from error
        raise RuntimeError(f"Invalid config: {error}") from error
