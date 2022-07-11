import dataclasses
from bisect import bisect_right
from decimal import Decimal
from typing import Dict, Iterator, List, Tuple

from ape.contracts import ContractLog
from eth_utils.humanize import humanize_seconds
from pydantic import BaseModel
from rich import box
from rich.console import Console
from rich.table import Table


def asof(stack, needle):
    keys = sorted(stack)
    index = bisect_right(keys, needle) - 1
    return stack[keys[index]]


class Fees(BaseModel):
    management_fee: int = 0
    performance_fee: int = 0
    strategist_fee: int = 0
    gain: int = 0
    duration: int = None

    @property
    def governance_fee(self):
        return self.management_fee + self.performance_fee

    @property
    def total_fee(self):
        return self.management_fee + self.performance_fee + self.strategist_fee

    def as_table(self, decimals, title=None):
        table = Table(title=title, box=box.SIMPLE)
        table.add_column("name")
        table.add_column("value", justify="right")
        table.add_column("% gain", justify="right")

        for name in ["management_fee", "performance_fee", "strategist_fee", "total_fee", "gain"]:
            percentage = getattr(self, name) / self.gain if self.gain else 0
            table.add_row(
                name,
                format(Decimal(getattr(self, name)) / 10**decimals, f",.{decimals}f"),
                format(percentage, ".2%") if name != "gain" else "",
            )
        if self.duration is not None:
            table.add_row("duration", format(self.duration, ",d"), humanize_seconds(self.duration))

        console = Console()
        console.print(table)


class FeeConfiguration(BaseModel):
    management_fee: int
    performance_fee: int
    strategist_fee: int

    def __str__(self):
        return " ".join(f"{name}={value / 10_000:.2%}" for name, value in self)


LogPosition = Tuple[int, int]  # block_number, log_index


class FeeHistory(BaseModel):
    management_fee: Dict[LogPosition, int]
    performance_fee: Dict[LogPosition, int]
    strategist_fee: Dict[str, Dict[LogPosition, int]]

    def at_pos(self, pos: LogPosition, strategy: str):
        return FeeConfiguration(
            management_fee=asof(self.management_fee, pos),
            performance_fee=asof(self.performance_fee, pos),
            strategist_fee=asof(self.strategist_fee[strategy], pos),
        )

    def at_report(self, report: ContractLog):
        return self.at_pos((report.block_number, report.log_index), report.strategy)


@dataclasses.dataclass()
class TraceFrame:
    """
    A modified version of `evm_trace.TraceFrame` with integers
    in stack/memory and no gas, gas_cost, depth, storage fields.
    """

    pc: int
    op: str
    stack: List[int]
    memory: List[int]

    def __post_init__(self):
        self.stack = [int(v, 16) for v in self.stack]
        self.memory = [int(v, 16) for v in self.memory]

    @classmethod
    def parse_obj(cls, obj):
        class_fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in obj.items() if k in class_fields})


class Trace(list):
    """
    `Trace.parse_obj(trace['structLogs'])`
    """

    @classmethod
    def parse_obj(cls, obj) -> List[TraceFrame]:
        return cls(TraceFrame.parse_obj(item) for item in obj)

    def scan(self, pc) -> Iterator[TraceFrame]:
        for frame in self:
            if frame.pc == pc:
                yield frame

    def dict(self):
        return [dataclasses.asdict(frame) for frame in self]
