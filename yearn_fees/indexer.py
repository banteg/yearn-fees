import logging
from decimal import Decimal

from ape import chain, networks
from dask import distributed
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from yearn_fees import utils
from yearn_fees.assess import assess_fees
from yearn_fees.models import Report, bind_db, db_session, select
from yearn_fees.traces import fees_from_trace
import threading
import warnings


class WorkerConnection(distributed.WorkerPlugin):
    def setup(self, worker):
        silence_loggers()
        bind_db()
        networks.ethereum.mainnet.use_default_provider().__enter__()
        chain.provider.web3.provider._request_kwargs["timeout"] = 600


def silence_loggers():
    warnings.filterwarnings("ignore")  # , r".*Connecting Geth plugin to non-Geth network.*")
    for logger in ["distributed.utils_perf", "distributed.worker_memory"]:
        logging.getLogger(logger).setLevel(logging.ERROR)


def console_thread(console):
    for message in distributed.Sub("console"):
        console.log(message)


def log(message):
    distributed.Pub("console").put(message)


def plural(word, count):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def get_unindexed_transaction_hashes():
    reports = utils.get_reports()
    transactions = {log.transaction_hash.hex() for log in reports}

    num_transactions = len(transactions)

    with db_session:
        for tx_hash in select(report.transaction_hash for report in Report):
            transactions.discard(tx_hash)

    log(
        f"[yellow]{len(reports)} reports spanning {num_transactions} transactions, {len(transactions)} unindexed"
    )

    tx_height = {log.transaction_hash.hex(): log.block_number for log in reports}
    return sorted(transactions, key=tx_height.get)


def start():
    # start a dask cluster, lower n_workers if you run out of memory
    cluster = distributed.LocalCluster(n_workers=8, threads_per_worker=1)
    client = distributed.Client(cluster)
    client.register_worker_plugin(WorkerConnection())
    silence_loggers()

    # send messages from workers into the main thread's console using `log`
    console = Console()
    threading.Thread(target=console_thread, args=(console,), daemon=True).start()

    log(client.dashboard_link)

    unindexed = client.submit(get_unindexed_transaction_hashes).result()
    tasks = client.map(load_transaction, unindexed)

    progress = Progress(
        TimeElapsedColumn(),
        BarColumn(),
        TimeRemainingColumn(),
        TextColumn("{task.percentage:>3.1f}% ({task.completed}/{task.total})"),
        console=console,
    )
    with progress:
        task = progress.add_task("index txs", total=len(unindexed))
        for result in distributed.as_completed(tasks):
            progress.update(task, advance=1)


def load_transaction(tx):
    """
    Index and load all reports from a transaction into the database.
    """
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
            log(f"[red]mismatch at {tx}")
            log(fees_assess.compare(fees_trace, decimals, output=False))
            continue
        else:
            log(f"[green]reconciled {plural('report', len(reports))} at {tx}")

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
