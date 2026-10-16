#!/usr/bin/env python3
"""Build the sound archive from the game's own and the MIDI files that replace its sequences.

    sdat_build.py BASE.sdat MIDI_DIR OUT.sdat

Each MIDI_DIR/<SEQUENCE>.mid, named after a sequence of the archive (SEQ_GS_T_WAKABA.mid), replaces that sequence,
converted by mid2sseq.py. The sequence keeps its bank, volume, priorities and player unless MIDI_DIR/midi.cfg says
otherwise, one line per file, as pokeemerald's midi.cfg:

    SEQ_GS_T_WAKABA.mid: -V100 -GBANK_BGM_FIELD1

    -V<n>  the sequence's volume, 0 to 127
    -G<b>  its bank, by name or number
    -C<n>  its channel priority      -P<n>  its player priority      -L<n>  its player

Without MIDI files the archive is the game's own, byte for byte. The other files keep their order and the archive's
32-byte alignment; a replaced sequence takes the place of its file, or a new file at the end when the file is shared
with other sequences (the dummy ones).
"""
import argparse
import re
import struct
import sys
from pathlib import Path

import mid2sseq

SEQ, BANK = 0, 2
INFO_SEQ = struct.Struct("<HHHBBBB")             # File, unused, bank, volume, channel priority, player priority, player
OPTIONS = {"V": 3, "G": 2, "C": 4, "P": 5, "L": 6}  # Option letter to its INFO_SEQ field


def align(value: int, to: int = 32) -> int:
    return value + -value % to


class Sdat:
    def __init__(self, data: bytes):
        if data[:4] != b"SDAT":
            raise SystemExit("error: not a sound archive")
        self.data = bytearray(data)
        (self.symb, _, self.info, _, self.fat_offset, _, self.file_offset, _) = struct.unpack_from("<8I", data, 0x10)
        count = struct.unpack_from("<I", data, self.fat_offset + 8)[0]
        self.fat = [list(struct.unpack_from("<4I", data, self.fat_offset + 12 + 16 * i)) for i in range(count)]
        self.files = [bytes(data[offset:offset + size]) for offset, size, _, _ in self.fat]

    def records(self, base: int, kind: int) -> list[int]:
        table = base + struct.unpack_from("<I", self.data, base + 8 + 4 * kind)[0]
        count = struct.unpack_from("<I", self.data, table)[0]
        return list(struct.unpack_from(f"<{count}I", self.data, table + 4))

    def names(self, kind: int) -> dict[str, int]:
        names = {}
        for number, offset in enumerate(self.records(self.symb, kind) if self.symb else []):
            if offset:
                end = self.data.index(b"\0", self.symb + offset)
                names[self.data[self.symb + offset:end].decode("ascii")] = number
        return names

    def seq_entries(self) -> dict[int, int]:
        """The offsets of the sequences' INFO entries, by number."""
        return {n: self.info + offset for n, offset in enumerate(self.records(self.info, SEQ)) if offset}

    def build(self) -> bytes:
        out = self.data[:self.fat_offset]
        out += b"FAT " + struct.pack("<II", 12 + 16 * len(self.files), len(self.files))
        file_offset = len(out) + 16 * len(self.files)
        pos = align(file_offset + 16)
        entries = []
        for file, (_, _, *reserved) in zip(self.files, self.fat + [[0, 0, 0, 0]] * len(self.files)):
            entries.append(struct.pack("<4I", pos, len(file), *reserved))
            pos = align(pos + len(file))
        out += b"".join(entries)
        out += b"FILE" + struct.pack("<III", pos - file_offset, len(self.files), 0)
        for file in self.files:
            out += bytes(align(len(out)) - len(out)) + file
        out += bytes(pos - len(out))
        struct.pack_into("<I", out, 8, len(out))
        struct.pack_into("<4I", out, 0x20, self.fat_offset, file_offset - self.fat_offset, file_offset,
                         pos - file_offset)
        return bytes(out)


def read_config(path: Path) -> dict[str, list[tuple[str, str]]]:
    config = {}
    if not path.exists():
        return config
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.split("#")[0].strip()
        if not line:
            continue
        name, _, options = line.partition(":")
        parsed = []
        for option in options.split():
            match = re.fullmatch(r"-([A-Z])(\S+)", option)
            if not match or match[1] not in OPTIONS:
                raise SystemExit(f"error: {path}:{number}: unknown option {option}")
            parsed.append((match[1], match[2]))
        config[name.strip()] = parsed
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base", type=Path)
    parser.add_argument("midi_dir", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    sdat = Sdat(args.base.read_bytes())
    sequences = sdat.names(SEQ)
    banks = sdat.names(BANK)
    entries = sdat.seq_entries()
    config = read_config(args.midi_dir / "midi.cfg")
    midis = sorted(args.midi_dir.glob("*.mid")) if args.midi_dir.is_dir() else []
    for name in config:
        if not (args.midi_dir / name).exists():
            print(f"warning: midi.cfg names {name}, which isn't in {args.midi_dir}", file=sys.stderr)

    for midi in midis:
        name = midi.stem
        if name not in sequences or sequences[name] not in entries:
            sys.exit(f"error: {midi}: the sound archive has no sequence {name}")
        entry = entries[sequences[name]]
        fields = list(INFO_SEQ.unpack_from(sdat.data, entry))

        def warn(message):
            print(f"warning: {midi}: {message}", file=sys.stderr)

        try:
            sseq = mid2sseq.convert(midi.read_bytes(), warn)
        except SystemExit as e:
            sys.exit(f"{e.code.replace('error: ', f'error: {midi}: ', 1)}")
        for letter, value in config.get(midi.name, []):
            try:
                value = banks[value] if letter == "G" and value in banks else int(value, 0)
            except ValueError:
                sys.exit(f"error: midi.cfg: {midi.name}: -{letter}{value} isn't a number"
                         + (" or a bank" if letter == "G" else ""))
            fields[OPTIONS[letter]] = value

        file_id = fields[0]
        shared = sum(1 for e in entries.values() if struct.unpack_from("<H", sdat.data, e)[0] == file_id) > 1
        if shared:
            file_id = len(sdat.files)
            sdat.files.append(sseq)
        else:
            sdat.files[file_id] = sseq
        fields[0] = file_id
        INFO_SEQ.pack_into(sdat.data, entry, *fields)

    args.out.write_bytes(sdat.build())


if __name__ == "__main__":
    main()
