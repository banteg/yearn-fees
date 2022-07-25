import json
import sys
import zlib
from time import perf_counter

import httpx
from ape import networks
from dask.distributed import Client, LocalCluster
from rich.console import Console
from rich.progress import Progress
from toolz import unique
from tqdm import tqdm
from ape import chain, networks

from typer import Typer
from yearn_fees.utils import fetch_all_reports

app = Typer()


@app.command("measure")
def stream_trace(tx):
    """
    Measures both compressed and uncompressed trace response size.

    Use to debug https://github.com/ledgerwatch/erigon/issues/4637
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": "debug_traceTransaction", "params": [tx]}
    headers = {"accept-encoding": ""}
    bytes_wire = 0
    frames = 0
    t0 = perf_counter()
    bar_wire = tqdm(desc="wire", unit="B", unit_scale=True, unit_divisor=1024)
    bar_frames = tqdm(desc="frames", unit="frames")

    with httpx.stream("POST", "http://127.0.0.1:8545", json=payload, headers=headers) as r:
        for chunk in r.iter_raw():
            new_bytes = len(chunk)
            bytes_wire += new_bytes
            new_frames = chunk.count(b'{"pc":')
            frames += new_frames
            bar_wire.update(new_bytes)
            bar_frames.update(new_frames)

    res = {
        "tx": tx,
        "bytes_wire": bytes_wire,
        "frames": frames,
        "elapsed": perf_counter() - t0,
    }
    print(res)
    return res


@app.command("dropped")
def measure_dropped():
    with networks.parse_network_choice(":mainnet:geth"):
        reports = fetch_all_reports()

    txs = list(unique(log.transaction_hash for log in reports))
    blocks = {log.transaction_hash: log.block_number for log in reports}

    print(f"{len(txs)} txs")
    f = open("dropped-trace-sizes.jsonl", "wt")

    console = Console()
    cluster = LocalCluster(n_workers=16)
    client = Client(cluster)
    print(client.dashboard_link)

    with Progress(console=console) as progress:
        task = progress.add_task("measure", total=len(txs))
        for tx, fut in zip(txs, client.map(stream_trace, txs)):
            res = fut.result()
            res["block_number"] = blocks[tx]
            f.write(json.dumps(res) + "\n")
            f.flush()
            progress.update(task, advance=1)
            console.log(res)

    f.close()


if __name__ == "__main__":
    with networks.ethereum.mainnet.use_default_provider():
        app()
