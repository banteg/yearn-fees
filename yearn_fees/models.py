import os
from decimal import Decimal

from pony.orm import Database, Optional, PrimaryKey, Required, db_session

db = Database()


class Report(db.Entity):
    _table_ = "reports"
    # position
    block_number = Required(int)
    transaction_hash = Required(str)
    log_index = Required(int)
    # log
    vault = Required(str)
    strategy = Required(str)
    version = Required(str)
    # report
    gain = Required(Decimal, sql_type="numeric")
    loss = Required(Decimal, sql_type="numeric")
    debt_paid = Optional(Decimal, sql_type="numeric")
    total_gain = Required(Decimal, sql_type="numeric")
    total_loss = Required(Decimal, sql_type="numeric")
    total_debt = Required(Decimal, sql_type="numeric")
    debt_added = Required(Decimal, sql_type="numeric")
    debt_ratio = Required(int)
    # fee config
    management_fee_bps = Required(int)
    performance_fee_bps = Required(int)
    strategist_fee_bps = Required(int)
    # fees charged
    management_fee = Required(Decimal, sql_type="numeric")
    performance_fee = Required(Decimal, sql_type="numeric")
    strategist_fee = Required(Decimal, sql_type="numeric")
    duration = Required(int)

    PrimaryKey(block_number, log_index)


db.bind(
    provider="postgres",
    user=os.environ.get("PGUSER", "postgres"),
    host=os.environ.get("PGHOST", "127.0.0.1"),
    password=os.environ.get("PGPASS", None),
    database="yearn-fees",
)

db.generate_mapping(create_tables=True)
