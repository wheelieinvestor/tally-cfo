from tally.config import get_config
from tally.ingest.mercury import MercuryClient
from tally.ingest.public import PublicClient


def sync_all() -> None:
    config = get_config()
    MercuryClient(config.mercury_api_token).sync()
    PublicClient(config.public_api_token).sync()
