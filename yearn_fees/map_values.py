import random
from typing import List
from ape import Contract
from eth_utils import to_int
from evm_trace import TraceFrame
from rich import print

from yearn_fees.fees import assess_fees
from yearn_fees.memory_layout import MemoryLayout
from yearn_fees.traces import split_trace
from yearn_fees.vault_utils import (
    get_decimals,
    get_endorsed_vaults,
    get_fee_config_at_report,
    get_reports,
    get_trace,
    reports_from_tx,
    version_from_report,
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

    layout = MemoryLayout(trace, version)
    highlight = dict(
        total_fee=fees.total_fee,
        governance_fee=fees.governance_fee,
        **fees.dict(),
    )
    layout.display(highlight)

    for required_param in [
        "management_fee",
        "performance_fee",
        "strategist_fee",
        "gain",
        "duration",
    ]:
        if required_param not in layout._memory_layout:
            print(f"find {required_param}")
            find_value(trace, getattr(fees, required_param))


def layout_tx(tx):
    reports = reports_from_tx(tx)
    print(f"[green]found {len(reports)} reports")

    raw_trace = get_trace(tx)
    traces = split_trace(raw_trace, reports)

    for report, trace in zip(reports, traces):
        conf = get_fee_config_at_report(report)
        fees = assess_fees(report)
        decimals = get_decimals(report.contract_address)
        fees.as_table(decimals, "calculated fees")

        version = version_from_report(report)
        display_trace(trace, version, fees)

        print(repr(fees))
