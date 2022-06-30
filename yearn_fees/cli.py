from ape import chain, networks, Contract
from yearn_fees.traces import fees_from_trace
from yearn_fees.vault_utils import get_trace, get_report_from_tx
from yearn_fees.fees import assess_fees
import click


@click.group()
def cli():
    pass


@cli.command("tx")
@click.argument("tx")
@click.option("--vault")
@click.option("--compare", is_flag=True)
def read_from_tx(tx, vault=None, compare=False):
    vault, report = get_report_from_tx(tx, vault)
    version = vault.apiVersion()
    decimals = vault.decimals()
    trace = get_trace(tx)
    print()

    fees_calc = assess_fees(vault, report)
    fees_calc.as_table(decimals, title="calculated fees")

    fees_trace = fees_from_trace(trace, version)
    fees_trace.as_table(decimals, title="trace fees")

    if compare:
        fees_calc.compare(fees_trace, decimals)


if __name__ == "__main__":
    with networks.ethereum.mainnet.use_default_provider():
        chain.provider.web3.provider._request_kwargs["timeout"] = 600
        cli()
