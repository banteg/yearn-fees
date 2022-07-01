from operator import attrgetter
from typing import Iterable, List, Tuple
from ape import chain, Contract, convert
from ape.types import AddressType
from ape.contracts import ContractInstance, ContractLog
from evm_trace import TraceFrame
from functools import lru_cache

from yearn_fees.types import FeeParameters


@lru_cache(maxsize=None)
def get_registry():
    latest_registry = convert("v2.registry.ychad.eth", AddressType)
    return Contract(latest_registry)


@lru_cache(maxsize=None)
def _get_vaults():
    registry = get_registry()
    return list(registry.NewVault.range(12_000_000, chain.blocks.height, 1_000_000))


def get_endorsed_vaults(version=None):
    vaults = _get_vaults()
    if version is None:
        return [log.vault for log in vaults]
    else:
        return [log.vault for log in vaults if log.api_version == version]


@lru_cache
def _get_reports(vault: str):
    vault = Contract(vault)
    return list(vault.StrategyReported.range(0, chain.blocks.height, 1_000_000))


def get_reports(vault: ContractInstance) -> Iterable[ContractLog]:
    return _get_reports(vault.address)


def log_asof(stack: List[ContractLog], needle: ContractLog):
    """
    Find the last log in the stack preceeding the needle.
    Useful for establishing ordering within the same block.
    """
    key = attrgetter("block_number", "index")
    return [item for item in sorted(stack, key=key) if key(item) < key(needle)][-1]


def get_fees_at_harvest(vault: ContractInstance, report: ContractLog) -> int:
    """
    A more accurate method to get fee configuration.
    Supports fee adjustments in the same block as harvest.
    """
    strategy = Contract(report.strategy)
    vault = Contract(strategy.vault())

    management_fee = vault.UpdateManagementFee.range(0, chain.blocks.height, 1_000_000)
    performance_fee = vault.UpdatePerformanceFee.range(0, chain.blocks.height, 1_000_000)
    strategist_fee = vault.StrategyUpdatePerformanceFee.range(
        0, chain.blocks.height, 1_000_000, event_parameters={"strategy": report.strategy}
    )
    return FeeParameters(
        management_fee=log_asof(management_fee, report).managementFee,
        performance_fee=log_asof(performance_fee, report).performanceFee,
        strategist_fee=log_asof(strategist_fee, report).performanceFee,
    )


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
