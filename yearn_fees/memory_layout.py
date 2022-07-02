from typing import List
from eth_utils import to_int

from evm_trace import TraceFrame
from rich.table import Table
from rich.console import Console

# fmt: off
# output by a modified vyper compiler
# https://gist.github.com/banteg/5e89aeeb2b1f5a5f982dc6d340c52b09
MEMORY_LAYOUT = {
    '0.3.0': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'governance_fee': 13, 'strategist_fee': 14, 'total_fee': 15}},
    '0.3.1': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'governance_fee': 13, 'strategist_fee': 14, 'total_fee': 15}},
    '0.3.2': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'governance_fee': 13, 'strategist_fee': 14, 'total_fee': 15}},
    '0.3.3': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'governance_fee': 13, 'strategist_fee': 14, 'total_fee': 15}},
    '0.3.4': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'governance_fee': 13, 'strategist_fee': 14, 'total_fee': 15}},
    '0.3.5': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'precisionFactor': 13, 'management_fee': 14, 'strategist_fee': 15, 'performance_fee': 16, 'total_fee': 17}},
    '0.4.0': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'duration': 13, 'management_fee': 14, 'strategist_fee': 15, 'performance_fee': 16, 'total_fee': 17}},
    '0.4.1': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'duration': 13, 'management_fee': 14, 'strategist_fee': 15, 'performance_fee': 16, 'total_fee': 17}},
    '0.4.2': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'duration': 13, 'management_fee': 14, 'strategist_fee': 15, 'performance_fee': 16, 'total_fee': 17}},
    '0.4.3': {'_assessFees': {'#internal_0': 12, 'strategy': 10, 'gain': 11, 'duration': 13, 'management_fee': 14, 'strategist_fee': 15, 'performance_fee': 16, 'total_fee': 17}},
}

# computed from combining source_map and ast outputs
PROGRAM_COUNTERS = {
    '0.3.0': [15333, 15334, 15370, 15371, 15407, 15412, 15434, 15439, 15464, 15469, 15520, 15565, 15570, 15618, 15623, 15650, 15655, 15666, 15684, 15689, 15712, 15769, 15770, 15822, 15845, 15850, 15867, 15872, 15955, 15956, 15992, 16015, 16094, 16095, 16127, 16128, 16133, 16134],
    '0.3.1': [15410, 15411, 15438, 15443, 15465, 15470, 15495, 15500, 15551, 15596, 15601, 15649, 15654, 15681, 15686, 15697, 15715, 15720, 15743, 15800, 15801, 15853, 15876, 15881, 15898, 15903, 15986, 15987, 16023, 16046, 16125, 16126, 16158, 16159, 16164, 16165],
    '0.3.2': [16977, 16978, 17005, 17010, 17032, 17037, 17062, 17067, 17118, 17163, 17168, 17216, 17221, 17248, 17253, 17264, 17282, 17287, 17310, 17367, 17368, 17420, 17443, 17448, 17465, 17470, 17553, 17554, 17590, 17613, 17692, 17693, 17725, 17726, 17731, 17732],
    '0.3.3': [19560, 19587, 19592, 19614, 19619, 19644, 19649, 19700, 19745, 19750, 19798, 19803, 19830, 19835, 19846, 19864, 19869, 19892, 19949, 19950, 20002, 20025, 20030, 20047, 20052, 20135, 20136, 20172, 20195, 20274, 20275, 20307, 20312],
    '0.4.3': [20207, 20257, 20262, 20284, 20289, 20299, 20312, 20313, 20371, 20376, 20384, 20389, 20404, 20409, 20435, 20440, 20465, 20470, 20548, 20553, 20596, 20601, 20640, 20645, 20666, 20671, 20696, 20705, 20717, 20782, 20783, 20843, 20866, 20871, 20888, 20893, 20984, 20985, 21029, 21052, 21139, 21140, 21180, 21195],
    '0.3.4': [19793, 19819, 19824, 19843, 19848, 19870, 19875, 19900, 19905, 19956, 20001, 20006, 20054, 20059, 20086, 20091, 20102, 20120, 20125, 20148, 20205, 20206, 20258, 20281, 20286, 20303, 20308, 20391, 20392, 20428, 20451, 20530, 20531, 20563, 20568],
    '0.3.5': [20315, 20396, 20401, 20409, 20414, 20429, 20434, 20479, 20484, 20506, 20511, 20536, 20541, 20563, 20568, 20607, 20612, 20641, 20664, 20669, 20717, 20722, 20749, 20754, 20787, 20792, 20817, 20822, 20849, 20854, 20865, 20883, 20888, 20909, 20914, 20939, 20963, 20968, 20987, 20992, 21004, 21016, 21081, 21082, 21142, 21165, 21170, 21196, 21201, 21218, 21223, 21239, 21244, 21335, 21336, 21380, 21403, 21490, 21491, 21531, 21546],
    '0.4.0': [20250, 20300, 20305, 20327, 20332, 20342, 20355, 20356, 20414, 20419, 20427, 20432, 20447, 20452, 20478, 20483, 20508, 20513, 20591, 20596, 20639, 20644, 20683, 20688, 20709, 20714, 20739, 20748, 20760, 20825, 20826, 20886, 20909, 20914, 20931, 20936, 21027, 21028, 21072, 21095, 21182, 21183, 21223, 21238],
    '0.4.1': [20272, 20322, 20327, 20349, 20354, 20364, 20377, 20378, 20436, 20441, 20449, 20454, 20469, 20474, 20500, 20505, 20530, 20535, 20613, 20618, 20661, 20666, 20705, 20710, 20731, 20736, 20761, 20770, 20782, 20847, 20848, 20908, 20931, 20936, 20953, 20958, 21049, 21050, 21094, 21117, 21204, 21205, 21245, 21260],
    '0.4.2': [20336, 20386, 20391, 20413, 20418, 20428, 20441, 20442, 20500, 20505, 20513, 20518, 20533, 20538, 20564, 20569, 20594, 20599, 20677, 20682, 20725, 20730, 20769, 20774, 20795, 20800, 20825, 20834, 20846, 20911, 20912, 20972, 20995, 21000, 21017, 21022, 21113, 21114, 21158, 21181, 21268, 21269, 21309, 21324],
}
# fmt: on


class MemoryLayout(dict):
    """
    Pivots a trace to (pc -> name -> memory value).
    """

    def __init__(self, trace: List[TraceFrame], version: str):
        self._memory_layout = MEMORY_LAYOUT[version]
        self._program_coutners = PROGRAM_COUNTERS[version]

        for frame in trace:
            if frame.pc not in self._program_coutners:
                continue
            self[frame.pc] = {"op": frame.op}
            for fn, positions in self._memory_layout.items():
                for name, pos in positions.items():
                    try:
                        self[frame.pc][name] = to_int(frame.memory[pos])
                    except IndexError:
                        self[frame.pc][name] = None

    def display(self, highlight_values=None, console=None):
        """
        Display memory layout as a table.
        """
        table = Table()
        table.add_column("pc", justify="right")
        table.add_column("op")

        for fn, positions in self._memory_layout.items():
            for name in positions:
                table.add_column(name, justify="right")

        for pc, layout in self.items():
            row = [f"{pc}", f'{layout["op"]}']
            for name, value in layout.items():
                if name == "op":
                    continue
                if value is None:
                    row.append(f"[dim](unallocated)")
                else:
                    style = f"[bold yellow]" if value in highlight_values else ""
                    row.append(f"{style}{value}")

            table.add_row(*row)

        if console is None:
            console = Console()

        console.print(table)
