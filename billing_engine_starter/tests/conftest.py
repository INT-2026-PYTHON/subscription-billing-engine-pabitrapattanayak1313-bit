"""Shared pytest fixtures + helpers."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pytest

from billing_engine.db.database import Database
from billing_engine.db.repository import (
    CustomerRepository, PlanRepository, PlanTierRepository, DiscountRepository,
    SubscriptionRepository, UsageRecordRepository,
    InvoiceRepository, InvoiceLineItemRepository, LedgerRepository,
    PaymentAttemptRepository,
)
from billing_engine.discounts import Discount
from billing_engine.money import Money
from billing_engine.pricing import FlatRate
from billing_engine.taxes import NoTax, TaxContext


@pytest.fixture
def db() -> Database:
    """A fresh, file-backed SQLite database with schema applied.

    File-backed (not :memory:) so the same DB can be opened across multiple
    short-lived connections in a single test (which BillingCycle does).
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    database.init_schema()
    yield database
    Path(path).unlink(missing_ok=True)


# ----------------------------------------------------------------
# Bundle of repositories (cuts boilerplate in integration-y tests)
# ----------------------------------------------------------------
@dataclass
class Repos:
    db: Database
    customers: CustomerRepository
    plans: PlanRepository
    tiers: PlanTierRepository
    discounts: DiscountRepository
    subscriptions: SubscriptionRepository
    usage: UsageRecordRepository
    invoices: InvoiceRepository
    line_items: InvoiceLineItemRepository
    ledger: LedgerRepository
    attempts: PaymentAttemptRepository


@pytest.fixture
def db() -> Database:
    """A fresh, file-backed SQLite database with schema applied.

    File-backed (not :memory:) so the same DB can be opened across multiple
    short-lived connections in a single test (which BillingCycle does).
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    database.init_schema()
    yield database
    
    # Cleanup: on Windows, we need to ensure SQLite releases its locks
    # before trying to delete the file.
    import sys
    import gc
    
    if sys.platform == "win32":
        # Force garbage collection to release any lingering references
        gc.collect()
        # Give the OS time to release file locks
        import time
        time.sleep(0.05)
    
    # Now try to delete the file
    try:
        Path(path).unlink()
    except PermissionError:
        # If still locked on Windows, this is expected under heavy load
        # The temp file will be cleaned up by the OS eventually
        pass