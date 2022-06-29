import json
import sys
from rich import print
from pydantic import BaseModel
from os.path import exists

path = sys.argv[1]

if exists(path):
    trace = json.load(open(path))["structLogs"]
else:
    from brownie import network, web3

    network.connect("mainnet")
    resp = web3.manager.request_blocking("debug_traceTransaction", [path])
    trace = resp["structLogs"]


pc = 21139  # 0.4.3
frame = next(x for x in trace if x["pc"] == pc)
# print(frame)

stack_map = {
    "gain": 3,
    "duration": 5,
    "management_fee": 6,
    "strategist_fee": 7,
    "performance_fee": 8,
    "total_fee": 9,
}

fees = {name: int(frame["stack"][pos], 16) for name, pos in stack_map.items()}

# print("stack")
# for i, item in enumerate(frame["stack"]):
#     print(i, int(item, 16) if len(item) != 42 else item)

print(fees)
