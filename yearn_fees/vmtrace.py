"""
Replay vmTrace and recover memory and stack values at each step of execution.

References:
    https://docs.rs/web3/latest/web3/types/struct.VMTrace.html
    https://github.com/ledgerwatch/erigon/blob/devel/core/vm/instructions.go
    https://github.com/ethereumbook/ethereumbook/blob/develop/13evm.asciidoc
    https://medium.com/coinmonks/ethereum-virtual-machine-evm-how-does-it-work-part-2-4198401d2a11
    https://hackernoon.com/getting-deep-into-evm-how-ethereum-works-backstage-ac7efa1f0015
    https://github.com/ledgerwatch/erigon/blob/devel/cmd/rpcdaemon/commands/trace_adhoc.go#L460
"""

from __future__ import annotations

from typing import Any, List, Optional, Type

import msgspec
import rich
from eth.vm.memory import Memory
from eth.vm.stack import Stack
from eth_abi import decode_single, encode_single
from eth_utils import decode_hex, encode_hex
from hexbytes import HexBytes


# fmt: off
# opcodes grouped by number of items they pop from the stack
POPCODES = {
    1: ["EXTCODEHASH", "ISZERO", "NOT", "BALANCE", "CALLDATALOAD", "EXTCODESIZE", "BLOCKHASH", "POP", "MLOAD", "SLOAD", "JUMP", "SELFDESTRUCT"],
    2: ["SHL", "SHR", "SAR", "REVERT", "ADD", "MUL", "SUB", "DIV", "SDIV", "MOD", "SMOD", "EXP", "SIGNEXTEND", "LT", "GT", "SLT", "SGT", "EQ", "AND", "XOR", "OR", "BYTE", "SHA3", "MSTORE", "MSTORE8", "SSTORE", "JUMPI", "LOG0", "RETURN"],
    3: ["RETURNDATACOPY", "ADDMOD", "MULMOD", "CALLDATACOPY", "CODECOPY", "CREATE"],
    4: ["CREATE2", "EXTCODECOPY"],
    6: ["STATICCALL", "DELEGATECALL"],
    7: ["CALL", "CALLCODE"]
}
# fmt: on
POPCODES = {op: n for n in POPCODES for op in POPCODES[n]}
POPCODES.update({f"LOG{n}": n + 2 for n in range(1, 5)})
POPCODES.update({f"SWAP{i}": i + 1 for i in range(1, 17)})
POPCODES.update({f"DUP{i}": i for i in range(1, 17)})


class uint256(int):
    pass


class VMTrace(msgspec.Struct):
    code: HexBytes
    """The code to be executed."""
    ops: List[VMOperation]
    """The operations executed."""


class VMOperation(msgspec.Struct):
    pc: int
    """The program counter."""
    cost: int
    """The gas cost for this instruction."""
    ex: Optional[VMExecutedOperation]
    """Information concerning the execution of the operation."""
    sub: Optional[VMTrace]
    """Subordinate trace of the CALL/CREATE if applicable."""
    op: str
    """Opcode that is being called."""
    idx: str
    """Index in the tree."""


class VMExecutedOperation(msgspec.Struct):
    used: int
    """The total gas used."""
    push: List[uint256]
    """The stack item placed, if any."""
    mem: Optional[MemoryDiff]
    """If altered, the memory delta."""
    store: Optional[StorageDiff]
    """The altered storage value, if any."""


class MemoryDiff(msgspec.Struct):
    off: int
    """Offset into memory the change begins."""
    data: HexBytes
    """The changed data."""


class StorageDiff(msgspec.Struct):
    key: uint256
    """Which key in storage is changed."""
    val: uint256
    """What the value has been changed to."""


def enc_hook(obj: Any) -> Any:
    """Given an object that msgspec doesn't know how to serialize by
    default, convert it into an object that it does know how to
    serialize"""
    if type is uint256:
        return hex(obj)
    if type is HexBytes:
        return encode_hex(obj)


def dec_hook(type: Type, obj: Any) -> Any:
    """Given a type in a schema, convert ``obj`` (composed of natively
    supported objects) into an object of type ``type``"""
    if type is uint256:
        return uint256(obj, 16)
    if type is HexBytes:
        return HexBytes(decode_hex(obj))


def display(vm: VMTrace, offset=0, compare=None, call_target=None):
    memory = Memory()
    stack = Stack()

    if call_target:
        rich.print(f"[bold red]{call_target}")
        call_target = None

    def extend_memory(offset, size):
        memory.extend(offset, size)

    def write_memory(offset, data):
        extend_memory(offset, len(data))
        memory.write(offset, len(data), data)

    for op in vm.ops:
        print("-" * 80)
        rich.print(f"{hex(op.pc):>4} ({op.pc})| {op.op}")
        rich.print(f"[yellow]stack ({len(stack.values)} values)")
        for i, (t, v) in enumerate(reversed(stack.values)):
            val = encode_single("uint256", v)
            print(f"{hex(i)[2:]:>4}| {val.hex()}")

        rich.print(f"[magenta]memory ({len(memory) // 32} words)")
        for i in range(0, len(memory), 32):
            mem = memory.read_bytes(i * 32, 32).ljust(32, b"\x00")
            print(f"{hex(i)[2:]:>4}| {mem.hex()}")

        # rich.print(f'VMTRACE {op}')
        if compare:
            other = next(compare)
            # rich.print(f'DEBUGTRACE {other}')
            assert op.op == other.op and op.pc == other.pc
            # rich.print(f"[bold green]compare memory")

            a = [
                memory.read_bytes(i * 32, 32).ljust(32, b"\x00") for i, _ in enumerate(other.memory)
            ]
            b = other.memory[:]
            if a != b:
                rich.print(f"[red]MEMORY MISMATCH AT[/] {op}")
                rich.print(f"a: {reversed(a)}")
                rich.print(f"b: {reversed(b)}")
                exit(1)

            # rich.print(f"[bold green]compare stack")
            a = [i[1] for i in stack.values]
            b = [int(i.hex(), 16) for i in other.stack]
            if a != b:
                rich.print(f"[red]STACK MISMATCH AT[/] {op}")
                rich.print(f"a: {a}")
                rich.print(f"b: {b}")
                exit(1)

        if op.op in ["CALL", "DELEGATECALL", "STATICCALL"]:
            call_target = decode_single("address", encode_single("uint256", stack.values[-2][1]))
            rich.print(f"[bold yellow]{op.op} ADDR {call_target}")
            rich.print(f'{"    " * offset}pc={op.pc} op={op.op} off_w={op.ex}')

        # stack
        if num_pop := POPCODES.get(op.op):
            stack.pop_ints(num_pop)

        for item in op.ex.push:
            stack.push_int(item)

        # memory
        if op.ex.mem:
            write_memory(op.ex.mem.off, op.ex.mem.data)

        # subcalls
        if op.sub:
            rich.print(f"[bold red]{op.op} has {len(op.sub.ops)} subtraces")
            display(op.sub, offset=offset + 1, compare=compare, call_target=call_target)


decoder = msgspec.json.Decoder(VMTrace, dec_hook=dec_hook)
encoder = msgspec.json.Encoder(enc_hook=enc_hook)
