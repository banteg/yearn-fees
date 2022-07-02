import random
from collections import defaultdict
from typing import List, Literal

import click
from ape import Contract, chain, networks
from eth_utils import to_int
from evm_trace import TraceFrame
from pydantic import BaseModel
from rich import print
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from yearn_fees.fees import assess_fees
from yearn_fees.memory_layout import MEMORY_LAYOUT, PROGRAM_COUNTERS
from yearn_fees.types import Fees
from yearn_fees.vault_utils import (
    get_endorsed_vaults,
    get_fee_config_at_report,
    get_report_from_tx,
    get_reports,
    get_trace,
)


class FoundMapping(BaseModel):
    loc: Literal["stack", "memory"]
    pc: int
    pos: int
    name: str


@click.group()
def cli():
    pass


def count_values(frame: TraceFrame, fees: Fees):
    """
    Count exact matches against stack and memory. Exclude 0 as this value is too common.
    """
    stack_memory = {to_int(item) for item in frame.stack + frame.memory}
    return len(stack_memory & {value for _, value in fees} - {0})


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
            matches = [name for name, value in fees if value == item and item != 0]
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


def map_from_tx(tx=None, vault=None, report=None, max_frames=3):
    # specify either tx and optionally vault, or vault and report
    if tx is not None:
        vault, report = get_report_from_tx(tx, vault)
        trace = get_trace(tx)
    else:
        trace = get_trace(report.transaction_hash.hex())

    fees = assess_fees(vault, report)
    fees.as_table(vault.decimals(), "calculated fees")

    frames = sorted(trace, key=lambda frame: count_values(frame, fees), reverse=True)

    found = []
    for frame in frames[:max_frames]:
        results = display_frame(frame, fees)
        found.extend(results)

    return found


def found_to_guess(found):
    name_to_pc = defaultdict(list)
    pc_to_name = defaultdict(set)

    for item in found:
        name_to_pc[item.name].append(item.pc)
        pc_to_name[item.pc].add(item.name)

    console.print(name_to_pc)
    console.print(pc_to_name)


def find_value(trace, value):
    print(f"[bold green]find value: {value}")
    if value == 0:
        print('[red]refusing to search for zero')
        return
    for frame in trace:
        for i, item in enumerate(frame.memory):
            if to_int(item) == value:
                print(f"[magenta]pc={frame.pc} loc=memory pos={i}")
        for i, item in enumerate(frame.stack):
            if to_int(item) == value:
                print(f"[yellow]pc={frame.pc} loc=stack pos={i}")


@cli.command("tx")
@click.argument("tx")
@click.option("--vault")
def map_tx(tx, vault=None):
    found = map_from_tx(tx, vault, max_frames=10)
    found_to_guess(found)


def display_trace(trace: List[TraceFrame], version, fees):
    highlight_values = set(fees.dict().values()) | {fees.governance_fee, fees.total_fee}
    mem_pos = MEMORY_LAYOUT[version]["_assessFees"]
    program_counters = PROGRAM_COUNTERS[version]

    table = Table()
    table.add_column("pc", justify="right")
    table.add_column("op")
    for name in mem_pos:
        table.add_column(name, justify="right")

    for i, frame in enumerate(trace):
        if frame.pc not in program_counters:
            continue
        row = [str(frame.pc), frame.op]
        for name, pos in mem_pos.items():
            try:
                value = to_int(frame.memory[pos])
                style = "[bold yellow]" if value in highlight_values else ""
                row.append(f"{style}{value}")
            except IndexError:
                row.append("[dim](unallocated)")

        table.add_row(*row)

    console.print(table)

    for required_param in ['management_fee', 'performance_fee', 'strategist_fee', 'gain', 'duration']:
        if required_param not in mem_pos:
            print(f'find {required_param}')
            find_value(trace, getattr(fees, required_param))


@cli.command("display_mapped")
@click.argument("version")
def mapped(version):
    vaults = get_endorsed_vaults(version)
    if len(vaults) > 1:
        vaults = random.sample(vaults, 1)

    for vault in vaults:
        vault = Contract(vault)
        reports = list(get_reports(vault=vault, only_profitable=True, non_matching_fees=True))
        if len(reports) > 1:
            reports = random.sample(reports, 1)

        for report in reports:
            print(report.__dict__)
            fees = assess_fees(vault, report)
            fees.as_table(vault.decimals(), "calculated fees")

            trace = get_trace(report.transaction_hash.hex())
            display_trace(trace, version, fees)

            print(repr(fees))


@cli.command("display_tx")
@click.argument("tx")
@click.option("--vault")
def mapped_tx(tx, vault=None):
    vault, report = get_report_from_tx(tx, vault)
    conf = get_fee_config_at_report(report)
    print(conf)
    fees = assess_fees(vault, report)
    fees.as_table(vault.decimals(), "calculated fees")

    trace = get_trace(report.transaction_hash.hex())
    display_trace(trace, vault.apiVersion(), fees)

    print(repr(fees))


@cli.command("version")
@click.argument("version")
def map_version(version):
    found = []
    with Progress(console=console) as progress:
        vaults = get_endorsed_vaults(version)
        if len(vaults) > 5:
            vaults = random.sample(vaults, 5)

        vaults_task = progress.add_task("vaults", total=len(vaults))

        for vault in vaults:
            vault = Contract(vault)
            reports = get_reports(vault, only_profitable=True)
            if len(reports) > 5:
                reports = random.sample(reports, 5)

            reports_task = progress.add_task("reports", total=len(reports))
            for report in reports:
                results = map_from_tx(vault=vault, report=report, max_frames=5)
                found.extend(results)
                progress.update(reports_task, advance=1)

            progress.update(vaults_task, advance=1)

    found_to_guess(found)


if __name__ == "__main__":
    console = Console()

    with networks.ethereum.mainnet.use_default_provider():
        chain.provider.web3.provider._request_kwargs["timeout"] = 600
        cli()
