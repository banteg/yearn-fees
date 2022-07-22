import random
from collections import defaultdict
from functools import lru_cache
from operator import attrgetter
from typing import Dict, List

from ape import Contract, chain
from ape.contracts import ContractLog
from ape.types import LogFilter
from semantic_version import Version
from toolz import concat, groupby, unique, valfilter

from yearn_fees import traces
from yearn_fees.cache import cache
from yearn_fees.types import FeeConfiguration, FeeHistory, LogPosition, Trace, asof

# sort key for logs/events
LOG_KEY = attrgetter("block_number", "log_index")


def get_range():
    return 11_000_000, chain.blocks.height, 1_000_000


@lru_cache(maxsize=None)
def get_registry():
    """
    Get the latest vault registry on mainnet.
    """
    return Contract("v2.registry.ychad.eth")


def get_vaults_by_version() -> Dict[str, List[str]]:
    registry = get_registry()
    vaults = groupby(attrgetter("api_version"), registry.NewVault)

    return {
        version: [log["vault"] for log in vaults[version]]
        for version in vaults
        if Version(version) >= Version("0.3.0")
    }


@cache.memoize()
def get_decimals(contract) -> int:
    return Contract(contract).decimals()


def get_endorsed_vaults(version=None, flat=False):
    """
    Find all vaults of version, or return all vaults by version or as a list.
    """
    vaults = get_vaults_by_version()
    if version:
        return vaults[version]

    if flat:
        return list(concat(vaults.values()))

    return vaults


def vault_selectors(event_name):
    """
    Find all variants of an event selector across all vault versions.
    """
    each_version = [Contract(vaults[0]) for vaults in get_vaults_by_version().values()]

    return list(
        unique(
            (getattr(vault, event_name).abi for vault in each_version),
            key=lambda abi: abi.selector,
        )
    )


def fetch_all_reports() -> List[ContractLog]:
    """
    Fetch all StrategyReported events for all endorsed vaults.
    """
    vaults = get_endorsed_vaults(flat=True)
    abis = vault_selectors("StrategyReported")
    topics = [[LogFilter.from_event(abi).topic_filter[0] for abi in abis]]
    filt = LogFilter(addresses=vaults, events=abis, topic_filter=topics)
    logs = chain.provider.get_contract_logs(filt)
    return list(logs)


def version_from_report(report: ContractLog):
    """
    Return a cached api version (for endorsed vaults) or read from chain.
    """
    vaults = get_endorsed_vaults()
    try:
        version = next(version for version in vaults if report.contract_address in vaults[version])
    except StopIteration:
        version = Contract(report.contract_address).apiVersion()

    return version


def get_reports(
    vault: str = None, only_profitable=False, non_matching_fees=False
) -> List[ContractLog]:
    """
    Get all vault reports, filtering them by vault, gain, or non-matching performance/strategist fees.
    """
    reports = fetch_all_reports()

    if vault:
        reports = [log for log in reports if log.contract_address == vault]

    if only_profitable:
        reports = [log for log in reports if log.gain > 0]

    if not vault and non_matching_fees:
        raise NotImplementedError("add a cached strategy to vault mapping first")

    if non_matching_fees:
        fee_conf = get_vault_fee_history(vault)

        def non_matching_fee(log):
            conf = fee_conf.at_report(log)
            return conf.performance_fee != conf.strategist_fee

        reports = [log for log in reports if non_matching_fee(log)]

    return reports


def get_sample_txs(version, num_vaults, num_txs):
    """
    Sample a version using several vaults and several txs from each vault.
    """
    reports = get_reports()
    vaults = get_endorsed_vaults(version)
    num_vaults = min(num_vaults, len(vaults))

    txs = []
    for vault in random.sample(vaults, num_vaults):
        vault_txs = list(
            unique(log.transaction_hash.hex() for log in reports if log.contract_address == vault)
        )
        txs.extend(random.sample(vault_txs, min(num_txs, len(vault_txs))))

    return txs


def txs_with_multiple_reports():
    """
    Find transactions where multiple reports have happened.
    """
    reports = get_reports()

    return valfilter(
        lambda logs: len(logs) >= 2, groupby(lambda log: log.transaction_hash, reports)
    )


def txs_with_multiple_vault_harvests():
    """
    Find transaction with multiple harvests of the same vault.
    """
    reports = get_reports()

    return valfilter(
        lambda logs: len(logs) >= 2,
        groupby(lambda log: (log.transaction_hash, log.contract_address), reports),
    )


def txs_with_multiple_strategy_harvests():
    """
    Find transaction with multiple harvests of the same strategy (0 duration).
    """
    reports = get_reports()

    return valfilter(
        lambda logs: len(logs) >= 2,
        groupby(lambda log: (log.transaction_hash, log.strategy), reports),
    )


def get_lifecycle_history(report: ContractLog) -> Dict[LogPosition, ContractLog]:
    """
    vault last report is set:
    - initialize = block.timestamp
    - report = block.timestamp

    strategy last report is set:
    - add strategy = block.timestamp
    - migrate strategy = block.timestamp
    - report = block.timestamp
    """
    version = Version(version_from_report(report))
    vault = Contract(report.contract_address)

    reports = get_reports(report.contract_address)
    additions = vault.StrategyAdded.range(
        chain.blocks.height,
        search_topics={"strategy": report["strategy"]},
    )
    migrations = list(
        vault.StrategyMigrated.range(
            chain.blocks.height,
            search_topics={"newVersion": report["strategy"]},
        )
    )
    last_report_updates = {}

    for log in reports:
        if version >= Version("0.3.5"):
            if log.strategy != report.strategy:
                continue
        last_report_updates[LOG_KEY(log)] = log

    for log in additions:
        last_report_updates[LOG_KEY(log)] = log

    for log in migrations:
        last_report_updates[LOG_KEY(log)] = log

    return {key: last_report_updates[key] for key in sorted(last_report_updates)}


def duration_from_report(report: ContractLog) -> int:
    history = get_lifecycle_history(report)
    last_event = asof(history, (report.block_number, report.log_index - 1))
    return (
        chain.blocks[report.block_number].timestamp
        - chain.blocks[last_event.block_number].timestamp
    )


def get_vault_fee_history(vault: str) -> FeeHistory:
    vault = Contract(vault)
    management_fee = {LOG_KEY(log): log.managementFee for log in vault.UpdateManagementFee}
    performance_fee = {LOG_KEY(log): log.performanceFee for log in vault.UpdatePerformanceFee}
    strategist_fee = defaultdict(dict)
    # strategy performance fee is set on init
    for log in vault.StrategyAdded:
        strategist_fee[log.strategy][LOG_KEY(log)] = log.performanceFee
    # on update strategy fee
    for log in vault.StrategyUpdatePerformanceFee:
        strategist_fee[log.strategy][LOG_KEY(log)] = log.performanceFee
    # and is also inherited on migration
    for log in vault.StrategyMigrated:
        strategist_fee[log.newVersion][LOG_KEY(log)] = asof(
            strategist_fee[log.oldVersion], LOG_KEY(log)
        )

    return FeeHistory(
        management_fee=management_fee,
        performance_fee=performance_fee,
        strategist_fee=strategist_fee,
    )


def get_fee_config_at_report(report: ContractLog) -> FeeConfiguration:
    """
    A more accurate method to get fee configuration.
    Supports fee adjustments in the same block as report.
    """
    vault = report.contract_address
    fee_conifg = get_vault_fee_history(vault)

    return fee_conifg.at_report(report)


@cache.memoize()
def _get_trace(tx: str) -> Trace:
    # use the lowest-level method available to bypass slow web3.py middlewares
    resp = chain.provider.web3.provider.make_request("debug_traceTransaction", [tx])
    trace = Trace.parse_obj(resp["result"]["structLogs"])

    return trace


def get_trace(tx) -> Trace:
    if isinstance(tx, bytes):
        tx = tx.hex()

    return _get_trace(tx)


def get_split_trace(tx) -> List[Trace]:
    if isinstance(tx, bytes):
        tx = tx.hex()
    trace = get_trace(tx)
    reports = reports_from_tx(tx)
    split = traces.split_trace(trace, reports)
    assert len(reports) == len(split), f"reports={len(reports)} split={len(split)} tx={tx}"

    return split


@cache.memoize()
def reports_from_tx(tx) -> List[ContractLog]:
    logs = []
    receipt = chain.provider.get_transaction(tx)
    for event in vault_selectors("StrategyReported"):
        logs.extend(receipt.decode_logs(event))

    reports = sorted(logs, key=LOG_KEY)

    return reports


def reports_from_block(block_number, vault=None, strategy=None) -> List[ContractLog]:
    reports = [log for log in get_reports() if log.block_number == block_number]
    if vault:
        reports = [log for log in reports if log.contract_address == vault]
    if strategy:
        reports = [log for log in reports if log.strategy == strategy]

    return reports


def plural(word, num):
    return f"{num} {word}" if num == 1 else f"{num} {word}s"
