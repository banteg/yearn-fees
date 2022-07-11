import json
from typing import List, Optional

from ape import chain, config, networks
from ape_foundry.providers import FoundryForkConfig
from ape_vyper import compiler
from ethpm_types import ContractType
from rich import print

from yearn_fees import compile_sources, utils
from yearn_fees.cache import cache
from yearn_fees.types import Fees


class SourceContractType(ContractType):
    source: str
    code: Optional[str]

    @classmethod
    def from_file(cls, path):
        return cls(source=open(path).read())

    def __eq__(self, other):
        assert isinstance(other, SourceContractType)
        return self.source == other.source


def compile_version(version):
    key = f"sources:{version}"
    source_path = f"sources/Vault_v{version}.vy"
    latest_source = SourceContractType.from_file(source_path)
    cached_source = cache.get(key)
    if cached_source:
        if cached_source == latest_source:
            return cached_source

    print(f"[yellow]compiling [bold]{source_path}[/]")
    pragma_spec = compiler.get_pragma_spec(latest_source.source)
    vyper_version = compile_sources.install_vyper(pragma_spec)
    vyper_binary = compile_sources.get_executable(vyper_version)
    formats = ["bytecode_runtime", "abi"]
    stdoutdata, stderrdata, command, proc = compile_sources.vyper_wrapper(
        vyper_binary=vyper_binary,
        source_files=source_path,
        f=",".join(formats),
    )
    code, abi = stdoutdata.splitlines()

    source = SourceContractType(
        source=latest_source.source,
        code=code,
        abi=json.loads(abi),
    )
    cache[key] = source
    return source


def fork_tx(tx) -> List[Fees]:
    receipt = chain.provider.get_transaction(tx)
    timestamp = chain.blocks[receipt.block_number].timestamp
    block_transactions = chain.blocks[receipt.block_number].transactions
    tx_index = next(i for i, x in enumerate(block_transactions) if x.txn_hash.hex() == tx)

    reports = utils.reports_from_tx(tx)
    versions = [utils.version_from_report(r) for r in reports]
    results = []

    # fork at a previous block
    config._plugin_configs["foundry"].port = 7545
    config._plugin_configs["foundry"].fork = {
        "ethereum": {
            "mainnet": FoundryForkConfig(
                upstream_provider="geth",
                block_number=receipt.block_number - 1,
            )
        }
    }

    with networks.ethereum.mainnet_fork.use_provider("foundry"):
        contracts = {}
        # replace runtime bytecode
        for report, version in zip(reports, versions):
            contracts[version] = compile_version(version)
            chain.provider._make_request(
                "anvil_setCode", [report.contract_address, contracts[version].code]
            )

        # disable automine so all transactions end up in the same block
        chain.provider._make_request("evm_setAutomine", [False])
        chain.pending_timestamp = timestamp

        # replay the block till our transaction
        for txn in block_transactions[:tx_index]:
            chain.provider.web3.eth.send_raw_transaction(txn.serialize_transaction())

        # replay tx with higher gas limit to accommodate logs
        replay_tx = block_transactions[tx_index]
        replay_tx.gas_limit += 100_000
        replay_tx.chain_id = chain.chain_id  # ape bug?
        chain.provider.unlock_account(replay_tx.sender)
        replay_tx_hash = chain.provider.web3.eth.send_transaction(replay_tx.dict())

        # advance one block and make sure we at the original height and timestamp
        chain.mine()
        assert chain.blocks.head.timestamp == timestamp
        assert chain.blocks.height == receipt.block_number

        fork_receipt = chain.provider.web3.eth.get_transaction_receipt(replay_tx_hash)
        assert fork_receipt["status"], "tx failed"

        for report, version in zip(reports, versions):
            event = next(
                chain.provider.network.ecosystem.decode_logs(
                    contracts[version].events["Fees"],
                    [
                        log
                        for log in fork_receipt["logs"]
                        if log["address"] == report.contract_address
                    ],
                )
            )
            results.append(Fees.parse_obj(event.event_arguments))

    return results
