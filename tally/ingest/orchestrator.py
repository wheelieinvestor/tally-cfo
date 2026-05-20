import structlog

from tally.config import get_mercury_api_token
from tally.db import default_db_path
from tally.ingest.mercury import MercuryClient, SyncResult

logger = structlog.get_logger()


def sync_all(providers: list[str] | None = None) -> dict[str, SyncResult]:
    selected = providers or ["mercury"]
    results: dict[str, SyncResult] = {}
    for provider in selected:
        if provider != "mercury":
            logger.warning("Skipping provider for this slice", provider=provider)
            continue
        client = MercuryClient(get_mercury_api_token())
        results["mercury"] = client.sync(default_db_path())

    return results
