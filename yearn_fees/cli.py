"""
yearn-fees layout version 0.3.3
yearn-fees layout tx 0xabc..def

yearn-fees compare version 0.4.3
yearn-fees compare tx 0xabc..def
"""
import random

import click
from ape import Contract, chain, networks
from rich import print

from yearn_fees.fees import assess_fees
from yearn_fees.map_values import display_tx, display_version
from yearn_fees.traces import fees_from_trace, split_trace
from yearn_fees.vault_utils import (
    get_decimals,
    get_endorsed_vaults,
    get_reports,
    get_trace,
    reports_from_tx,
    version_from_report,
)


class MainnetCommand(click.Command):
    def invoke(self, ctx):
        with networks.ethereum.mainnet.use_default_provider():
            chain.provider.web3.provider._request_kwargs["timeout"] = 600
            super().invoke(ctx)


@click.group()
def cli():
    pass


@cli.group()
def layout():
    pass


@cli.group()
def compare():
    pass


@compare.command("version", cls=MainnetCommand)
@click.argument("version")
def compare_version(version):
    vaults = get_endorsed_vaults(version)
    if len(vaults) > 5:
        vaults = random.sample(vaults, 5)

    for vault in vaults:
        vault = Contract(vault)
        decimals = vault.decimals()
        reports = get_reports(vault, only_profitable=True)
        if len(reports) > 5:
            reports = random.sample(reports, 5)

        for report in reports:
            print(report.__dict__)

            fees_calc = assess_fees(vault, report)
            fees_calc.as_table(decimals, title="calculated fees")

            trace = get_trace(report.transaction_hash.hex())
            fees_trace = fees_from_trace(trace, version)
            fees_trace.as_table(decimals, title="trace fees")

            fees_calc.compare(fees_trace, decimals)


@compare.command("tx", cls=MainnetCommand)
@click.argument("tx")
@click.option("--vault")
def compare_tx(tx, vault=None):
    reports = reports_from_tx(tx)
    print(f"[green]found {len(reports)} reports")

    raw_trace = get_trace(tx)
    traces = split_trace(raw_trace, reports)

    for report, trace in zip(reports, traces):
        print(report.__dict__)

        decimals = get_decimals(report.contract_address)
        version = version_from_report(report)

        fees_calc = assess_fees(report)
        fees_calc.as_table(decimals, title="calculated fees")

        fees_calc.as_table(decimals, "calculated fees")

        fees_trace = fees_from_trace(trace, version)
        fees_trace.as_table(decimals, title="trace fees")

        fees_calc.compare(fees_trace, decimals)


@layout.command("version", cls=MainnetCommand)
@click.argument("version")
def layout_version(version):
    display_version(version)


@layout.command("tx", cls=MainnetCommand)
@click.argument("tx")
def layout_tx(tx):
    display_tx(tx)


@cli.command(cls=MainnetCommand)
def dev():
    from rich import print

    tx = "0x706151dc2aef97f9688290f393131fe3f07b4f4ac61f82ed37b99e7ac7c4abee"
    receipt = chain.provider.get_transaction(tx)
    vault = Contract("0xd9788f3931Ede4D5018184E198699dC6d66C1915")
    reports = list(vault.StrategyReported.from_receipt(receipt))
    trace = get_trace(tx)
    parts, versions = split_trace(trace, reports)
    print([len(x) for x in parts])
    print(versions)
    result = [fees_from_trace(p, v) for p, v in zip(parts, versions)]
    print(result)


if __name__ == "__main__":
    cli()
