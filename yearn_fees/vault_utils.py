from typing import Iterable, Tuple
from ape import chain, Contract, convert
from ape.types import AddressType
from ape.contracts import ContractInstance, ContractLog
from evm_trace import TraceFrame
from functools import lru_cache


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


def get_reports(vault: ContractInstance) -> Iterable[ContractLog]:
    return vault.StrategyReported.range(12_000, chain.blocks.height, 1_000_000)


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
