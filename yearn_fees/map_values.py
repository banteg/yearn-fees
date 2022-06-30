from collections import defaultdict
from typing import Literal

import click
from ape import chain, networks
from eth_utils import to_int
from evm_trace import TraceFrame
from pydantic import BaseModel
from rich import print
from rich.console import Console
from rich.table import Table

from yearn_fees.fees import assess_fees
from yearn_fees.types import Fees
from yearn_fees.vault_utils import get_endorsed_vaults, get_report_from_tx, get_trace


class FoundMapping(BaseModel):
    loc: Literal["stack", "memory"]
    pc: int
    pos: int
    name: str


@click.group()
def cli():
    pass


def count_values(frame: TraceFrame, fees: Fees):
    stack_memory = {to_int(item) for item in frame.stack + frame.memory}
    return len(stack_memory & {value for _, value in fees})


def display_frame(frame: TraceFrame, fees: Fees):
    table = Table(title=f"pc={frame.pc}")
    table.add_column("loc")
    table.add_column("pos", justify="right")
    table.add_column("value", justify="right")
    table.add_column("name")
    found = []

    for loc in ["stack", "memory"]:
        items = [to_int(item) for item in getattr(frame, loc)]
        for pos, item in enumerate(items):
            matches = [name for name, value in fees if value == item]
            for name in matches:
                found.append(FoundMapping(pc=frame.pc, loc=loc, pos=pos, name=name))
            table.add_row(
                loc,
                str(pos),
                str(item),
                ", ".join(matches),
            )

    if found:
        console.print(table)

    return found


def map_from_tx(tx, vault=None, max_frames=3):
    vault, report = get_report_from_tx(tx, vault)
    trace = get_trace(tx)

    fees = assess_fees(vault, report)
    print(fees.as_table(vault.decimals(), "calculated fees"))

    frames = sorted(trace, key=lambda frame: count_values(frame, fees), reverse=True)

    found = []
    for frame in frames[:max_frames]:
        results = display_frame(frame, fees)
        found.extend(results)

    return found


@cli.command("tx")
@click.argument("tx")
@click.option("--vault")
def map_tx(tx, vault=None):
    found = map_from_tx(tx, vault, max_frames=10)

    name_to_pc = defaultdict(list)
    pc_to_name = defaultdict(set)

    for item in found:
        name_to_pc[item.name].append(item.pc)
        pc_to_name[item.pc].add(item.name)

    print(name_to_pc)
    print(pc_to_name)


if __name__ == "__main__":
    console = Console()

    with networks.ethereum.mainnet.use_default_provider():
        chain.provider.web3.provider._request_kwargs["timeout"] = 600
        cli()
