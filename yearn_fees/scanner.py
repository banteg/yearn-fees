from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Literal

from pydantic import BaseModel
from rich import print

from yearn_fees.assess import assess_fees
from yearn_fees.memory_layout import MemoryLayout
from yearn_fees.traces import fees_from_trace
from yearn_fees.types import Trace
from yearn_fees.utils import (
    get_decimals,
    get_reports,
    get_split_trace,
    get_vaults_by_version,
    reports_from_tx,
    version_from_report,
)


class MatchedValue(BaseModel):
    loc: Literal["stack", "memory"]
    pc: int
    index: int

    class Config:
        frozen = True


def find_value(trace, value) -> List[MatchedValue]:
    results = []
    if value == 0:
        return results
    # drop frames with a repeating program counter
    counts = Counter(frame.pc for frame in trace)

    for frame in trace:
        if counts[frame.pc] > 1:
            continue
        for loc in ["stack", "memory"]:
            for index, item in enumerate(getattr(frame, loc)):
                if item == value:
                    results.append(MatchedValue(loc=loc, pc=frame.pc, index=index))

    return results


def display_trace(trace: Trace, version, fees):

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

    traces = get_split_trace(tx)

    for report, trace in zip(reports, traces):
        version = version_from_report(report)
        if only_version and version != only_version:
            continue
        print(f"version {version}")
        print(report.__dict__)
        fees = assess_fees(report)
        print(repr(fees))

        decimals = get_decimals(report.contract_address)
        fees.as_table(decimals, "calculated fees")

        display_trace(trace, version, fees)


def find_duration_from_tx(tx, version=None, quiet=False):
    reports = reports_from_tx(tx)
    traces = get_split_trace(tx)
    results = Counter()

    for i, (report, trace) in enumerate(zip(reports, traces)):
        vers = version_from_report(report)
        if version and vers != version:
            continue

        decimals = get_decimals(report.contract_address)

        fees_assess = assess_fees(report)
        duration = fees_assess.duration
        if duration == 0:
            continue

        print(f"[green]{tx} report {i}")
        print(f"version {vers}")
        fees_trace = fees_from_trace(trace, vers)
        fees_assess.compare(fees_trace, decimals)

        for res in find_value(trace, duration):
            results[res] += 1

    if not quiet:
        for res, num in results.most_common():
            print(f"({num}) {res}")

    return results


def find_duration(version, tx=None, samples=10):
    """
    Find non-ambiguous program counters where duration is in memory or on stack.
    """
    reports = get_reports()
    vaults = get_vaults_by_version()
    reports = [log for log in reports if log.contract_address in vaults[version]]
    txs = {log.transaction_hash.hex() for log in reports}
    txs = sorted(txs)[:samples]
    results = Counter()

    with ThreadPoolExecutor(4) as pool:
        tasks = [pool.submit(find_duration_from_tx, tx, version, quiet=True) for tx in txs]
        for future in as_completed(tasks):
            results.update(future.result())

    best = max(results.values())
    for res, num in results.most_common():
        if num <= best - 2:
            continue
        print(f"({num}) {res}")
