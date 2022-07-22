import dataclasses
from bisect import bisect_right
from decimal import Decimal
from pickletools import string1
from typing import Dict, Iterator, List, Tuple

from ape.contracts import ContractLog
from eth_utils.humanize import humanize_seconds
from pydantic import BaseModel
from rich import box
from rich.console import Console
from rich.table import Table
from msgspec import Struct


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


class TraceFrame(Struct):
    """
    A modified version of `evm_trace.TraceFrame` with integers
    in stack/memory and no gas, gas_cost, depth, storage fields.
    """

    pc: int
    op: string1
    stack: List[int]
    memory: List[int]

    @classmethod
    def parse(cls, obj):
        return cls(
            pc=obj["pc"],
            op=obj["op"],
            stack=[int(v, 16) for v in obj["stack"]],
            memory=[int(v, 16) for v in obj["memory"]],
        )
