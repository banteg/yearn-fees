"""
yearn-fees layout 0.3.3
yearn-fees layout 0xabc..def

yearn-fees compare 0.4.3
yearn-fees compare 0xabc..def
"""
import json
import click
from ape import chain, networks

from yearn_fees.compare import compare_methods
from yearn_fees.memory_layout import MEMORY_LAYOUT
from yearn_fees.scanner import layout_tx
from yearn_fees.utils import get_sample_txs, get_trace
from eth_utils import to_int


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
        txs = get_sample_txs(version_or_tx, 3, 3)
        for tx in txs:
            layout_tx(tx)
    else:
        layout_tx(version_or_tx)


@cli.command(cls=MainnetCommand)
@click.argument("version_or_tx")
def compare(version_or_tx):
    if version_or_tx in MEMORY_LAYOUT:
        txs = get_sample_txs(version_or_tx, 3, 3)
        for tx in txs:
            compare_methods(tx)
    else:
        compare_methods(version_or_tx)


@cli.command(cls=MainnetCommand)
@click.argument("tx")
def dump_trace(tx):
    trace = get_trace(tx)
    data = []
    for frame in trace:
        item = frame.dict()
        item["stack"] = [to_int(x) for x in item["stack"]]
        item["memory"] = [to_int(x) for x in item["memory"]]
        item["storage"] = {to_int(x): to_int(y) for x, y in item["storage"].items()}
        data.append(item)

    path = f"traces/{tx}.json"
    with open(path, "wt") as f:
        json.dump(data, f, indent=2)
    
    print(path)


if __name__ == "__main__":
    cli()
