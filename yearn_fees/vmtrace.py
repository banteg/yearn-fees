# ported from https://docs.rs/web3/latest/web3/types/struct.VMTrace.html
from __future__ import annotations

from typing import Any, List, Optional, Type

import msgspec
from eth_utils import decode_hex, encode_hex
from hexbytes import HexBytes


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


decoder = msgspec.json.Decoder(VMTrace, dec_hook=dec_hook)
encoder = msgspec.json.Encoder(enc_hook=enc_hook)
