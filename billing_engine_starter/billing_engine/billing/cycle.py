"""
BillingCycle — finds due subscriptions, generates invoices, posts ledger DEBITs,
advances the subscription period. Must be IDEMPOTENT (safe to run twice).
"""

from __future__ import annotations

import sqlite3

from dataclasses import dataclass
from datetime import date

from typing import Callable

from billing_engine.billing.pipeline import build_invoice
from billing_engine.db import (
    Database,
    CustomerRepository,
    PlanRepository,
    SubscriptionRepository,
    UsageRecordRepository,
    InvoiceRepository,
    InvoiceLineItemRepository,
    LedgerRepository,
)
from billing_engine.models import (
    SubscriptionStatus,
    InvoiceStatus,
    LedgerEntry,
    LedgerDirection,
)


@dataclass
class BillingResult:
    invoices_created: int
    invoices_skipped_duplicate: int
    trials_activated: int


class BillingCycle:
    """Day-3 deliverable. Day-4 stretch: add `upgrade_subscription(...)`."""

    def __init__(
        self,
        db: Database,
        customer_repo: CustomerRepository,
        plan_repo: PlanRepository,
        subscription_repo: SubscriptionRepository,
        usage_repo: UsageRecordRepository,
        invoice_repo: InvoiceRepository,
        line_item_repo: InvoiceLineItemRepository,
        ledger_repo: LedgerRepository,
        strategy_factory: Callable,
        discount_factory: Callable,
        tax_factory: Callable,
    ) -> None:
        self.db = db
        self.customer_repo = customer_repo
        self.plan_repo = plan_repo
        self.subscription_repo = subscription_repo
        self.usage_repo = usage_repo
        self.invoice_repo = invoice_repo
        self.line_item_repo = line_item_repo
        self.ledger_repo = ledger_repo
        self.strategy_factory = strategy_factory
        self.discount_factory = discount_factory
        self.tax_factory = tax_factory

    # --------------------------------------------------------
    def run(self, as_of: date) -> BillingResult:
        """Bill all subscriptions whose current period ends on or before `as_of`."""

        invoices_created = 0
        invoices_skipped_duplicate = 0
        trials_activated = 0

        # Activate trials that have ended
        for sub in self.subscription_repo.list_all():
            if (
                sub.status == SubscriptionStatus.TRIAL
                and sub.trial_end is not None
                and sub.trial_end <= as_of
            ):
                self.subscription_repo.update_status(
                    sub.id,
                    SubscriptionStatus.ACTIVE,
                )
                trials_activated += 1

        due_subscriptions = self.subscription_repo.get_due_for_billing(as_of)

        for sub in due_subscriptions:
            try:
                customer = self.customer_repo.get(sub.customer_id)
                plan = self.plan_repo.get(sub.plan_id)

                strategy = self.strategy_factory(plan)
                discount = self.discount_factory(sub.discount_id)
                tax_calc, tax_context = self.tax_factory(customer)

                usage_quantity = 0

                invoice_count = self.invoice_repo.count_for_subscription(sub.id)

                invoice = build_invoice(
                    subscription=sub,
                    plan=plan,
                    strategy=strategy,
                    discount=discount,
                    tax_calc=tax_calc,
                    tax_context=tax_context,
                    usage_quantity=usage_quantity,
                    period_start=sub.current_period_start,
                    period_end=sub.current_period_end,
                    invoice_count_so_far=invoice_count,
                )

                invoice.status = InvoiceStatus.ISSUED

                saved_invoice = self.invoice_repo.add(invoice)

                for item in invoice.line_items:
                    self.line_item_repo.add(
                        item.__class__(
                            id=None,
                            invoice_id=saved_invoice.id,
                            description=item.description,
                            amount=item.amount,
                            kind=item.kind,
                        )
                    )

                self.ledger_repo.add(
                    LedgerEntry(
                        id=None,
                        invoice_id=saved_invoice.id,
                        customer_id=sub.customer_id,
                        amount=saved_invoice.total,
                        direction=LedgerDirection.DEBIT,
                        reason=f"Invoice {saved_invoice.id}",
                    )
                )

                # Monthly period advance
                old_end = sub.current_period_end

                if old_end.month == 12:
                    new_end = date(old_end.year + 1, 1, old_end.day)
                else:
                    new_end = date(old_end.year, old_end.month + 1, old_end.day)

                self.subscription_repo.update_period(
                    sub.id,
                    old_end,
                    new_end,
                )

                invoices_created += 1

            except sqlite3.IntegrityError:
                invoices_skipped_duplicate += 1

        return BillingResult(
            invoices_created=invoices_created,
            invoices_skipped_duplicate=invoices_skipped_duplicate,
            trials_activated=trials_activated,
        )

    # --------------------------------------------------------
    def upgrade_subscription(self, subscription_id: int, new_plan_id: int, switch_date: date) -> None:
        """Mid-cycle upgrade — Day 4 stretch."""
        # TODO Day 4
        raise NotImplementedError("Day 4: implement BillingCycle.upgrade_subscription")