from typing import Dict, Iterator, List, Optional

import yaml
from eth_utils import to_int
from evm_trace import TraceFrame
from pydantic import BaseModel, Field
from semantic_version import Version

from yearn_fees.types import Fees


class TraceMapping(BaseModel):
    pc: int
    stack: Optional[Dict[str, int]] = Field(default_factory=dict)
    memory: Optional[Dict[str, int]] = Field(default_factory=dict)


def get_mapping(version):
    mappings = yaml.safe_load(open("vault-mapping.yml"))
    if version not in mappings:
        raise ValueError("unsupported version", version)

    return [TraceMapping.parse_obj(item) for item in mappings[version]]


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


def read_from_trace(trace: List[TraceFrame], mapping: List[TraceMapping]):
    """
    Recover data from trace frames using trace mappings.
    """
    data = {}
    for source in mapping:
        frame = next(frame for frame in trace if frame.pc == source.pc)
        for name, pos in source.stack.items():
            data[name] = to_int(frame.stack[pos])
        for name, pos in source.memory.items():
            data[name] = to_int(frame.memory[pos])

    return data


def fees_from_trace(trace: Iterator[TraceFrame], version: str):
    """
    Recover fee data from trace frames.
    """
    mapping = get_mapping(version)
    if version == "0.3.3":
        data = get_from_trace_033(trace)
    else:
        data = read_from_trace(trace, mapping)
    fees = Fees(**data)

    if Version(version) > Version("0.3.5"):
        if fees.total_fee > fees.gain:
            fees.management_fee = fees.gain - fees.performance_fee - fees.strategist_fee

    return fees
