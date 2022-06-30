from typing import Iterable
from ape import chain, Contract, convert
from ape.types import AddressType
from ape.contracts import ContractInstance, ContractLog


def get_registry():
    latest_registry = convert("v2.registry.ychad.eth", AddressType)
    return Contract(latest_registry)


def get_endorsed_vaults(version=None):
    registry = get_registry()
    new_vaults = registry.NewVault.range(12_000_000, chain.blocks.height, 1_000_000)
    if version is None:
        return [log.vault for log in new_vaults]
    else:
        return [log.vault for log in new_vaults if log.api_version == version]


def get_reports(vault: ContractInstance) -> Iterable[ContractLog]:
    return vault.StrategyReported.range(12_000, chain.blocks.height, 1_000_000)
