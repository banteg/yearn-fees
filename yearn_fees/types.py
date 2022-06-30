from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from rich import box
from rich.console import Console
from rich.table import Table


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

    def as_table(self, decimals):
        table = Table(box=box.SIMPLE)
        table.add_column("name")
        table.add_column("value", justify="right")
        table.add_column("% gain", justify="right")

        for name in ["management_fee", "performance_fee", "strategist_fee", "total_fee", "gain"]:
            table.add_row(
                name,
                format(Decimal(getattr(self, name)) / 10**decimals, f",.{decimals}f"),
                format(getattr(self, name) / self.gain, ".2%") if name != "gain" else "--",
            )

        console = Console()
        console.print(table)
