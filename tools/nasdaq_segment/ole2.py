"""Minimal OLE2/CFB-lasare — stdlib only. Extraherar en namngiven strom.

Racker for att na 'Workbook'-strommen i en legacy .xls (BIFF8).
Ingen tredjepartsberoende: olefile/xlrd behovs inte.
"""
from __future__ import annotations
import struct

SIG = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
FREE, ENDOFCHAIN, FATSECT, DIFSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFC


class OLE2:
    def __init__(self, data: bytes):
        if data[:8] != SIG:
            raise ValueError("inte en OLE2/CFB-fil")
        self.d = data
        u16 = lambda o: struct.unpack_from("<H", data, o)[0]
        u32 = lambda o: struct.unpack_from("<I", data, o)[0]
        self.ssz = 1 << u16(30)                 # sektorstorlek
        self.mssz = 1 << u16(32)                # minisektorstorlek
        n_fat = u32(44)
        dir_start = u32(48)
        self.mini_cutoff = u32(56)
        mini_fat_start, n_mini_fat = u32(60), u32(64)
        difat_start, n_difat = u32(68), u32(72)

        # DIFAT: 109 forsta posterna ligger i headern
        difat = [u32(76 + 4 * i) for i in range(109)]
        s = difat_start
        for _ in range(n_difat):
            if s in (ENDOFCHAIN, FREE):
                break
            off = self._off(s)
            per = self.ssz // 4 - 1
            difat += [u32(off + 4 * i) for i in range(per)]
            s = u32(off + 4 * per)
        difat = [x for x in difat[:n_fat] if x not in (FREE, ENDOFCHAIN)]

        # FAT
        self.fat = []
        for fs in difat:
            off = self._off(fs)
            self.fat += [u32(off + 4 * i) for i in range(self.ssz // 4)]

        # MiniFAT
        self.minifat = []
        s = mini_fat_start
        for _ in range(n_mini_fat):
            if s in (ENDOFCHAIN, FREE):
                break
            off = self._off(s)
            self.minifat += [u32(off + 4 * i) for i in range(self.ssz // 4)]
            s = self.fat[s] if s < len(self.fat) else ENDOFCHAIN

        # Katalog
        self.dirs = []
        for sec in self._chain(dir_start):
            off = self._off(sec)
            for k in range(self.ssz // 128):
                e = off + 128 * k
                nlen = u16(e + 64)
                if nlen < 2:
                    continue
                namn = data[e:e + nlen - 2].decode("utf-16-le", "ignore")
                self.dirs.append({"name": namn, "type": data[e + 66],
                                  "start": u32(e + 116), "size": u32(e + 120)})
        root = next((x for x in self.dirs if x["type"] == 5), None)
        self.mini_start = root["start"] if root else ENDOFCHAIN

    def _off(self, sec):
        return 512 + sec * self.ssz

    def _chain(self, start, fat=None):
        fat = self.fat if fat is None else fat
        out, s, seen = [], start, set()
        while s not in (ENDOFCHAIN, FREE) and s < len(fat) and s not in seen:
            seen.add(s); out.append(s); s = fat[s]
        return out

    def read(self, name: str) -> bytes:
        e = next((x for x in self.dirs if x["name"] == name), None)
        if e is None:
            raise KeyError(f"strom saknas: {name} (finns: {[d['name'] for d in self.dirs]})")
        if e["size"] >= self.mini_cutoff:
            buf = b"".join(self.d[self._off(s):self._off(s) + self.ssz]
                           for s in self._chain(e["start"]))
        else:
            mini = b"".join(self.d[self._off(s):self._off(s) + self.ssz]
                            for s in self._chain(self.mini_start))
            buf = b"".join(mini[s * self.mssz:(s + 1) * self.mssz]
                           for s in self._chain(e["start"], self.minifat))
        return buf[:e["size"]]

    def streams(self):
        return [d["name"] for d in self.dirs if d["type"] == 2]
