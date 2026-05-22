import structlog

from tally.config import get_mercury_api_token, get_public_api_token
from tally.db import default_db_path
from tally.ingest.mercury import MercuryClient
from tally.ingest.public import PublicClient
from tally.ingest.types import SyncResult

logger = structlog.get_logger()


def sync_all(providers: list[str] | None = None) -> dict[str, SyncResult]:
    selected = providers or ["mercury", "public"]
    results: dict[str, SyncResult] = {}
    for provider in selected:
        try:
            if provider == "mercury":
                client = MercuryClient(get_mercury_api_token())
            elif provider == "public":
                client = PublicClient(get_public_api_token())
            else:
                logger.warning("Skipping unknown provider", provider=provider)
                continue
            results[provider] = client.sync(default_db_path())
        except Exception as error:
            logger.error("Provider sync failed", provider=provider, error=str(error))
            result = SyncResult()
            result.errors.append(str(error))
            results[provider] = result

    return results
