import random
from collections import defaultdict
from typing import List, Literal

import click
from ape import Contract
from eth_utils import to_int
from evm_trace import TraceFrame
from pydantic import BaseModel
from rich import print
from rich.table import Table

from yearn_fees.fees import assess_fees
from yearn_fees.memory_layout import MemoryLayout
from yearn_fees.types import Fees
from yearn_fees.vault_utils import (
    get_endorsed_vaults,
    get_fee_config_at_report,
    get_report_from_tx,
    get_reports,
    get_trace,
)


def find_value(trace, value):
    print(f"[bold green]find value: {value}")
    if value == 0:
        print("[red]refusing to search for zero")
        return
    for frame in trace:
        for i, item in enumerate(frame.memory):
            if to_int(item) == value:
                print(f"[magenta]pc={frame.pc} loc=memory pos={i}")
        for i, item in enumerate(frame.stack):
            if to_int(item) == value:
                print(f"[yellow]pc={frame.pc} loc=stack pos={i}")


def display_trace(trace: List[TraceFrame], version, fees):
    highlight_values = set(fees.dict().values()) | {fees.governance_fee, fees.total_fee}

    layout = MemoryLayout(trace, version)
    layout.display(highlight_values, console)

    for required_param in [
        "management_fee",
        "performance_fee",
        "strategist_fee",
        "gain",
        "duration",
    ]:
        if required_param not in layout._memory_layout["_assessFees"]:
            print(f"find {required_param}")
            find_value(trace, getattr(fees, required_param))


def display_version(version):
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


def display_tx(tx, vault=None):
    vault, report = get_report_from_tx(tx, vault)
    conf = get_fee_config_at_report(report)
    print(conf)
    fees = assess_fees(vault, report)
    fees.as_table(vault.decimals(), "calculated fees")

    trace = get_trace(report.transaction_hash.hex())
    display_trace(trace, vault.apiVersion(), fees)

    print(repr(fees))
