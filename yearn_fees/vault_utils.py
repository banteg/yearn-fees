from collections import defaultdict
from functools import lru_cache
from operator import attrgetter
from typing import Iterable, List, Optional, Tuple

from ape import Contract, chain, convert
from ape.contracts import ContractInstance, ContractLog
from ape.types import AddressType
from toolz import concat, groupby, unique

from yearn_fees.cache import cache
from yearn_fees.types import AsofDict, FeeConfiguration, FeeHistory

# sort key for logs/events
LOG_KEY = attrgetter("block_number", "log_index")


def get_range():
    return 11_000_000, chain.blocks.height, 1_000_000


@lru_cache(maxsize=None)
def get_registry():
    latest_registry = convert("v2.registry.ychad.eth", AddressType)
    return Contract(latest_registry)


@cache.memoize()
def _get_vaults():
    registry = get_registry()
    logs = registry.NewVault.range(*get_range())
    vaults = groupby(attrgetter("api_version"), logs)
    return {version: [log.vault for log in vaults[version]] for version in vaults}


def get_endorsed_vaults(version=None):
    vaults = _get_vaults()
    if version:
        return vaults[version]

    return list(concat(vaults.values()))


@cache.memoize()
def fetch_all_reports() -> List[ContractLog]:
    """
    Fetch all StrategyReported events for all endorsed vaults.
    """
    vaults = _get_vaults()
    # find all variants of the selector
    strategy_reported = list(
        unique(
            [Contract(item[0]).StrategyReported.abi for item in vaults.values()],
            key=lambda abi: abi.selector,
        )
    )
    all_vaults = list(concat(vaults.values()))
    logs = chain.provider.get_contract_logs(
        address=all_vaults,
        abi=strategy_reported,
        start_block=0,
        stop_block=chain.blocks.height,
        block_page_size=1_000_000,
    )
    return list(logs)


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

    if not vault and non_matching_fee:
        raise NotImplementedError("add a cached strategy to vault mapping first")

    if non_matching_fees:
        fee_conf = get_vault_fee_config(vault)

        def non_matching_fee(log):
            conf = fee_conf.at_report(log)
            return conf.performance_fee != conf.strategist_fee

        reports = [log for log in reports if non_matching_fee(log)]

    return reports


def log_asof(stack: List[ContractLog], needle: ContractLog):
    """
    Find the last log in the stack preceeding the needle.
    Useful for establishing ordering within the same block.
    """
    key = attrgetter("block_number", "index")
    stack = sorted(stack, key=key)
    return [item for item in stack if key(item) < key(needle)][-1]


# @cache.memoize()
def get_vault_fee_config(vault: str) -> FeeHistory:
    vault = Contract(vault)
    management_fee = {
        LOG_KEY(log): log.managementFee for log in vault.UpdateManagementFee.range(*get_range())
    }
    performance_fee = {
        LOG_KEY(log): log.performanceFee for log in vault.UpdatePerformanceFee.range(*get_range())
    }
    strategist_fee = defaultdict(AsofDict)
    # strategy performance fee is set on init
    for log in vault.StrategyAdded.range(*get_range()):
        strategist_fee[log.strategy][LOG_KEY(log)] = log.performanceFee
    # on update strategy fee
    for log in vault.StrategyUpdatePerformanceFee.range(*get_range()):
        strategist_fee[log.strategy][LOG_KEY(log)] = log.performanceFee
    # and is also inherited on migration
    for log in vault.StrategyMigrated.range(*get_range()):
        strategist_fee[log.newVersion][LOG_KEY(log)] = strategist_fee[log.oldVersion][LOG_KEY(log)]

    return FeeHistory(
        management_fee=AsofDict(management_fee),
        performance_fee=AsofDict(performance_fee),
        strategist_fee=strategist_fee,
    )


def get_fee_config_at_report(report: ContractLog, vault: Optional[str] = None) -> FeeConfiguration:
    """
    A more accurate method to get fee configuration.
    Supports fee adjustments in the same block as report.
    """
    strategy = Contract(report.strategy)
    if vault is None:
        vault = strategy.vault()
    fee_conifg = get_vault_fee_config(vault)

    return fee_conifg.at_report(report)


@cache.memoize()
def get_trace(tx):
    return list(chain.provider.get_transaction_trace(tx))


def get_report_from_tx(tx, vault=None) -> Tuple[ContractInstance, ContractLog]:
    receipt = chain.provider.get_transaction(tx)
    if vault is None:
        receipt_addresses = {log["address"] for log in receipt.logs}
        vault = next(v for v in get_endorsed_vaults() if v in receipt_addresses)

    vault = Contract(vault)
    report = next(vault.StrategyReported.from_receipt(receipt))
    return vault, report
