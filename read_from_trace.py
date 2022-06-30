import json
from decimal import Decimal
from pathlib import Path

import click
import yaml
from ape import Contract, chain, convert, networks
from ape.types import AddressType
from hexbytes import HexBytes
from rich import print
from assess_fees import assess_fees


@click.group()
def cli():
    pass


def map_trace(trace, version, scale=1):
    mapping = yaml.safe_load(open("vault-mapping.yml"))
    values = {}

    for item in mapping[version]:
        frame = next(f for f in trace if f["pc"] == item["pc"])
        for loc in ["stack", "memory"]:
            for key, pos in item.get(loc, {}).items():
                values[key] = int.from_bytes(HexBytes(frame[loc][pos]), "big")

    for key in values:
        if key not in ["duration"]:
            values[key] = Decimal(values[key]) / scale

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
@click.option("--vault")
def read_from_tx(tx, vault=None):
    receipt = chain.provider.get_transaction(tx)
    if vault is None:
        receipt_addresses = {log["address"] for log in receipt.logs}
        vaults = get_vaults()
        vault = next(log for log in vaults if log.vault in receipt_addresses)
        vault = Contract(vault.vault)
    else:
        vault = Contract(vault)
    version = vault.apiVersion()
    scale = 10 ** vault.decimals()
    report = next(vault.StrategyReported.from_receipt(receipt))
    trace = chain.provider._make_request("debug_traceTransaction", [tx])

    fees_calc = assess_fees(vault, report)
    print("calculated", fees_calc)

    trace_fees = map_trace(trace["structLogs"], version, scale)
    print("traced", trace_fees)


if __name__ == "__main__":
    with networks.ethereum.mainnet.use_default_provider():
        chain.provider.web3.middleware_onion.remove("attrdict")
        chain.provider.web3.provider._request_kwargs["timeout"] = 600
        cli()
