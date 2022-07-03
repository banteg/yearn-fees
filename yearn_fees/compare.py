from rich import print

from yearn_fees.assess import assess_fees
from yearn_fees.traces import fees_from_trace, split_trace
from yearn_fees.utils import get_decimals, get_trace, reports_from_tx, version_from_report


def compare_methods(tx, only_version=None):
    reports = reports_from_tx(tx)
    print(f"[green]found {len(reports)} reports")

    raw_trace = get_trace(tx)
    traces = split_trace(raw_trace, reports)

    for report, trace in zip(reports, traces):
        version = version_from_report(report)
        if only_version and version != only_version:
            continue
        print(report.__dict__)

        decimals = get_decimals(report.contract_address)

        fees_calc = assess_fees(report)
        fees_calc.as_table(decimals, title="calculated fees")

        fees_trace = fees_from_trace(trace, version)
        fees_trace.as_table(decimals, title="trace fees")

        fees_calc.compare(fees_trace, decimals)
