from decimal import Decimal
from typing import Dict, Optional, Tuple

from pydantic import BaseModel
from rich import box
from rich.console import Console
from rich.table import Table
from eth_utils.humanize import humanize_seconds
from toolz import last
from ape.contracts import ContractLog


class AsofDict(dict):
    """
    Allows you to get the closest previous item.

    >>> AsofDict({1: 'a', 3: 'b'})[2]
    'a'
    """

    def __getitem__(self, key):
        return super().__getitem__(last(item for item in sorted(self) if item <= key))


class Fees(BaseModel):
    management_fee: int = 0
    performance_fee: int = 0
    strategist_fee: int = 0
    gain: int = 0
    duration: int = 0

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
        if self.duration:
            table.add_row("duration", format(self.duration, ",d"), humanize_seconds(self.duration))

        console = Console()
        console.print(table)

    def compare(self, other, decimals):
        assert isinstance(other, Fees), "can only compare to Fees"
        table = Table(box=box.SIMPLE)
        table.add_column("name")
        table.add_column("left", justify="right")
        table.add_column("right", justify="right")
        table.add_column("test")

        for name in ["management_fee", "performance_fee", "strategist_fee", "total_fee", "gain"]:
            table.add_row(
                name,
                format(Decimal(getattr(self, name)) / 10**decimals, f",.{decimals}f"),
                format(Decimal(getattr(other, name)) / 10**decimals, f",.{decimals}f"),
                f"[green]✔︎" if getattr(self, name) == getattr(other, name) else "[red]✘",
            )
        table.add_row(
            "duration",
            format(self.duration, ",d") if self.duration else "--",
            format(other.duration, ",d") if other.duration else "--",
            f"[green]✔︎" if self.duration == other.duration else "[red]✘",
        )

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
    management_fee: AsofDict[LogPosition, int]
    performance_fee: AsofDict[LogPosition, int]
    strategist_fee: Dict[str, AsofDict[LogPosition, int]]

    def at_pos(self, pos: LogPosition, strategy: str):
        return FeeConfiguration(
            management_fee=self.management_fee[pos],
            performance_fee=self.performance_fee[pos],
            strategist_fee=self.strategist_fee[strategy][pos],
        )

    def at_report(self, report: ContractLog):
        return self.at_pos((report.block_number, report.log_index), report.strategy)
