from dataclasses import dataclass, field


@dataclass
class SyncResult:
    accounts_synced: int = 0
    transactions_inserted: int = 0
    transactions_skipped: int = 0
    positions_synced: int = 0
    trades_inserted: int = 0
    trades_skipped: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
