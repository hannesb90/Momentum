"""Minimal BIFF8-lasare — stdlib only. Racker for att lasa celler ur en legacy .xls.

Hanterar: BOUNDSHEET, SST (med CONTINUE-delade strangar), LABELSST, LABEL,
RK, MULRK, NUMBER, BLANK/MULBLANK. Returnerar per blad en dict {(rad,kol): varde}.
"""
from __future__ import annotations
import struct

BOF, EOF_, BOUNDSHEET, SST, CONTINUE = 0x0809, 0x000A, 0x0085, 0x00FC, 0x003C
LABELSST, LABEL, RK, MULRK, NUMBER, BLANK, MULBLANK = 0x00FD, 0x0204, 0x027E, 0x00BD, 0x0203, 0x0201, 0x00BE


def records(buf, start=0):
    p = start
    n = len(buf)
    while p + 4 <= n:
        t, ln = struct.unpack_from("<HH", buf, p)
        yield p, t, buf[p + 4:p + 4 + ln]
        p += 4 + ln


def _rk(v):
    cents = v & 1
    if v & 2:
        num = float(v >> 2)
    else:
        num = struct.unpack("<d", struct.pack("<q", (v & 0xFFFFFFFC) << 32))[0]
    return num / 100 if cents else num


def _sst(buf, pos, ln):
    """Laser SST inkl. CONTINUE. Returnerar lista av strangar."""
    data = buf[pos + 4:pos + 4 + ln]
    p = pos + 4 + ln
    conts = []
    while p + 4 <= len(buf):
        t, l2 = struct.unpack_from("<HH", buf, p)
        if t != CONTINUE:
            break
        conts.append(buf[p + 4:p + 4 + l2])
        p += 4 + l2
    blocks = [data] + conts
    bi, off = 0, 8            # hoppa cstTotal/cstUnique
    total = struct.unpack_from("<I", data, 4)[0]

    def rd(n):
        nonlocal bi, off
        ut = b""
        while n > 0:
            if bi >= len(blocks):
                return ut
            take = min(n, len(blocks[bi]) - off)
            if take <= 0:
                bi += 1; off = 0; continue
            ut += blocks[bi][off:off + take]; off += take; n -= take
        return ut

    def grbit_vid_block():
        nonlocal bi, off
        while bi < len(blocks) and off >= len(blocks[bi]):
            bi += 1; off = 0
        return None if bi >= len(blocks) else blocks[bi][off]

    out = []
    for _ in range(total):
        b = rd(2)
        if len(b) < 2:
            break
        cch = struct.unpack("<H", b)[0]
        g = rd(1)
        if not g:
            break
        grbit = g[0]
        hi, rich, ext = grbit & 1, (grbit >> 3) & 1, (grbit >> 2) & 1
        cRun = struct.unpack("<H", rd(2))[0] if rich else 0
        cbExt = struct.unpack("<i", rd(4))[0] if ext else 0
        # teckendata kan delas over CONTINUE; grbit repeteras da
        chars, kvar, cur_hi = [], cch, hi
        while kvar > 0:
            while bi < len(blocks) and off >= len(blocks[bi]):
                bi += 1; off = 0
                if bi < len(blocks):
                    cur_hi = blocks[bi][off] & 1; off += 1
            if bi >= len(blocks):
                break
            plats = (len(blocks[bi]) - off) // (2 if cur_hi else 1)
            ta = min(kvar, plats)
            raw = rd(ta * (2 if cur_hi else 1))
            chars.append(raw.decode("utf-16-le" if cur_hi else "latin-1", "ignore"))
            kvar -= ta
        if rich:
            rd(4 * cRun)
        if ext:
            rd(cbExt)
        out.append("".join(chars))
    return out


def parse(wb: bytes):
    sheets, sst = [], []
    for pos, t, d in records(wb):
        if t == BOUNDSHEET:
            off = struct.unpack_from("<I", d, 0)[0]
            cch = d[6]
            hi = d[7] & 1
            namn = d[8:8 + cch * (2 if hi else 1)].decode("utf-16-le" if hi else "latin-1", "ignore")
            sheets.append({"name": namn, "offset": off})
        elif t == SST:
            ln = struct.unpack_from("<H", wb, pos + 2)[0]
            sst = _sst(wb, pos, ln)
        elif t == EOF_ and sheets and sst:
            break

    ut = []
    for sh in sheets:
        celler = {}
        for pos, t, d in records(wb, sh["offset"]):
            if t == EOF_:
                break
            if t == LABELSST:
                r, c, _, i = struct.unpack_from("<HHHI", d, 0)
                celler[(r, c)] = sst[i] if i < len(sst) else ""
            elif t == LABEL:
                r, c = struct.unpack_from("<HH", d, 0)
                cch = struct.unpack_from("<H", d, 6)[0]
                hi = d[8] & 1
                celler[(r, c)] = d[9:9 + cch * (2 if hi else 1)].decode(
                    "utf-16-le" if hi else "latin-1", "ignore")
            elif t == RK:
                r, c, _, v = struct.unpack_from("<HHHi", d, 0)
                celler[(r, c)] = _rk(v & 0xFFFFFFFF)
            elif t == MULRK:
                r, c1 = struct.unpack_from("<HH", d, 0)
                n = (len(d) - 6) // 6
                for k in range(n):
                    v = struct.unpack_from("<i", d, 4 + 6 * k + 2)[0]
                    celler[(r, c1 + k)] = _rk(v & 0xFFFFFFFF)
            elif t == NUMBER:
                r, c, _, v = struct.unpack_from("<HHHd", d, 0)
                celler[(r, c)] = v
        ut.append({"name": sh["name"], "cells": celler})
    return ut
