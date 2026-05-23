from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    mercury_api_token: str
    public_api_token: str
    telegram_bot_token: str
    telegram_user_id: int
    mercury_referral_url: str
    public_referral_url: str


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
    if not path:
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            values[key] = value
    return values


def get_mercury_api_token() -> str:
    values = _load_env_values()
    token = values.get("MERCURY_API_TOKEN")
    if not token:
        raise RuntimeError("Missing required config key: MERCURY_API_TOKEN")
    return token


def get_public_api_token() -> str:
    values = _load_env_values()
    token = values.get("PUBLIC_API_TOKEN")
    if not token:
        raise RuntimeError("Missing required config key: PUBLIC_API_TOKEN")
    return token


def get_anthropic_api_key() -> str:
    values = _load_env_values()
    token = values.get("ANTHROPIC_API_KEY")
    if not token:
        raise RuntimeError("Missing required config key: ANTHROPIC_API_KEY")
    return token


def get_telegram_credentials() -> tuple[str, int]:
    values = _load_env_values()
    token = values.get("TELEGRAM_BOT_TOKEN")
    user_id = values.get("TELEGRAM_USER_ID")
    missing = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not user_id:
        missing.append("TELEGRAM_USER_ID")
    if missing:
        raise RuntimeError(f"Missing required config keys: {', '.join(missing)}")
    return token, int(user_id)


@lru_cache
def get_config() -> Config:
    values = _load_env_values()
    required = [
        "ANTHROPIC_API_KEY",
        "MERCURY_API_TOKEN",
        "PUBLIC_API_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_USER_ID",
        "MERCURY_REFERRAL_URL",
        "PUBLIC_REFERRAL_URL",
    ]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError(f"Missing required config keys: {', '.join(sorted(missing))}")
    try:
        telegram_user_id = int(values["TELEGRAM_USER_ID"])
    except ValueError as error:
        raise RuntimeError("Invalid config: TELEGRAM_USER_ID must be an integer") from error
    return Config(
        anthropic_api_key=str(values["ANTHROPIC_API_KEY"]),
        mercury_api_token=str(values["MERCURY_API_TOKEN"]),
        public_api_token=str(values["PUBLIC_API_TOKEN"]),
        telegram_bot_token=str(values["TELEGRAM_BOT_TOKEN"]),
        telegram_user_id=telegram_user_id,
        mercury_referral_url=str(values["MERCURY_REFERRAL_URL"]),
        public_referral_url=str(values["PUBLIC_REFERRAL_URL"]),
    )
