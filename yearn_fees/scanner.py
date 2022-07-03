from collections import Counter
import random
from typing import List

from eth_utils import to_int
from evm_trace import TraceFrame
from rich import print

from yearn_fees.assess import assess_fees
from yearn_fees.memory_layout import MemoryLayout
from yearn_fees.traces import fees_from_trace, split_trace
from yearn_fees.utils import (
    get_decimals,
    get_reports,
    get_trace,
    get_vaults_by_version,
    reports_from_tx,
    version_from_report,
)


def find_value(trace, value):
    results = []
    if value == 0:
        return results
    for frame in trace:
        for i, item in enumerate(frame.memory):
            if to_int(item) == value:
                results.append((frame.pc, "memory", i))
        for i, item in enumerate(frame.stack):
            if to_int(item) == value:
                results.append((frame.pc, "stack", i))
    return results


def display_trace(trace: List[TraceFrame], version, fees):

    layout = MemoryLayout(trace, version)
    highlight = dict(
        total_fee=fees.total_fee,
        governance_fee=fees.governance_fee,
        **fees.dict(),
    )
    layout.display(highlight)

    if "duration" not in layout._memory_layout:
        print(f"[red]warn[/] duration not in memory layout, scan for it separately")


def layout_tx(tx, only_version=None):
    reports = reports_from_tx(tx)
    print(f"[green]found {len(reports)} reports")

    raw_trace = get_trace(tx)
    traces = split_trace(raw_trace, reports)

    for report, trace in zip(reports, traces):
        version = version_from_report(report)
        if only_version and version != only_version:
            continue
        print(report.__dict__)
        fees = assess_fees(report)
        print(repr(fees))

        decimals = get_decimals(report.contract_address)
        fees.as_table(decimals, "calculated fees")

        display_trace(trace, version, fees)


def find_duration(version):
    """
    Find non-ambiguous program counters where duration is in memory or on stack.
    """
    reports = get_reports()
    vaults = get_vaults_by_version()
    reports = [log for log in reports if log.contract_address in vaults[version]]
    txs = {log.transaction_hash.hex() for log in reports}
    txs = sorted(txs)[:10]
    durations = Counter()

    for tx in txs:
        print(f"[green]{tx}")
        reports = reports_from_tx(tx)
        raw_trace = get_trace(tx)
        traces = split_trace(raw_trace, reports)
        i = 0

        for report, trace in zip(reports, traces):
            vers = version_from_report(report)
            if vers != version:
                continue

            decimals = get_decimals(report.contract_address)

            fees_assess = assess_fees(report)

            fees_trace = fees_from_trace(trace, vers)
            fees_assess.compare(fees_trace, decimals)
            if fees_assess.duration != 0:
                i += 1
                durations.update(find_value(trace, fees_assess.duration))

            for (pc, loc, index), n in durations.most_common():
                if n != i:
                    continue
                print(f"pc={pc} loc={loc} index={index} [{n}]")
