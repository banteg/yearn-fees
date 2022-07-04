from typing import List

from ape.contracts import ContractLog
from semantic_version import Version

from yearn_fees import utils
from yearn_fees.memory_layout import EARLY_EXIT, PROGRAM_COUNTERS, MemoryLayout
from yearn_fees.types import Fees, Trace


def split_trace(trace: Trace, reports: List[ContractLog]) -> List[Trace]:
    """
    Splits a trace into chunks covering _assessFees.
    """
    parts = []

    for report in reports:
        version = utils.version_from_report(report)
        program_counters = PROGRAM_COUNTERS[version]
        jump_in = next(
            i
            for i, frame in enumerate(trace)
            if frame.pc == program_counters[0] and frame.op == "JUMPDEST"
        )
        out_pcs = [program_counters[-1]]
        if version in EARLY_EXIT:
            out_pcs.append(EARLY_EXIT[version])
        jump_out = next(
            i + 1
            for i, frame in enumerate(trace[jump_in:], jump_in)
            if frame.pc in out_pcs and frame.op == "JUMP"
        )
        parts.append(trace[jump_in:jump_out])
        trace = trace[jump_out:]

    return parts


def fees_from_trace(trace: Trace, version: str) -> Fees:
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
            data["management_fee"] = 0
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
