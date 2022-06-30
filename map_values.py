from collections import Counter, defaultdict
import sys
import json
from ape import chain, networks, Contract
from pathlib import Path
from rich import print
from semantic_version import Version
import click

MAX_BPS = 10_000


@click.group()
def cli():
    pass


def assess_fees(vault, strategy, event, duration, version):
    if Version(version) >= Version("0.3.3"):
        SECS_PER_YEAR = 31_556_952
    else:
        SECS_PER_YEAR = 31_557_600

    vault = Contract(vault)
    strategy = Contract(strategy)
    pre_height = height = event["block_number"] - 1

    gain = event["event_arguments"]["gain"]
    if Version(version) >= Version("0.4.0"):
        # no fees are charges if there was no gain
        if gain == 0:
            return {}
    if Version(version) >= Version("0.3.5"):
        total_debt = vault.strategies(strategy, height=pre_height).totalDebt
        delegated_assets = strategy.delegatedAssets(height=pre_height)
        total_assets = total_debt - delegated_assets
    elif Version(version) >= Version("0.3.4"):
        total_debt = vault.totalDebt(height=pre_height)
        delegated_assets = vault.delegatedAssets(height=pre_height)
        total_assets = total_debt - delegated_assets
    elif Version(version) >= Version("0.3.1"):
        total_assets = vault.totalDebt(height=pre_height)
    elif Version(version) >= Version("0.3.0"):
        total_assets = vault.totalAssets(height=pre_height)
    else:
        raise ValueError("invalid version %s", version)

    # fee bps
    management_fee_bps = vault.managementFee(height=pre_height)
    performance_fee_bps = vault.performanceFee(height=pre_height)
    strategist_fee_bps = vault.strategies(strategy, height=pre_height).performanceFee
    print(f"{management_fee_bps=}")
    print(f"{performance_fee_bps=}")
    print(f"{strategist_fee_bps=}")

    management_fee = total_assets * duration * management_fee_bps // MAX_BPS // SECS_PER_YEAR
    strategist_fee = 0
    performance_fee = 0
    if gain > 0:
        strategist_fee += gain * strategist_fee_bps // MAX_BPS
        performance_fee += gain * performance_fee_bps // MAX_BPS

    total_fee = management_fee + performance_fee + strategist_fee
    if Version(version) >= Version("0.3.5"):
        if total_fee > gain:
            total_fee = gain
            management_fee = gain - performance_fee - strategist_fee

    return {
        "management_fee": management_fee,
        "performance_fee": performance_fee,
        "governance_fee": management_fee + performance_fee,
        "strategist_fee": strategist_fee,
        "total_fee": total_fee,
        "duration": duration,
        "gain": gain,
    }
    # look at full traces maybe? for duration and mgmt/perf separation


def count_values(frame, fees):
    values_present = set()
    for location in ["stack", "memory"]:
        values_present |= {
            value for value in fees.values() if value in frame[f"{location}_int"] and value != 0
        }
    return len(values_present)


def display_frame(frame, fees):
    print(f'[bold red]{frame["pc"]}[/]')
    values_found = defaultdict(set)
    for location in ["stack", "memory"]:
        values_present = [value for value in fees.values() if value in frame[f"{location}_int"]]
        if values_present:
            print(f"[cyan]{location}[/]")
            for i, item in enumerate(frame[f"{location}_int"]):
                match = [name for name, value in fees.items() if item == value and value != 0]
                print(f"  {i:2} {item}", ", ".join(match))
                for name in match:
                    values_found[name].add(frame["pc"])

            print(f"    {location}:")
            for i, item in enumerate(frame[f"{location}_int"]):
                match = [name for name, value in fees.items() if item == value and value != 0]
                for m in match:
                    print(f"      {i}: {m}")

    return values_found


def map_trace(data):
    strategy = data["event"]["event_arguments"]["strategy"]
    fees = assess_fees(data["vault"], strategy, data["event"], data["duration"], data["version"])
    frames = sorted(data["frames"], key=lambda frame: count_values(frame, fees), reverse=True)
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


if __name__ == "__main__":
    with networks.ethereum.mainnet.use_default_provider():
        cli()
