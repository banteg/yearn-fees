from collections import Counter, defaultdict
import sys
import json
from ape import chain, networks, Contract
from pathlib import Path
from hexbytes import HexBytes
from rich import print
from semantic_version import Version
import click
from yearn_fees.assess_fees import assess_fees
from yearn_fees.read_from_trace import get_vaults

MAX_BPS = 10_000


@click.group()
def cli():
    pass


def stack_to_ints(stack):
    return [int.from_bytes(HexBytes(value), "big") for value in stack]


def count_values(frame, fees):
    values_present = set()
    for location in ["stack", "memory"]:
        stack = stack_to_ints(frame[location])
        values_present |= {value for value in fees.values() if value in stack}
    return len(values_present)


def display_frame(frame, fees):
    print(f'[bold red]{frame["pc"]}[/]')
    values_found = defaultdict(set)
    for location in ["stack", "memory"]:
        stack = stack_to_ints(frame[location])
        values_present = [value for value in fees.values() if value in stack]
        if values_present:
            print(f"[cyan]{location}[/]")
            for i, item in enumerate(stack):
                match = [name for name, value in fees.items() if item == value]
                print(f"  {i:2} {item}", ", ".join(match))
                for name in match:
                    values_found[name].add(frame["pc"])

            print(f"    {location}:")
            for i, item in enumerate(stack):
                match = [name for name, value in fees.items() if item == value]
                for m in match:
                    print(f"      {i}: {m}")

    return values_found


def map_trace(trace, report, vault):
    fees = assess_fees(vault, report)
    print(fees)
    frames = sorted(trace["structLogs"], key=lambda frame: count_values(frame, fees), reverse=True)
    pcs = Counter()
    finds = defaultdict(set)
    for frame in frames[:3]:
        found = display_frame(frame, fees)
        for name in found:
            finds[name] |= found[name]
        pcs[frame["pc"]] += 1

    return pcs, finds


@cli.command("version")
@click.argument("version")
def map_version(version):
    pcs = Counter()
    finds = defaultdict(set)
    for path in Path(f"traces").glob(f"v{version}_*.json"):
        try:
            pc, found = map_trace(json.loads(path.read_text()))
            pcs += pc
            for name in found:
                finds[name] |= found[name]
        except AssertionError as e:
            print(e)
    print(f"[bold green]most common[/]")
    for a, b in pcs.most_common():
        print(a, b)
    for a, b in finds.items():
        print(f"[bold green]{a}[/]", b)


@cli.command("file")
@click.argument("path")
def map_file(path):
    map_trace(json.loads(Path(path).read_text()))


def get_trace_cached(tx, vault=None):
    receipt = chain.provider.get_transaction(tx)
    if vault is None:
        receipt_addresses = {log["address"] for log in receipt.logs}
        vaults = get_vaults()
        vault = next(log for log in vaults if log.vault in receipt_addresses)
        vault = Contract(vault.vault)
    else:
        vault = Contract(vault)
    version = vault.apiVersion()
    report = next(vault.StrategyReported.from_receipt(receipt))

    path = Path(f"traces/v{version}_{tx}.json")
    if path.exists():
        trace = json.loads(path.read_text())
    else:
        trace = chain.provider._make_request("debug_traceTransaction", [tx])
        path.write_text(json.dumps(trace))

    return trace, report, vault


@cli.command("tx")
@click.argument("tx")
@click.option("--vault")
def map_tx(tx, vault=None):
    trace, report, vault = get_trace_cached(tx, vault)
    pcs, finds = map_trace(trace, report, vault)
    print(f"[bold green]most common[/]")
    for a, b in pcs.most_common():
        print(a, b)
    for a, b in finds.items():
        print(f"[bold green]{a}[/]", b)


if __name__ == "__main__":
    with networks.ethereum.mainnet.use_default_provider():
        chain.provider.web3.middleware_onion.remove("attrdict")
        chain.provider.web3.provider._request_kwargs["timeout"] = 600
        cli()
