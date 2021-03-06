import logging
import threading
import warnings
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from ape import chain, networks
from dask import distributed
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from toolz import unique

from yearn_fees import utils
from yearn_fees.assess import assess_fees
from yearn_fees.models import ObjectNotFound, Report, bind_db, db_session, select
from yearn_fees.traces import fees_from_trace

FORBIDDEN_TXS = [
    # https://github.com/ledgerwatch/erigon/issues/4637
    "0xb9e6b6f275212824215e8f50818f12b37b7ca4c2e0b943785357c35b23743b94",
    "0xd770356649f1e60e7342713d483bd8946f967e544db639bd056dfccc8d534d8e",
    "0x9ef7a35012286fef17da12624aa124ebc785d9e7621e1fd538550d1209eb9f7d",
]


class Status(Enum):
    loaded = "green"
    skipped = "yellow"
    dropped = "red"


class WorkerConnection(distributed.WorkerPlugin):
    def setup(self, worker):
        silence_loggers()
        bind_db()
        networks.ethereum.mainnet.use_default_provider().__enter__()
        chain.provider.web3.provider._request_kwargs["timeout"] = 600


def silence_loggers():
    warnings.filterwarnings("ignore")
    for logger in ["distributed.utils_perf", "distributed.worker_memory"]:
        logging.getLogger(logger).setLevel(logging.ERROR)


def console_thread(console):
    for message in distributed.Sub("console"):
        console.log(message)


def log(message):
    distributed.Pub("console").put(message)


def get_unindexed_txs():
    """
    Find all transaction hashes which have unindexed reports.
    """
    reports = utils.get_reports()
    unindexed_reports = {(report.block_number, report.log_index): report for report in reports}

    with db_session:
        for row in Report.select():
            unindexed_reports.pop((row.block_number, row.log_index), None)

    num_txs = len(list(unique(report.transaction_hash.hex() for report in reports)))
    unindexed_txs = list(
        unique(report.transaction_hash.hex() for report in unindexed_reports.values())
    )
    log(f"[yellow]found {len(reports)} reports spanning {num_txs} transactions")
    log(f"[green]index {len(unindexed_reports)} reports spanning {len(unindexed_txs)} transactions")

    return unindexed_txs


def start():
    # start a dask cluster, lower n_workers if you run out of memory
    cluster = distributed.LocalCluster(n_workers=4, threads_per_worker=1)
    client = distributed.Client(cluster)
    client.register_worker_plugin(WorkerConnection())
    silence_loggers()

    # send messages from workers into the main thread's console using `log`
    console = Console(log_path=False)
    threading.Thread(target=console_thread, args=(console,), daemon=True).start()

    log(client.dashboard_link)

    unindexed_txs = client.submit(get_unindexed_txs).result()
    tasks = client.map(load_transaction, unindexed_txs)

    progress = Progress(
        TimeElapsedColumn(),
        BarColumn(),
        TimeRemainingColumn(),
        TextColumn("{task.percentage:>3.1f}% ({task.completed}/{task.total})"),
        console=console,
    )
    with progress:
        task = progress.add_task("index txs", total=len(unindexed_txs))
        for result in distributed.as_completed(tasks):
            progress.update(task, advance=1)


def load_transaction(tx):
    """
    Index and load all reports from a transaction into the database.
    """
    if tx in FORBIDDEN_TXS:
        log(f"[bold red]forbidden tx {tx}")
        return

    reports = utils.reports_from_tx(tx)
    traces = utils.get_split_trace(tx)

    stats = Counter()

    for report, trace in zip(reports, traces):
        with db_session:
            try:
                Report[report.block_number, report.log_index]
            except ObjectNotFound:
                pass
            else:
                stats[Status.skipped] += 1
                continue

        timestamp = chain.blocks[report.block_number].timestamp
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
            stats[Status.dropped] += 1
            continue

        with db_session:
            Report(
                block_number=report.block_number,
                timestamp=datetime.fromtimestamp(timestamp, timezone.utc),
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
            stats[Status.loaded] += 1

    stats = [
        f'[{stat.value}]{stat.name} {utils.plural("report", num)}[/]'
        for stat, num in stats.most_common()
    ]
    log(f"{', '.join(stats)} [yellow]at {tx}[/]")
