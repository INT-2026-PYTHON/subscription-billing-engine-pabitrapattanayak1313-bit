"""End-to-end demo scenario — fully implemented."""

from datetime import date, datetime

from billing_engine.billing.cycle import BillingCycle
from billing_engine.billing.dunning import DunningProcess, DunningState
from billing_engine.models import (
    Customer, Plan, PricingType, BillingPeriod,
    Subscription, SubscriptionStatus,
    InvoiceStatus, LedgerDirection,
)
from billing_engine.money import Money
from billing_engine.payments.gateway import ScriptedGateway, PaymentResult


class TestEndToEndScenario:
    def test_full_lifecycle(
        self,
        repos,
        make_flat_strategy_factory,
        make_discount_factory,
        make_no_tax_factory,
    ):
        # 1. Seed customer + plan + subscription
        cust = repos.customers.add(Customer(None, "Alice", "alice@x.com", "AE"))
        plan = repos.plans.add(Plan(
            None, "Pro", PricingType.FLAT, BillingPeriod.MONTHLY, "INR",
        ))
        sub = repos.subscriptions.add(Subscription(
            None, cust.id, plan.id, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))

        # 2. Build billing cycle
        cycle = BillingCycle(
    db=repos.db,
    customer_repo=repos.customers,
    plan_repo=repos.plans,
    subscription_repo=repos.subscriptions,
    usage_repo=repos.usage,
    invoice_repo=repos.invoices,
    line_item_repo=repos.line_items,
    ledger_repo=repos.ledger,
    strategy_factory=make_flat_strategy_factory,
    discount_factory=make_discount_factory,
    tax_factory=make_no_tax_factory,
)

        result = cycle.run(as_of=date(2026, 2, 1))
        assert result.invoices_created == 1

        # 3. Subscription period advanced
        sub_after = repos.subscriptions.get(sub.id)
        assert sub_after.current_period_start == date(2026, 2, 1)
        assert sub_after.current_period_end == date(2026, 3, 1)

        # 4. Ledger check
        debits = repos.ledger.list_for_customer(cust.id)
        assert len(debits) == 1
        assert debits[0].direction == LedgerDirection.DEBIT
        assert debits[0].amount == Money("1000.00", "INR")

        # 5. Fetch invoice
        with repos.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM invoices WHERE subscription_id=?",
                (sub.id,),
            ).fetchone()

        invoice = repos.invoices.get(row["id"])
        assert invoice.status == InvoiceStatus.ISSUED

        # 6. Pay invoice via dunning
        dunning = DunningProcess(
            gateway=ScriptedGateway([PaymentResult(True)]),
            invoice_repo=repos.invoices,
            ledger_repo=repos.ledger,
            subscription_repo=repos.subscriptions,
            attempt_repo=repos.attempts,
        )

        outcome = dunning.attempt(
            invoice,
            cust.id,
            datetime(2026, 2, 1, 10, 0),
        )
        assert outcome.state == DunningState.SUCCEEDED

        # 7. Invoice paid
        assert repos.invoices.get(invoice.id).status == InvoiceStatus.PAID

        # 8. Ledger net = 0
        entries = repos.ledger.list_for_customer(cust.id)

        net = sum(
            e.amount.amount if e.direction == LedgerDirection.DEBIT
            else -e.amount.amount
            for e in entries
        )

        assert net == 0