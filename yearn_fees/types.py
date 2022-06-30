from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from rich import box
from rich.console import Console
from rich.table import Table
from eth_utils.humanize import humanize_seconds


class Fees(BaseModel):
    management_fee: int
    performance_fee: int
    strategist_fee: int
    gain: Optional[int]
    duration: Optional[int]

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
            table.add_row(
                name,
                format(Decimal(getattr(self, name)) / 10**decimals, f",.{decimals}f"),
                format(getattr(self, name) / self.gain, ".2%") if name != "gain" else "--",
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
            format(self.duration, ",d"),
            format(other.duration, ",d"),
            f"[green]✔︎" if self.duration == other.duration else "[red]✘",
        )

        console = Console()
        console.print(table)