"""
Tests for the funds-ledger feature:
- import_ledger: row classification (deposit/withdrawal/charge/trade/other),
  signed amount, dedup, and derived headline figures
- build_summary: ledger-derived metrics (net_deposited, free_cash, personal XIRR)

No network. Uses an in-memory SQLite session for the importer; build_summary
tests use lightweight mock objects (mirroring test_portfolio.py).
"""
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.account import Account
from app.models.ledger import LedgerEntry
from app.services.import_ledger import import_ledger
from app.services.portfolio import build_summary


# A trimmed but representative slice of a real Zerodha funds/ledger export:
# opening/closing markers, two deposits, a withdrawal, a charge, two equity
# settlements (one debit = buy, one credit = sell).
SAMPLE_CSV = b"""particulars,posting_date,cost_center,voucher_type,debit,credit,net_balance
Opening Balance,,,,,,0.000000
Funds added using UPI RO7716 with reference number 111,2024-01-01,NSE-EQ - Z,Bank Receipts,0.000000,10000.000000,10000.000000
Net settlement for Equity with settlement number: 2024001,2024-01-02,NSE-EQ - Z,Book Voucher,6000.000000,0.000000,4000.000000
DP Charges for Sale of ITC on 03/01/2024,2024-01-03,NSE-EQ - Z,Journal Entry,15.340000,0.000000,3984.660000
Net settlement for Equity with settlement number: 2024002,2024-01-10,NSE-EQ - Z,Book Voucher,0.000000,2000.000000,5984.660000
Funds added using UPI RO7716 with reference number 222,2024-02-01,NSE-EQ - Z,Bank Receipts,0.000000,5000.000000,10984.660000
Payout of 3000.0/- to HDFC BANK LTD as per withdrawal request,2024-03-01,NSE-EQ - Z,Bank Payments,3000.000000,0.000000,7984.660000
Closing Balance,,,,,,7984.660000
"""


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    # Register models on the metadata before create_all.
    import app.models.account   # noqa: F401
    import app.models.ledger    # noqa: F401
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(Account(id=1, label="Test", broker="manual", is_active=True))
    s.commit()
    yield s
    s.close()
    engine.dispose()


# -----------------------------------------------------------------------
# import_ledger
# -----------------------------------------------------------------------

class TestImportLedger:
    def test_classification_and_counts(self, session):
        result = import_ledger(session, SAMPLE_CSV, account_id=1)
        # 6 real rows imported; opening + closing markers skipped.
        assert result["imported"] == 6
        assert result["skipped"] == 2
        assert result["errors"] == []

        rows = session.query(LedgerEntry).all()
        by_type: dict[str, int] = {}
        for r in rows:
            by_type[r.entry_type] = by_type.get(r.entry_type, 0) + 1
        assert by_type == {"deposit": 2, "withdrawal": 1, "charge": 1, "trade": 2}

    def test_signed_amounts(self, session):
        import_ledger(session, SAMPLE_CSV, account_id=1)
        deposit = (
            session.query(LedgerEntry)
            .filter(LedgerEntry.entry_type == "deposit")
            .order_by(LedgerEntry.entry_date.asc())
            .first()
        )
        charge = session.query(LedgerEntry).filter(LedgerEntry.entry_type == "charge").first()
        assert deposit.amount == 10000.0   # credit − debit, positive
        assert charge.amount == -15.34     # debit, negative

    def test_headline_figures(self, session):
        result = import_ledger(session, SAMPLE_CSV, account_id=1)
        assert result["total_deposited"] == 15000.0
        assert result["total_withdrawn"] == 3000.0
        assert result["net_deposited"] == 12000.0  # 15000 − 3000
        assert result["total_charges"] == 15.34
        assert result["free_cash"] == 7984.66      # last balance

    def test_dedup_on_reimport(self, session):
        first = import_ledger(session, SAMPLE_CSV, account_id=1)
        assert first["imported"] == 6
        second = import_ledger(session, SAMPLE_CSV, account_id=1)
        assert second["imported"] == 0
        assert second["skipped"] == 8  # all rows already present (+ markers)
        # Totals are stable across a re-import.
        assert second["net_deposited"] == 12000.0

    def test_empty_csv(self, session):
        result = import_ledger(session, b"", account_id=1)
        assert result["imported"] == 0
        assert result["errors"]  # "CSV has no headers"


# -----------------------------------------------------------------------
# build_summary with ledger
# -----------------------------------------------------------------------

def _ledger_entry(entry_type, amount, entry_date, account_id=1, eid=1, balance=0.0):
    e = MagicMock()
    e.entry_type = entry_type
    e.amount = amount
    e.entry_date = entry_date
    e.account_id = account_id
    e.id = eid
    e.balance = balance
    return e


def _holding(average_price, quantity, last_price):
    h = MagicMock()
    h.average_price = average_price
    h.quantity = quantity
    h.last_price = last_price
    h.pnl = (last_price - average_price) * quantity
    h.day_change = 0.0
    return h


class TestBuildSummaryWithLedger:
    def test_no_ledger_fields_are_none(self):
        result = build_summary([_holding(100.0, 10, 120.0)], [])
        assert result["net_deposited"] is None
        assert result["personal_xirr"] is None
        assert result["free_cash"] is None

    def test_ledger_metrics(self):
        ledger = [
            _ledger_entry("deposit", 10000.0, date(2024, 1, 1), eid=1, balance=10000.0),
            _ledger_entry("charge", -15.34, date(2024, 1, 3), eid=2, balance=9984.66),
            _ledger_entry("withdrawal", -3000.0, date(2024, 3, 1), eid=3, balance=6984.66),
        ]
        holdings = [_holding(100.0, 10, 120.0)]  # current value 1200
        result = build_summary(holdings, [], ledger)
        assert result["net_deposited"] == 7000.0   # 10000 − 3000
        assert result["total_withdrawn"] == 3000.0
        assert result["total_charges"] == 15.34
        assert result["free_cash"] == 6984.66      # latest balance
        # personal_xirr is computable (deposits/withdrawals + final value)
        assert result["personal_xirr"] is not None

    def test_personal_xirr_positive_when_value_exceeds_pocket(self):
        # Deposit 1000 a year ago; account now worth 1200 → positive return.
        one_year_ago = date.today() - timedelta(days=365)
        ledger = [_ledger_entry("deposit", 1000.0, one_year_ago, eid=1, balance=0.0)]
        holdings = [_holding(100.0, 10, 120.0)]  # value 1200, free_cash 0
        result = build_summary(holdings, [], ledger)
        assert result["personal_xirr"] > 0

    def test_personal_xirr_none_without_current_value(self):
        # Ledger imported but no holdings and no free cash → no meaningful return.
        ledger = [
            _ledger_entry("deposit", 1000.0, date(2024, 1, 1), eid=1, balance=0.0),
            _ledger_entry("withdrawal", -200.0, date(2024, 6, 1), eid=2, balance=0.0),
        ]
        result = build_summary([], [], ledger)
        assert result["net_deposited"] == 800.0
        assert result["personal_xirr"] is None  # no final value to measure against

    def test_free_cash_sums_across_accounts(self):
        ledger = [
            _ledger_entry("deposit", 5000.0, date(2024, 1, 1), account_id=1, eid=1, balance=500.0),
            _ledger_entry("deposit", 5000.0, date(2024, 1, 1), account_id=2, eid=2, balance=300.0),
        ]
        result = build_summary([], [], ledger)
        assert result["free_cash"] == 800.0  # 500 + 300
