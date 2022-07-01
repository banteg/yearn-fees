from collections import defaultdict
from operator import attrgetter
from typing import Iterable, List, Optional, Tuple
from ape import chain, Contract, convert
from ape.types import AddressType
from ape.contracts import ContractInstance, ContractLog
from evm_trace import TraceFrame
from functools import lru_cache

from yearn_fees.types import AsofDict, FeeHistory, FeeConfiguration

# sort key for logs/events
LOG_KEY = attrgetter("block_number", "index")


def get_range():
    return 11_000_000, chain.blocks.height, 1_000_000


@lru_cache(maxsize=None)
def get_registry():
    latest_registry = convert("v2.registry.ychad.eth", AddressType)
    return Contract(latest_registry)


@lru_cache(maxsize=None)
def _get_vaults():
    registry = get_registry()
    return list(registry.NewVault.range(*get_range()))


def get_endorsed_vaults(version=None):
    vaults = _get_vaults()
    if version is None:
        return [log.vault for log in vaults]
    else:
        return [log.vault for log in vaults if log.api_version == version]


@lru_cache
def _get_reports(vault: str):
    vault = Contract(vault)
    return list(vault.StrategyReported.range(*get_range()))


def get_reports(vault: ContractInstance) -> Iterable[ContractLog]:
    return _get_reports(vault.address)


def log_asof(stack: List[ContractLog], needle: ContractLog):
    """
    Find the last log in the stack preceeding the needle.
    Useful for establishing ordering within the same block.
    """
    key = attrgetter("block_number", "index")
    stack = sorted(stack, key=key)
    return [item for item in stack if key(item) < key(needle)][-1]


@lru_cache(maxsize=None)
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
        old_strategy = [
            value for key, value in strategist_fee[log.oldVersion].items() if key < LOG_KEY(log)
        ]
        strategist_fee[log.newVersion][LOG_KEY(log)] = old_strategy[-1]

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
    return fee_conifg.fees_at((report.block_number, report.index), report.strategy)


def get_trace(tx) -> Iterable[TraceFrame]:
    return list(chain.provider.get_transaction_trace(tx))


def get_report_from_tx(tx, vault=None) -> Tuple[ContractInstance, ContractLog]:
    receipt = chain.provider.get_transaction(tx)
    if vault is None:
        receipt_addresses = {log["address"] for log in receipt.logs}
        vault = next(v for v in get_endorsed_vaults() if v in receipt_addresses)

    vault = Contract(vault)
    report = next(vault.StrategyReported.from_receipt(receipt))
    return vault, report
