#!/usr/bin/env python3
"""Minimal SunSpec Modbus TCP simulator for SolarEdge-Exporter.

Serves a SolarEdge-shaped common block at holding register 40000 and a
single-phase inverter model (DID 101) at 40069 — enough for
dave92082/SolarEdge-Exporter to start and export AC_Power / DC_Power /
SunSpec_DID. No meter blocks (v1).
"""

from __future__ import annotations

import logging

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartTcpServer

LOG = logging.getLogger("sunspec-sim")

COMMON_BASE = 40000
INVERTER_BASE = 40069
SUNSPEC_ID = 0x53756E53  # "SunS"


def _u16(value: int) -> int:
    return value & 0xFFFF


def _i16(value: int) -> int:
    return value & 0xFFFF


def _pad_string(text: str, n_bytes: int) -> list[int]:
    raw = text.encode("ascii", errors="ignore")[:n_bytes].ljust(n_bytes, b"\x00")
    return [_u16((raw[i] << 8) | raw[i + 1]) for i in range(0, n_bytes, 2)]


def build_common_block() -> list[int]:
    regs: list[int] = []
    regs.append(_u16(SUNSPEC_ID >> 16))
    regs.append(_u16(SUNSPEC_ID & 0xFFFF))
    regs.append(1)
    regs.append(65)
    regs.extend(_pad_string("SolarEdge", 32))
    regs.extend(_pad_string("SE5000-SIM", 32))
    regs.extend(_pad_string("0003.2221", 32))
    regs.extend(_pad_string("SIM00001", 32))
    regs.append(1)
    regs.append(0)
    assert len(regs) == 70, len(regs)
    return regs


def build_inverter_block(ac_power: int = 2500, dc_power: int = 2600) -> list[int]:
    regs: list[int] = []
    regs.append(101)
    regs.append(50)
    regs.append(100)
    regs.append(100)
    regs.append(0)
    regs.append(0)
    regs.append(_i16(-1))
    regs.append(0)
    regs.append(0)
    regs.append(0)
    regs.append(2400)
    regs.append(0)
    regs.append(0)
    regs.append(_i16(-1))
    regs.append(_i16(ac_power))
    regs.append(0)
    regs.append(600)
    regs.append(_i16(-1))
    regs.append(_i16(ac_power))
    regs.append(0)
    regs.append(0)
    regs.append(0)
    regs.append(1000)
    regs.append(_i16(-3))
    energy = 12_500_000
    regs.append(_u16((energy >> 16) & 0xFFFF))
    regs.append(_u16(energy & 0xFFFF))
    regs.append(0)
    regs.append(80)
    regs.append(_i16(-1))
    regs.append(3250)
    regs.append(_i16(-1))
    regs.append(_i16(dc_power))
    regs.append(0)
    regs.append(0)
    regs.append(_i16(42))
    regs.append(0)
    regs.append(0)
    regs.append(0)
    regs.append(4)
    regs.append(0)
    assert len(regs) == 40, len(regs)
    return regs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    size = 41000
    holding = [0] * size
    common = build_common_block()
    inverter = build_inverter_block()
    holding[COMMON_BASE : COMMON_BASE + len(common)] = common
    holding[INVERTER_BASE : INVERTER_BASE + len(inverter)] = inverter

    store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, holding), zero_mode=True)
    context = ModbusServerContext(slaves=store, single=True)

    LOG.info(
        "SunSpec simulator listening on 0.0.0.0:502 (common@%d, inverter@%d)",
        COMMON_BASE,
        INVERTER_BASE,
    )
    StartTcpServer(context=context, address=("0.0.0.0", 502))


if __name__ == "__main__":
    main()
