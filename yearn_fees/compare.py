from decimal import Decimal
from typing import Dict

from rich import box, print
from rich.console import Console
from rich.table import Table

from yearn_fees import assess, fork, utils
from yearn_fees.traces import fees_from_trace
from yearn_fees.types import Fees


def compare_methods(tx, only_version=None):
    tx = tx.hex() if isinstance(tx, bytes) else tx
    reports = utils.reports_from_tx(tx)
    traces = utils.get_split_trace(tx)
    forked = fork.fork_tx(tx)
    print(f"[green]found {len(reports)} reports at {tx}")

    results = []

    for report, trace, fork_report in zip(reports, traces, forked):
        version = utils.version_from_report(report)
        if only_version and version != only_version:
            continue

        print(f"version {version}")
        print(report.__dict__)

        decimals = utils.get_decimals(report.contract_address)

        fees_calc = assess.assess_fees(report)
        fees_calc.as_table(decimals, title="calculated fees")

        fees_trace = fees_from_trace(trace, version)
        fees_trace.as_table(decimals, title="trace fees")

        results.append({"assess": fees_calc, "trace": fees_trace, "fork": fork_report})
        compare_as_table(results[-1], decimals)
    
    return results


def compare_as_table(fees: Dict[str, Fees], decimals: int, output=True):
    table = Table(box=box.SIMPLE)
    table.add_column("key")
    for name in fees:
        table.add_column(name, justify="right")

    table.add_column("test")

    def format_value(source, key):
        value = getattr(source, key, None)
        if key == "duration":
            return format(value, ",d") if value is not None else value

        return (
            format(Decimal(value) / 10**decimals, f",.{decimals}f")
            if value is not None
            else value
        )

    for key in [
        "management_fee",
        "performance_fee",
        "strategist_fee",
        "total_fee",
        "gain",
        "duration",
    ]:
        values_set = {getattr(source, key, None) for source in fees.values()}
        print(f"{values_set=}")
        table.add_row(
            key,
            *[format_value(source, key) for source in fees.values()],
            f"[green]✔︎" if len(values_set) == 1 and None not in values_set else "[red]✘",
        )

    if output:
        console = Console()
        console.print(table)
    else:
        return table
