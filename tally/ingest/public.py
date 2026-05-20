class PublicClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def sync(self) -> None:
        raise NotImplementedError
