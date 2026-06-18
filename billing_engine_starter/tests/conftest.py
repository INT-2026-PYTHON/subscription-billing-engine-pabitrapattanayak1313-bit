"""Shared pytest fixtures + helpers (FINAL FIXED VERSION)."""

from __future__ import annotations

import os
import tempfile
import pytest
import sys
import gc
import time
from dataclasses import dataclass
from pathlib import Path

from billing_engine.db.database import Database
from billing_engine.db.repository import (
    CustomerRepository,
    PlanRepository,
    PlanTierRepository,
    DiscountRepository,
    SubscriptionRepository,
    UsageRecordRepository,
    InvoiceRepository,
    InvoiceLineItemRepository,
    LedgerRepository,
    PaymentAttemptRepository,
)

from billing_engine.money import Money
from billing_engine.pricing import FlatRate
from billing_engine.taxes import NoTax
from billing_engine.discounts import Discount


# ============================================================
# DB FIXTURE
# ============================================================

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    database = Database(path)
    database.init_schema()

    yield database

    if sys.platform == "win32":
        gc.collect()
        time.sleep(0.05)

    try:
        Path(path).unlink(missing_ok=True)
    except PermissionError:
        pass


# ============================================================
# REPOSITORIES
# ============================================================

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
def repos(db):
    return Repos(
        db=db,
        customers=CustomerRepository(db),
        plans=PlanRepository(db),
        tiers=PlanTierRepository(db),
        discounts=DiscountRepository(db),
        subscriptions=SubscriptionRepository(db),
        usage=UsageRecordRepository(db),
        invoices=InvoiceRepository(db),
        line_items=InvoiceLineItemRepository(db),
        ledger=LedgerRepository(db),
        attempts=PaymentAttemptRepository(db),
    )


# ============================================================
# STRATEGY FACTORY (FIXED)
# ============================================================

@pytest.fixture
def make_flat_strategy_factory():
    def _factory(plan):
        return FlatRate(Money("1000", "INR"))
    return _factory


# ============================================================
# DISCOUNT FACTORY (FIXED)
# ============================================================

@pytest.fixture
def make_discount_factory():
    def _factory(*args, **kwargs):
        # IMPORTANT: must accept ANY args (cycle passes code/sub.discount_id)
        return None
    return _factory


# ============================================================
# TAX FACTORY (CRITICAL FIX)
# must return (tax_calculator, tax_context)
# ============================================================

@pytest.fixture
def make_no_tax_factory():
    def _factory(*args, **kwargs):
        return NoTax(), None   # THIS fixes your unpack error
    return _factory