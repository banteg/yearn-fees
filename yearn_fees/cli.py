"""
yearn-fees layout version 0.3.3
yearn-fees layout tx 0xabc..def

yearn-fees compare version 0.4.3
yearn-fees compare tx 0xabc..def
"""
import random

import click
from ape import Contract, chain, networks

from yearn_fees.fees import assess_fees
from yearn_fees.map_values import display_tx, display_version
from yearn_fees.traces import fees_from_trace
from yearn_fees.vault_utils import get_endorsed_vaults, get_report_from_tx, get_reports, get_trace


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
    vault, report = get_report_from_tx(tx, vault)
    version = vault.apiVersion()
    decimals = vault.decimals()
    trace = get_trace(tx)
    print()

    fees_calc = assess_fees(vault, report)
    fees_calc.as_table(decimals, title="calculated fees")

    fees_trace = fees_from_trace(trace, version)
    fees_trace.as_table(decimals, title="trace fees")

    fees_calc.compare(fees_trace, decimals)


@layout.command("version", cls=MainnetCommand)
@click.argument("version")
def layout_version(version):
    display_version(version)


@layout.command("tx", cls=MainnetCommand)
@click.argument("tx")
@click.option("--vault", default=None)
def layout_version(tx, vault):
    display_tx(tx, vault)


if __name__ == "__main__":
    cli()
