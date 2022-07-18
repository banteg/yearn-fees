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

from yearn_fees.utils import fetch_all_reports


def stream_trace(tx):
    """
    Measures both compressed and uncompressed trace response size.

    Use to debug https://github.com/ledgerwatch/erigon/issues/4637
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": "debug_traceTransaction", "params": [tx]}
    bytes_raw = 0
    bytes_data = 0
    d = zlib.decompressobj(zlib.MAX_WBITS | 16)
    t0 = perf_counter()

    with httpx.stream("POST", "http://127.0.0.1:8545", json=payload) as r:
        assert r.headers["content-encoding"] == "gzip", "enable `--http.compression` for erigon"
        for chunk in r.iter_raw():
            bytes_raw += len(chunk)
            chunk_fat = d.decompress(chunk)
            bytes_data += len(chunk_fat)

    return {
        "tx": tx,
        "bytes_raw": bytes_raw,
        "bytes_data": bytes_data,
        "elapsed": perf_counter() - t0,
    }


def measure_dropped():
    with networks.parse_network_choice(":mainnet:geth"):
        reports = fetch_all_reports()

    txs = list(unique(log.transaction_hash for log in reports))
    blocks = {log.transaction_hash: log.block_number for log in reports}

    print(f"{len(txs)} txs")
    f = open("dropped-trace-sizes.jsonl", "wt")

    console = Console()
    cluster = LocalCluster(n_workers=32)
    client = Client(cluster)
    print(client.dashboard_link)

    with Progress(console=console) as progress:
        task = progress.add_task("measure", total=len(txs))
        for tx, fut in zip(txs, client.map(stream_trace, txs)):
            res = fut.result()
            res['block_number'] = blocks[tx]
            f.write(json.dumps(res) + "\n")
            f.flush()
            progress.update(task, advance=1)
            console.log(res)

    f.close()


if __name__ == "__main__":
    if len(sys.argv) == 2:
        res = stream_trace(sys.argv[1])
        print(res)
    else:
        measure_dropped()
