import dataclasses
from typing import Iterator, List

from ape import Contract
from ape.contracts import ContractLog
from eth_abi import decode_single
from eth_utils import keccak
from ethpm_types import ContractInstance
from semantic_version import Version

from yearn_fees import utils
from yearn_fees.memory_layout import PROGRAM_COUNTERS, MemoryLayout
from yearn_fees.types import Fees, TraceFrame


@dataclasses.dataclass
class ReportMetadata:
    vault: ContractInstance
    version: str
    topic: int
    jumpdest: int

    @classmethod
    def from_report(cls, report):
        vault = Contract(report.contract_address)
        version = utils.version_from_report(report)

        return cls(
            vault=vault,
            version=version,
            topic=decode_single("uint256", keccak(text=vault.StrategyReported.abi.selector)),
            jumpdest=PROGRAM_COUNTERS[version][0],
        )


def split_trace(trace: Iterator[TraceFrame], reports: List[ContractLog]) -> List[List[TraceFrame]]:
    """
    Splits a trace into chunks covering _assessFees.
    """
    parts = []
    # we can skip an index if it's an iterator
    report_metadata = (ReportMetadata.from_report(report) for report in reports)
    meta = next(report_metadata)
    start = None

    part = []
    for i, frame in enumerate(trace):
        # for start we find a JUMPDEST where we enter _assessFees
        if start is None and frame.op == "JUMPDEST" and frame.pc == meta.jumpdest:
            start = i

        if start:
            part.append(frame)

        # for end this method is not reliable, since the function can terminate early
        # instead, we look for the StrategyReported event
        if start and frame.op == "LOG2" and meta.topic in frame.stack:
            parts.append(part)
            start = None
            try:
                meta = next(report_metadata)
            except StopIteration:
                break

    return parts


def fees_from_trace(trace: List[TraceFrame], version: str) -> Fees:
    """
    Recover fees from trace frames. The trace must be already split.
    The program counters are carefully selected from `yearn-fees layout`.
    """
    layout = MemoryLayout(trace, version)

    if version == "0.4.3":
        try:
            data = layout[21195]
        except KeyError:
            data = {"duration": layout[20284]["duration"]}

    elif version == "0.4.2":
        try:
            data = layout[21324]
        except KeyError:
            data = {"duration": layout[20441]["duration"]}

    elif version == "0.3.5":
        data = layout[21546]
        # no accurate way to get duration for 0.3.5

    elif version == "0.3.3":
        data = layout[20312]
        try:
            data["management_fee"] = layout[19835]["governance_fee"]
            data["performance_fee"] = layout[19846]["governance_fee"] - data["management_fee"]
        except KeyError:
            data["management_fee"] = data["governance_fee"]
            data["performance_fee"] = 0
        # no accurate way to get duration for 0.3.3

    elif version == "0.3.2":
        data = layout[17731]
        try:
            data["management_fee"] = layout[17253]["governance_fee"]
            data["performance_fee"] = layout[17264]["governance_fee"] - data["management_fee"]
        except KeyError:
            data["management_fee"] = data["governance_fee"]
            data["performance_fee"] = 0
        # no accurate way to get duration for 0.3.2

    elif version == "0.3.1":
        data = layout[16164]
        try:
            data["management_fee"] = layout[15686]["governance_fee"]
            data["performance_fee"] = layout[15697]["governance_fee"] - data["management_fee"]
        except KeyError:
            data["management_fee"] = data["governance_fee"]
            data["performance_fee"] = 0
        # no accurate way to get duration for 0.3.1

    elif version == "0.3.0":
        data = layout[16133]
        try:
            data["management_fee"] = layout[15655]["governance_fee"]
            data["performance_fee"] = layout[15666]["governance_fee"] - data["management_fee"]
        except KeyError:
            data["management_fee"] = data["governance_fee"]
            data["performance_fee"] = 0
        # no accurate way to get duration for 0.3.0

    else:
        raise NotImplementedError("unsupported version", version)

    fees = Fees.parse_obj(data)

    if Version(version) > Version("0.3.5"):
        if fees.total_fee > fees.gain:
            fees.management_fee = fees.gain - fees.performance_fee - fees.strategist_fee

    return fees
