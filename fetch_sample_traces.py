import json
import random
from dataclasses import asdict
from operator import attrgetter
from pathlib import Path

from ape import Contract, chain, convert, networks
from ape.types import AddressType
from ethpm_types import HexBytes
from semantic_version import Version
from toolz import groupby, valmap


def json_encoder(value):
    if isinstance(value, bytes):
        return value.hex()


def main():
    program_counters = json.load(open("metadata/pcs_by_version.json"))

    with networks.ethereum.mainnet.use_default_provider():
        # we need regular dicts to save json
        chain.provider.web3.middleware_onion.remove("attrdict")
        chain.provider.web3.provider._request_kwargs["timeout"] = 600

        latest_registry = convert("v2.registry.ychad.eth", AddressType)
        registry = Contract(latest_registry)

        logs = registry.NewVault.range(12_000_000, chain.blocks.height, 1_000_000)
        vaults = groupby(attrgetter("api_version"), logs)
        print(valmap(len, vaults))

        for version in vaults:
            if Version(version) < Version("0.3.0"):
                continue
            vault = Contract(random.choice(vaults[version]).vault)
            logs = vault.StrategyReported.range(12_000_000, chain.blocks.height, 1_000_000)
            for log in logs:
                if log.gain == 0:
                    continue
                print(version, log.transaction_hash.hex())
                trace = chain.provider._make_request(
                    "debug_traceTransaction", [log.transaction_hash.hex()]
                )
                frames = [
                    frame
                    for frame in trace["structLogs"]
                    if str(frame["pc"]) in program_counters[f"v{version}"]
                    #and frame["op"] == "JUMP"  # more likely to be the end of a method
                ]
                for frame in frames:
                    frame["stack_int"] = [int(item, 16) for item in frame["stack"]]
                    frame["memory_int"] = [int(f"0x{item}", 16) for item in frame["memory"]]
                # specifying height is an aspirational api, it requires patching ape
                a = vault.strategies(log.strategy, height=log.block_number - 1)
                b = vault.strategies(log.strategy, height=log.block_number)
                output = {
                    "frames": frames,
                    "event": asdict(log),
                    "strategy": b.__dict__,
                    "duration": b.lastReport - a.lastReport,
                }
                path = Path("traces") / f"v{version}_{log.transaction_hash.hex()}.json"
                path.write_text(json.dumps(output, default=json_encoder, indent=2))
                break


if __name__ == "__main__":
    main()
