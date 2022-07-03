from typing import List

from eth_utils import to_int
from evm_trace import TraceFrame
from semantic_version import Version

from yearn_fees.memory_layout import PROGRAM_COUNTERS, MemoryLayout
from yearn_fees.types import Fees
from yearn_fees.utils import version_from_report


def get_from_trace_033(trace):
    data = {}
    for frame in trace:
        if frame.pc == 19614:
            data.update(duration=to_int(frame.stack[2]))
        if frame.pc == 19835:
            data.update(
                management_fee=to_int(frame.memory[13]),
            )
        if frame.pc == 19846:
            data.update(performance_fee=to_int(frame.memory[13]) - data["management_fee"])
        if frame.pc == 20312:
            data.update(
                gain=to_int(frame.memory[11]),
                strategist_fee=to_int(frame.memory[14]),
            )

    return data


def split_trace(trace, reports):
    """
    Splits a trace into chunks covering _assessFees.
    """
    parts = []

    for report in reports:
        version = version_from_report(report)
        program_counters = PROGRAM_COUNTERS[version]
        jump_in = next(
            i
            for i, frame in enumerate(trace)
            if frame.pc == program_counters[0] and frame.op == "JUMPDEST"
        )
        jump_out = next(
            i + 1
            for i, frame in enumerate(trace[jump_in:], jump_in)
            if frame.pc == program_counters[-1] and frame.op == "JUMP"
        )
        parts.append(trace[jump_in:jump_out])
        trace = trace[jump_out:]

    return parts


def extract_from_stack(trace, pc, pos):
    frame = next(frame for frame in trace if frame.pc == pc)
    return to_int(frame.stack[pos])


def fees_from_trace(trace: List[TraceFrame], version: str):
    """
    Recover fees from trace frames. The trace must be already split.
    The program counters are derived from looking at `yearn-fees layout`.
    """
    layout = MemoryLayout(trace, version)
    if version == "0.4.3":
        data = layout[21195]
    elif version == "0.4.2":
        data = layout[21324]
    elif version == "0.3.5":
        data = layout[21546]
        data["duration"] = extract_from_stack(trace, 20516, 5)
    elif version == "0.3.3":
        data = layout[20312]
        data["management_fee"] = layout[19835]["governance_fee"]
        data["performance_fee"] = layout[19846]["governance_fee"] - data["management_fee"]
        data["duration"] = extract_from_stack(trace, 19620, 2)

    else:
        raise NotImplementedError("unsupported version", version)

    fees = Fees.parse_obj(data)

    if Version(version) > Version("0.3.5"):
        if fees.total_fee > fees.gain:
            fees.management_fee = fees.gain - fees.performance_fee - fees.strategist_fee

    return fees
