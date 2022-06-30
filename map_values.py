from collections import Counter, defaultdict
import sys
import json
from ape import chain, networks, Contract
from pathlib import Path
from rich import print
from semantic_version import Version
import click
from assess_fees import assess_fees

MAX_BPS = 10_000


@click.group()
def cli():
    pass


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
