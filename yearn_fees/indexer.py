from decimal import Decimal
from functools import wraps
from ape import networks

from pony.orm import select
from rich.console import Console

from yearn_fees import utils
from yearn_fees.assess import assess_fees
from yearn_fees.models import Report, bind_db, db_session
from yearn_fees.traces import fees_from_trace

from dask import distributed

console = Console()


def with_connection(f):
    """
    Since workers start in separate processes, we need setup eth and db connections fot them.
    """

    @wraps(f)
    def wrapped(*args, **kwds):
        bind_db()
        with networks.ethereum.mainnet.use_default_provider():
            f(*args, **kwds)

    return wrapped


def get_unindexed_transaction_hashes():
    reports = utils.get_reports()
    transactions = {log.transaction_hash.hex() for log in reports}

    num_transactions = len(transactions)

    with db_session:
        for tx_hash in select(report.transaction_hash for report in Report):
            transactions.discard(tx_hash)

    console.log(
        f"[yellow]found {len(reports)} reports spanning {num_transactions} transactions, {len(transactions)} unindexed"
    )

    tx_height = {log.transaction_hash.hex(): log.block_number for log in reports}
    return sorted(transactions, key=tx_height.get)


def start(num_workers: int):
    console.log("starting indexer")
    client = distributed.Client()
    console.log(client.dashboard_link)
    bind_db()

    queue = distributed.Queue()
    for tx_hash in get_unindexed_transaction_hashes():
        queue.put(tx_hash)

    tasks = [client.submit(worker, n, queue) for n in range(num_workers)]
    distributed.wait(tasks)

    print("done")


@with_connection
def worker(name, queue):
    while queue.qsize():
        tx = queue.get()
        console.log(f"[yellow]{name} indexing {tx}")

        reports = utils.reports_from_tx(tx)
        traces = utils.get_split_trace(tx)

        for report, trace in zip(reports, traces):
            version = utils.version_from_report(report)
            decimals = utils.get_decimals(report.contract_address)
            scale = 10**decimals

            fee_config = utils.get_fee_config_at_report(report)
            fees_assess = assess_fees(report)
            fees_trace = fees_from_trace(trace, version)
            # some versions can't get an accurate duration from trace
            if fees_trace.duration is None:
                fees_trace.duration = fees_assess.duration

            if fees_assess != fees_trace:
                console.log(f"[red]mismatch between assess and trace at {tx}")
                fees_assess.compare(fees_trace, decimals)
                continue

            fees_assess.as_table(decimals, tx)

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
