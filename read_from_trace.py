import json
from decimal import Decimal
from pathlib import Path

import click
import yaml
from ape import Contract, chain, convert, networks
from ape.types import AddressType
from hexbytes import HexBytes
from rich import print


@click.group()
def cli():
    pass


def map_trace(trace, version):
    mapping = yaml.safe_load(open("vault-mapping.yml"))
    values = {}
    for item in mapping[version]:
        frame = next(f for f in trace if f["pc"] == item["pc"])
        for loc in ["storage", "memory"]:
            for pos, key in item.get(loc, {}).items():
                values[key] = int.from_bytes(HexBytes(frame[loc][pos]), "big")
    return values


@cli.command("file")
@click.argument("path")
def read_from_file(path):
    trace = json.load(open(path))["frames"]
    version = Path(path).name.split("_")[0][1:]
    fees = map_trace(trace, version)
    print(fees)


def get_vaults():
    latest_registry = convert("v2.registry.ychad.eth", AddressType)
    registry = Contract(latest_registry)

    logs = registry.NewVault.range(12_000_000, chain.blocks.height, 1_000_000)
    return [log for log in logs]


@cli.command("tx")
@click.argument("tx")
def read_from_tx(tx):
    receipt = chain.provider.get_transaction(tx)
    receipt_addresses = {log["address"] for log in receipt.logs}
    vaults = get_vaults()
    vault = next(log for log in vaults if log.vault in receipt_addresses)
    vault = Contract(vault.vault)
    version = vault.apiVersion()
    scale = 10 ** vault.decimals()
    trace = chain.provider._make_request("debug_traceTransaction", [tx])
    fees = map_trace(trace["structLogs"], version)
    for item in fees:
        if item in ["duration"]:
            continue
        fees[item] = Decimal(fees[item]) / scale
    print(fees)


if __name__ == "__main__":
    with networks.ethereum.mainnet.use_default_provider():
        chain.provider.web3.middleware_onion.remove("attrdict")
        chain.provider.web3.provider._request_kwargs["timeout"] = 600
        cli()
