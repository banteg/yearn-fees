from decimal import Decimal
from queue import Queue

from pony.orm import select
from rich.console import Console

from yearn_fees.assess import assess_fees
from yearn_fees.models import Report, db_session, bind_db
from yearn_fees.traces import fees_from_trace, split_trace
from yearn_fees.utils import (
    get_decimals,
    get_fee_config_at_report,
    get_reports,
    get_trace,
    reports_from_tx,
    version_from_report,
)

console = Console()


def get_unindexed_transaction_hashes():
    reports = get_reports()
    transactions = {log.transaction_hash.hex() for log in reports}
    num_transactions = len(transactions)

    with db_session:
        for tx_hash in select(report.transaction_hash for report in Report):
            transactions.discard(tx_hash)

    console.log(
        f"[yellow]found {len(reports)} reports spanning {num_transactions} transactions, {len(transactions)} unindexed"
    )

    return transactions


def start():
    console.log("starting indexer")
    bind_db()

    queue = Queue()
    for tx_hash in get_unindexed_transaction_hashes():
        queue.put(tx_hash)

    worker(queue)


def worker(queue: Queue):
    while not queue.empty():
        tx = queue.get()
        console.log(f"[yellow]indexing {tx}")

        reports = reports_from_tx(tx)
        console.log(f"  {len(reports)} reports")

        raw_trace = get_trace(tx)
        traces = split_trace(raw_trace, reports)

        for report, trace in zip(reports, traces):
            version = version_from_report(report)
            decimals = get_decimals(report.contract_address)
            scale = 10**decimals

            fee_config = get_fee_config_at_report(report)
            fees_assess = assess_fees(report)
            fees_trace = fees_from_trace(trace, version)

            assert fees_assess == fees_trace, f"mismatch between assess and trace at {tx}"

            with db_session:
                Report(
                    block_number=report.block_number,
                    transaction_hash=report.transaction_hash.hex(),
                    log_index=report.log_index,
                    vault=report.contract_address,
                    strategy=report.strategy,
                    version=version,
                    gain=Decimal(report.gain) / scale,
                    loss=Decimal(report.loss) / scale,
                    debt_paid=Decimal(report.event_arguments.get("debtPaid", 0)) / scale,
                    total_gain=Decimal(report.totalGain) / scale,
                    total_loss=Decimal(report.totalLoss) / scale,
                    total_debt=Decimal(report.totalDebt) / scale,
                    debt_added=Decimal(report.debtAdded) / scale,
                    debt_ratio=report.debtRatio,
                    management_fee_bps=fee_config.management_fee,
                    performance_fee_bps=fee_config.performance_fee,
                    strategist_fee_bps=fee_config.strategist_fee,
                    management_fee=Decimal(fees_assess.management_fee) / scale,
                    performance_fee=Decimal(fees_assess.performance_fee) / scale,
                    strategist_fee=Decimal(fees_assess.strategist_fee) / scale,
                    duration=fees_assess.duration,
                )

        break