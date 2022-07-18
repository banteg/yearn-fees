import sys
import zlib

import httpx
from time import perf_counter


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


if __name__ == "__main__":
    res = stream_trace(sys.argv[1])
    print(res)
