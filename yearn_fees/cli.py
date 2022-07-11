"""
yearn-fees layout 0.3.3
yearn-fees layout 0xabc..def

yearn-fees compare 0.4.3
yearn-fees compare 0xabc..def
"""
import json

import click
from ape import chain, networks
from rich import print

from yearn_fees import fork, indexer, scanner, utils
from yearn_fees.compare import compare_methods
from yearn_fees.memory_layout import MEMORY_LAYOUT
from yearn_fees.utils import get_sample_txs, get_trace


class MainnetCommand(click.Command):
    def invoke(self, ctx):
        with networks.ethereum.mainnet.use_default_provider():
            chain.provider.web3.provider._request_kwargs["timeout"] = 600
            super().invoke(ctx)


@click.group()
def cli():
    pass


@cli.command(cls=MainnetCommand)
@click.argument("version_or_tx")
def layout(version_or_tx):
    if version_or_tx in MEMORY_LAYOUT:
        txs = get_sample_txs(version_or_tx, 10, 5)
        for tx in txs:
            scanner.layout_tx(tx, only_version=version_or_tx)
    else:
        scanner.layout_tx(version_or_tx)


@cli.command(cls=MainnetCommand)
@click.argument("version_or_tx")
def compare(version_or_tx):
    if version_or_tx in MEMORY_LAYOUT:
        txs = get_sample_txs(version_or_tx, 10, 5)
        for tx in txs:
            compare_methods(tx, only_version=version_or_tx)
    else:
        compare_methods(version_or_tx)


@cli.command(cls=MainnetCommand)
@click.argument("tx")
def dump_trace(tx):
    trace = get_trace(tx)

    path = f"traces/{tx}.json"
    with open(path, "wt") as f:
        json.dump(trace.dict(), f, indent=2)

    print(path)


@cli.command(cls=MainnetCommand)
def index():
    indexer.start()


@cli.command("fork", cls=MainnetCommand)
@click.argument("tx")
def fork_version(tx):
    reports = utils.reports_from_tx(tx)
    fees = fork.fork_tx(tx)
    for fee, report in zip(fees, reports):
        decimals = utils.get_decimals(report.contract_address)
        version = utils.version_from_report(report)
        fee.as_table(decimals, title=version)
    fork.fork_tx(tx)


@cli.command(cls=MainnetCommand)
@click.argument("version_or_tx")
@click.option("--samples", type=click.IntRange(min=1), default=10)
def find_duration(version_or_tx, samples):
    if version_or_tx in MEMORY_LAYOUT:
        version = version_or_tx
        scanner.find_duration(version, samples=samples)
    else:
        tx = version_or_tx
        scanner.find_duration_from_tx(tx)


@cli.command(cls=MainnetCommand)
def dropped():
    from yearn_fees.compare import compare_methods
    from rich.progress import track
    import json
    from os.path import exists

    dropped = open('dropped-txs.csv').read().splitlines()
    for tx in track(dropped):
        path = f'traces/{tx}.json'
        if exists(path):
            continue
        data = compare_methods(tx)
        data = [{key: value.dict() for key, value in item.items()} for item in data]
        with open(path, 'wt') as f:
            json.dump(data, f, default=str, indent=2)


if __name__ == "__main__":
    cli()
