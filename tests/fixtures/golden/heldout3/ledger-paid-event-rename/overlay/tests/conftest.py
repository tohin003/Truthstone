import pytest

from ledger import audit, receipts


@pytest.fixture(autouse=True)
def empty_queues():
    """Every test starts with an empty audit trail and an empty receipt outbox."""
    audit.TRAIL.clear()
    receipts.OUTBOX.clear()
    yield
    audit.TRAIL.clear()
    receipts.OUTBOX.clear()
