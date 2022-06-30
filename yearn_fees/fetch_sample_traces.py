import json
import random
from dataclasses import asdict
from operator import attrgetter
from pathlib import Path

import click
from ape import Contract, chain, convert, networks
from ape.types import AddressType
from semantic_version import Version
from toolz import groupby


def json_encoder(value):
    if isinstance(value, bytes):
        return value.hex()


@click.group()
def cli():
    pass


@cli.command("vaults")
def dump_vaults():
    """
    Output all vaults and strategies that were ever harvested.
    """
    latest_registry = convert("v2.registry.ychad.eth", AddressType)
    registry = Contract(latest_registry)
    sep = "    "
    logs = registry.NewVault.range(12_000_000, chain.blocks.height, 1_000_000)
    vaults = groupby(attrgetter("api_version"), logs)
    for version in sorted(vaults):
        print(version)
        for log in vaults[version]:
            vault = Contract(log.vault)
            mgmt = vault.managementFee()
            perf = vault.performanceFee()
            print(f"{sep}{vault} {mgmt} {perf}")
            reports = vault.StrategyReported.range(12_000_000, chain.blocks.height, 1_000_000)
            strategies = {log.strategy for log in reports}
            for strategy in strategies:
                spf = vault.strategies(strategy).performanceFee
                print(f"{sep*2}{strategy} {spf}")


def get_vaults():
    latest_registry = convert("v2.registry.ychad.eth", AddressType)
    registry = Contract(latest_registry)

    logs = registry.NewVault.range(12_000_000, chain.blocks.height, 1_000_000)
    return [log.vault for log in logs]


def combine_trace(vault, report):
    trace = chain.provider._make_request("debug_traceTransaction", [report.transaction_hash.hex()])
    frames = [
        frame
        for frame in trace["structLogs"]
        # if str(frame["pc"]) in program_counters[f"v{version}"]
        # and frame["op"] == "JUMP"  # more likely to be the end of a method
    ]
    for frame in frames:
        frame["stack_int"] = [int(item, 16) for item in frame["stack"]]
        frame["memory_int"] = [int(f"0x{item}", 16) for item in frame["memory"]]
    # specifying height is an aspirational api, it requires patching ape
    a = vault.strategies(report.strategy, height=report.block_number - 1)
    b = vault.strategies(report.strategy, height=report.block_number)
    version = vault.apiVersion()
    output = {
        "frames": frames,
        "event": asdict(report),
        "strategy": b.__dict__,
        "vault": vault.address,
        "version": version,
        "duration": b.lastReport - a.lastReport,
    }
    path = Path("traces") / f"v{version}_{report.transaction_hash.hex()}.json"
    path.write_text(json.dumps(output, default=json_encoder, indent=2))
    print(f"saved {path}")
    return output


@cli.command("sample")
def sample():
    program_counters = json.load(open("metadata/pcs_by_version.json"))

    latest_registry = convert("v2.registry.ychad.eth", AddressType)
    registry = Contract(latest_registry)

    logs = registry.NewVault.range(12_000_000, chain.blocks.height, 1_000_000)
    vaults = groupby(attrgetter("api_version"), logs)

    for version in sorted(vaults, key=Version):
        if Version(version) < Version("0.3.0"):
            continue
        for item in vaults[version]:
            vault = Contract(item.vault)
            logs = vault.StrategyReported.range(12_000_000, chain.blocks.height, 1_000_000)
            reports = [log for log in logs if log.gain > 0]
            random.shuffle(reports)
            # sample three random harvests for each vault
            for report in reports[:3]:
                combine_trace(vault, report)


@cli.command("dump_tx")
@click.argument("txhash")
def dump_tx(txhash):
    receipt = chain.provider.get_transaction(txhash)
    vaults = get_vaults()
    vault = Contract(next(log["address"] for log in receipt.logs if log["address"] in vaults))
    report = next(vault.StrategyReported.from_receipt(receipt))
    combine_trace(vault, report)


if __name__ == "__main__":
    with networks.ethereum.mainnet.use_default_provider():
        chain.provider.web3.provider._request_kwargs["timeout"] = 600
        cli()
