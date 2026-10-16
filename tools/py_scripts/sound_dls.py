#!/usr/bin/env python3
"""Export the sound archive's instrument banks as DLS files, with the envelopes the sound driver plays.

    sound_dls.py files/data/sound/gs_sound_data.sdat OUT_DIR [BANK_OR_SEQUENCE ...]

Without names it exports every bank of the archive; with names, those banks or the banks of those sequences. Each
bank becomes OUT_DIR/<BANK_NAME>.dls, and OUT_DIR/songs.txt says which file each sequence plays with.

Each region also has a "dsrg" chunk with what the sound driver plays, which other players skip: its type (1 PCM,
2 PSG, 3 noise), the PSG duty, the base key, the attack, decay, sustain, release and pan, and the wave's timer
(struct <8BHH, the last halfword 0), as NDS Synth reads it.

A bank's program N is the DLS instrument N of bank N // 128, once as a melodic instrument and once more as a drum
kit, so that a General MIDI synthesizer finds it on channel 10 too; a drum set and a key split are one instrument
with a region for each key or range. The samples are decoded to PCM16 at their true rate (the hardware's 16756991 Hz
over the wave's timer), the PSG instruments get square waves of their duty and the noise instrument the noise
generator's sequence, at the pitch the hardware gives them at their base key (timer 8006, middle C for the squares).

The envelopes follow the ARM7's sound driver (SND_UpdateExChannelEnvelope, attack_table$3790, CalcRelease and
SNDi_DecibelTable in sub/), which updates each channel every 2728 * 64 cycles, about 5.2 ms:
- the attenuation starts at -72.3 dB and the attack multiplies it by a / 256 each update, a being 255 - attack, or
  attack_table's for an attack of 109 and up. DLS's attack rises linearly in amplitude, so its time is twice the
  time the driver takes to reach -6 dB, which puts the half-way point where the driver has it;
- the decay and the release lower it by a fixed rate in 1/1280 dB each update, linear in dB as DLS's are, so their
  DLS times, the times to fall 96 dB, are exact;
- the sustain level is the ARM7's decibel table's (40 * log10(sustain / 127) dB, floored at -72.2), which DLS takes
  in 0.1% of its 96 dB range.
The velocity, volume and expression need nothing: the driver's curve, the same table, is DLS's default concave one.
"""
import argparse
import math
import struct
import sys
from pathlib import Path

ARM7_CLOCK = 16756991
FRAME = 2728 * 64 / 33513982                   # Seconds between the driver's envelope updates
ATTACK_TABLE = [0x00, 0x01, 0x05, 0x0E, 0x1A, 0x26, 0x33, 0x3F, 0x49, 0x54, 0x5C, 0x64, 0x6D, 0x74, 0x7B, 0x7F,
                0x84, 0x89, 0x8F]
# The ARM7's SNDi_DecibelTable (sub/asm/sound_card_pad_data.s), in tenths of a dB
DECIBELS = [
    -32768, -722, -721, -651, -601, -562, -530, -503, -480, -460, -442, -425, -410, -396, -383, -371,
    -360, -349, -339, -330, -321, -313, -305, -297, -289, -282, -276, -269, -263, -257, -251, -245,
    -239, -234, -229, -224, -219, -214, -210, -205, -201, -196, -192, -188, -184, -180, -176, -173,
    -169, -165, -162, -158, -155, -152, -149, -145, -142, -139, -136, -133, -130, -127, -125, -122,
    -119, -116, -114, -111, -109, -106, -103, -101, -99, -96, -94, -91, -89, -87, -85, -82,
    -80, -78, -76, -74, -72, -70, -68, -66, -64, -62, -60, -58, -56, -54, -52, -50,
    -49, -47, -45, -43, -42, -40, -38, -36, -35, -33, -31, -30, -28, -27, -25, -23,
    -22, -20, -19, -17, -16, -14, -13, -11, -10, -8, -7, -6, -4, -3, -1, 0,
]
SILENT = -723 << 7                             # The attenuation a note starts at, in 1/1280 dB
PER_DB = 1280                                  # The attenuation's units per dB
DLS_RANGE_DB = 96                              # The range of DLS's volume envelope
PSG_TIMER = 8006                               # The timer of the PSG and noise channels at their base key
PSG_STEPS = 32                                 # Samples per cycle of the exported square waves

# DLS connections: sources, destinations and transforms
SRC_NONE, DST_PAN = 0x0000, 0x0004
DST_ATTACK, DST_DECAY, DST_RELEASE, DST_SUSTAIN = 0x0206, 0x0207, 0x0209, 0x020A
DRUMS = 0x80000000

# Waves
PCM8, PCM16, ADPCM = 0, 1, 2
WAVE = struct.Struct("<BBHHHI")  # Encoding, loops, rate, timer, loop start and length after it, in words
INDEX_TABLE = [-1, -1, -1, -1, 2, 4, 6, 8]
STEP_TABLE = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107,
    118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894,
    6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
    32767,
]

# Bank instrument types
INST_PCM, INST_PSG, INST_NOISE, INST_DIRECT_PCM = 1, 2, 3, 4
INST_DRUM_SET, INST_KEY_SPLIT = 16, 17
NOTE = struct.Struct("<HHBBBBBB")  # Wave, wave archive slot, key, attack, decay, sustain, release, pan


# The sound archive


class Sdat:
    """A sound archive's banks, wave archives and sequences, with their names."""
    SEQ, BANK, WAVEARC = 0, 2, 3

    def __init__(self, data: bytes):
        if data[:4] != b"SDAT":
            raise SystemExit("error: not a sound archive")
        self.data = data
        symb, _, info, _, fat, _ = struct.unpack_from("<6I", data, 0x10)
        self.fat = [struct.unpack_from("<II", data, fat + 12 + 16 * i)
                    for i in range(struct.unpack_from("<I", data, fat + 8)[0])]
        self.info = info
        self.symb = symb
        self.names = {kind: self.symbols(kind) for kind in (self.SEQ, self.BANK, self.WAVEARC)}

    def records(self, base: int, kind: int) -> list[int]:
        """The offsets of a kind's records in a block, 0 for an unused number."""
        table = base + struct.unpack_from("<I", self.data, base + 8 + 4 * kind)[0]
        count = struct.unpack_from("<I", self.data, table)[0]
        return list(struct.unpack_from(f"<{count}I", self.data, table + 4))

    def symbols(self, kind: int) -> dict[int, str]:
        names = {}
        if not self.symb:
            return names
        for number, offset in enumerate(self.records(self.symb, kind)):
            if offset:
                end = self.data.index(b"\0", self.symb + offset)
                names[number] = self.data[self.symb + offset:end].decode("ascii", "replace")
        return names

    def name(self, kind: int, number: int) -> str:
        prefix = {self.SEQ: "SEQ", self.BANK: "BANK", self.WAVEARC: "WAVE"}[kind]
        return self.names[kind].get(number, f"{prefix}_{number:03}")

    def file(self, file_id: int) -> bytes:
        offset, size = self.fat[file_id]
        return self.data[offset:offset + size]

    def entry(self, kind: int, number: int) -> int | None:
        offsets = self.records(self.info, kind)
        return self.info + offsets[number] if number < len(offsets) and offsets[number] else None

    def count(self, kind: int) -> int:
        return len(self.records(self.info, kind))

    def bank(self, number: int) -> tuple[bytes, list[int | None]] | None:
        entry = self.entry(self.BANK, number)
        if entry is None:
            return None
        file_id, _, *archives = struct.unpack_from("<HH4H", self.data, entry)
        return self.file(file_id), [None if a == 0xFFFF else a for a in archives]

    def sequence_bank(self, number: int) -> int | None:
        entry = self.entry(self.SEQ, number)
        return None if entry is None else struct.unpack_from("<HHH", self.data, entry)[2]

    def wave_archive(self, number: int) -> bytes | None:
        entry = self.entry(self.WAVEARC, number)
        return None if entry is None else self.file(struct.unpack_from("<I", self.data, entry)[0] & 0xFFFFFF)


def adpcm_decode(data: bytes) -> list[int]:
    predictor, index = struct.unpack_from("<hH", data)
    index = min(88, index)
    samples = []
    for byte in data[4:]:
        for nibble in (byte & 0xF, byte >> 4):
            step = STEP_TABLE[index]
            diff = step >> 3
            if nibble & 1:
                diff += step >> 2
            if nibble & 2:
                diff += step >> 1
            if nibble & 4:
                diff += step
            predictor = max(-0x7FFF, predictor - diff) if nibble & 8 else min(0x7FFF, predictor + diff)
            index = min(88, max(0, index + INDEX_TABLE[nibble & 7]))
            samples.append(predictor)
    return samples


def decode(wave: bytes) -> tuple[int, list[int], int | None, int]:
    """Returns a wave's timer, its samples as PCM16 and the sample its loop starts at, or None."""
    encoding, loops, _, timer, start_words, length_words = WAVE.unpack_from(wave)
    data = wave[WAVE.size:WAVE.size + 4 * (start_words + length_words)]
    if encoding == PCM8:
        samples = [(byte - 256 if byte > 127 else byte) << 8 for byte in data]
        loop_start = start_words * 4
    elif encoding == PCM16:
        samples = [value for (value,) in struct.iter_unpack("<h", data[:len(data) & ~1])]
        loop_start = start_words * 2
    else:
        samples = adpcm_decode(data)
        loop_start = max(0, start_words - 1) * 8
    if not samples:
        samples = [0]
    if loop_start >= len(samples):
        loops = 0
    return timer, samples, loop_start if loops else None, timer


class Waves:
    """The sound archive's waves, decoded, by wave archive and number."""
    def __init__(self, sdat: Sdat):
        self.sdat = sdat
        self.cache = {}

    def get(self, archive: int, number: int):
        if archive not in self.cache:
            swar = self.sdat.wave_archive(archive)
            waves = []
            if swar and swar[:4] == b"SWAR":
                count = struct.unpack_from("<I", swar, 0x38)[0]
                offsets = struct.unpack_from(f"<{count}I", swar, 0x3C)
                waves = [offset for offset in offsets]
            self.cache[archive] = (swar, waves, {})
        swar, offsets, decoded = self.cache[archive]
        if not 0 <= number < len(offsets) or not offsets[number]:
            return None
        if number not in decoded:
            timer, samples, loop_start, _ = decode(swar[offsets[number]:])
            decoded[number] = (ARM7_CLOCK / timer, samples, loop_start, timer)
        return decoded[number]


# The sound driver's envelope


def attack_rate(attack: int) -> int:
    return ATTACK_TABLE[127 - attack] if attack >= 109 else 255 - attack


def fall_rate(value: int) -> int:
    """The decay or release rate of a value (CalcRelease): its attenuation's fall per update."""
    if value == 127:
        return 0xFFFF
    if value == 126:
        return 0x3C00
    if value < 50:
        return value * 2 + 1
    return 0x1E00 // (126 - value)


def attack_seconds(attack: int) -> float:
    """DLS's attack time for the driver's attack: twice its time to reach -6 dB, or 0 for an instant one."""
    rate = attack_rate(attack)
    if rate == 0:
        return 0
    level, frames = SILENT, 0
    while level < -6.02 * PER_DB:
        level = -((-level * rate) >> 8)
        frames += 1
    return 2 * frames * FRAME


def fall_seconds(value: int) -> float:
    """DLS's decay or release time, which DLS measures over its whole range."""
    return DLS_RANGE_DB * PER_DB / fall_rate(value) * FRAME


def time_cents(seconds: float) -> int:
    if seconds <= 0:
        return -0x80000000
    return round(1200 * math.log2(seconds) * 65536)


# DLS


def chunk(tag: bytes, data: bytes) -> bytes:
    return tag + struct.pack("<I", len(data)) + data + bytes(len(data) & 1)


def riff_list(kind: bytes, *chunks: bytes) -> bytes:
    return chunk(b"LIST", kind + b"".join(chunks))


def info(name: str) -> bytes:
    return riff_list(b"INFO", chunk(b"INAM", name.encode("ascii", "replace") + b"\0"))


def articulation(note: dict) -> bytes:
    """The region's envelope and pan, as DLS level 1 connections."""
    sustain = 0.0 if note["sustain"] == 0 else max(0.0, 1 + DECIBELS[note["sustain"]] / 10 / DLS_RANGE_DB)
    blocks = [
        (SRC_NONE, SRC_NONE, DST_ATTACK, 0, time_cents(attack_seconds(note["attack"]))),
        (SRC_NONE, SRC_NONE, DST_DECAY, 0, time_cents(fall_seconds(note["decay"]))),
        (SRC_NONE, SRC_NONE, DST_SUSTAIN, 0, round(sustain * 1000 * 65536)),
        (SRC_NONE, SRC_NONE, DST_RELEASE, 0, time_cents(fall_seconds(note["release"]))),
        (SRC_NONE, SRC_NONE, DST_PAN, 0, round((note["pan"] - 64) * 500 / 64 * 65536)),
    ]
    art = struct.pack("<II", 8, len(blocks)) + b"".join(struct.pack("<HHHHi", *block) for block in blocks)
    return riff_list(b"lart", chunk(b"art1", art))


def wave_sample(unity: int, fine: int, loop: tuple[int, int] | None) -> bytes:
    data = struct.pack("<IHhiII", 20, unity, fine, 0, 0, 1 if loop else 0)
    if loop:
        data += struct.pack("<IIII", 16, 0, *loop)
    return chunk(b"wsmp", data)


class Pool:
    """The waves of a DLS file, each PCM16 with its rate, fine tune and loop, by what they come from."""
    def __init__(self):
        self.waves = []
        self.index = {}

    def add(self, key, rate: float, samples: list[int], loop_start: int | None) -> int:
        if key not in self.index:
            whole = max(1, round(rate))
            fine = round(1200 * math.log2(rate / whole))
            loop = (loop_start, len(samples) - loop_start) if loop_start is not None else None
            self.index[key] = len(self.waves)
            self.waves.append((whole, fine, samples, loop, key))
        return self.index[key]

    def fine(self, index: int) -> int:
        return self.waves[index][1]

    def loop(self, index: int):
        return self.waves[index][3]

    def chunks(self) -> tuple[bytes, bytes]:
        lists = []
        for rate, fine, samples, loop, key in self.waves:
            fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
            data = struct.pack(f"<{len(samples)}h", *samples)
            lists.append(riff_list(b"wave", chunk(b"fmt ", fmt), wave_sample(60, fine, loop), chunk(b"data", data),
                                   info(" ".join(map(str, key)))))
        offsets, cursor = [], 0
        for item in lists:
            offsets.append(cursor)
            cursor += len(item)
        table = chunk(b"ptbl", struct.pack(f"<II{len(offsets)}I", 8, len(offsets), *offsets))
        return table, riff_list(b"wvpl", *lists)


def psg_wave(duty: int) -> tuple[float, list[int], int]:
    """A cycle of the square wave of a PSG duty, high for (duty + 1) / 8 of it, at middle C's rate."""
    high = (duty + 1) * PSG_STEPS // 8
    return ARM7_CLOCK / PSG_TIMER / 8 * PSG_STEPS, [0x7FFF if i < high else -0x7FFF for i in range(PSG_STEPS)], 0


def noise_wave() -> tuple[float, list[int], int]:
    """The noise generator's 15-bit sequence, a sample per step of its timer."""
    state, samples = 0x7FFF, []
    for _ in range(0x7FFF):
        if state & 1:
            state = (state >> 1) ^ 0x6000
            samples.append(-0x7FFF)
        else:
            state >>= 1
            samples.append(0x7FFF)
    return ARM7_CLOCK / PSG_TIMER, samples, 0


# Banks


def read_note(sbnk: bytes, offset: int, kind: int) -> dict:
    wave, archive, key, attack, decay, sustain, release, pan = NOTE.unpack_from(sbnk, offset)
    return {"type": kind, "wave": wave, "wave_archive": archive, "key": key, "attack": attack, "decay": decay,
            "sustain": sustain, "release": release, "pan": pan}


def read_bank(sbnk: bytes) -> list[tuple[int, list[tuple[int, int, dict]]]]:
    """A bank's programs, each with its regions: low key, high key and note."""
    count = struct.unpack_from("<I", sbnk, 0x38)[0]
    programs = []
    for program in range(count):
        kind, offset = struct.unpack_from("<BH", sbnk, 0x3C + 4 * program)
        if kind in (INST_PCM, INST_PSG, INST_NOISE, INST_DIRECT_PCM):
            programs.append((program, [(0, 127, read_note(sbnk, offset, kind))]))
        elif kind == INST_DRUM_SET:
            low, high = sbnk[offset], sbnk[offset + 1]
            regions = []
            for k in range(high - low + 1):
                sub = sbnk[offset + 2 + 12 * k]
                if sub:
                    regions.append((low + k, low + k, read_note(sbnk, offset + 4 + 12 * k, sub)))
            programs.append((program, regions))
        elif kind == INST_KEY_SPLIT:
            lasts = sbnk[offset:offset + 8]
            regions, low, pos = [], 0, offset + 8
            for last in lasts:
                if last == 0:
                    break
                sub = sbnk[pos]
                note = read_note(sbnk, pos + 2, sub)
                pos += 12
                if sub and last >= low:  # A region after a higher one never plays
                    regions.append((low, last, note))
                low = max(low, last + 1)
            programs.append((program, regions))
    return programs


def bank_dls(name: str, sbnk: bytes, slots: list[int | None], sdat: Sdat, waves: Waves) -> tuple[bytes, list[str]]:
    """Returns a bank's DLS file, and what it couldn't export."""
    pool = Pool()
    problems = []

    def region(low: int, high: int, note: dict, where: str) -> bytes | None:
        kind, key = note["type"], note["key"]
        if kind in (INST_PCM, INST_DIRECT_PCM):
            slot = note["wave_archive"]
            archive = slots[slot] if slot < len(slots) else None
            wave = waves.get(archive, note["wave"]) if archive is not None else None
            if wave is None:
                problems.append(f"{where}: wave {note['wave']} of wave archive slot {slot} is missing")
                return None
            index = pool.add((sdat.name(Sdat.WAVEARC, archive), note["wave"]), *wave[:3])
            timer, code = wave[3], 1
        elif kind == INST_PSG:
            index = pool.add(("psg", note["wave"]), *psg_wave(min(6, note["wave"])))
            timer, code = PSG_TIMER, 2
        else:
            index = pool.add(("noise",), *noise_wave())
            timer, code = PSG_TIMER, 3
        header = struct.pack("<HHHHHH", low, high, 0, 127, 0, 0)
        # The region as the sound driver has it, for players that emulate it (NDS Synth)
        native = struct.pack("<8BHH", code, note["wave"] if code == 2 else 0, key, note["attack"], note["decay"],
                             note["sustain"], note["release"], note["pan"], timer, 0)
        return riff_list(b"rgn ", chunk(b"rgnh", header), wave_sample(key, pool.fine(index), pool.loop(index)),
                         chunk(b"wlnk", struct.pack("<HHII", 0, 0, 1, index)), articulation(note),
                         chunk(b"dsrg", native))

    instruments = []
    for program, parts in read_bank(sbnk):
        where = f"{name} program {program}"
        regions = [r for r in (region(low, high, note, f"{where} keys {low}-{high}") for low, high, note in parts) if r]
        if not regions:
            continue
        for drums in (0, DRUMS):
            header = struct.pack("<III", len(regions), drums | (program // 128) << 8, program % 128)
            label = f"{name} program {program}" + (" (drums)" if drums else "")
            instruments.append(riff_list(b"ins ", chunk(b"insh", header), riff_list(b"lrgn", *regions), info(label)))
    table, pool_list = pool.chunks()
    body = (b"DLS " + chunk(b"vers", struct.pack("<II", 1 << 16, 0))
            + chunk(b"colh", struct.pack("<I", len(instruments))) + riff_list(b"lins", *instruments) + table
            + pool_list + info(name))
    return chunk(b"RIFF", body), problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sdat", type=Path, help="files/data/sound/gs_sound_data.sdat")
    parser.add_argument("output", type=Path, help="the directory to write the DLS files to")
    parser.add_argument("names", nargs="*", help="banks (BANK_*) or sequences (SEQ_*) to export")
    args = parser.parse_args()
    sdat = Sdat(args.sdat.read_bytes())
    banks = {sdat.name(Sdat.BANK, n): n for n in range(sdat.count(Sdat.BANK)) if sdat.entry(Sdat.BANK, n)}
    songs = {}
    for n in range(sdat.count(Sdat.SEQ)):
        bank = sdat.sequence_bank(n)
        if bank is not None and bank in banks.values():
            songs[sdat.name(Sdat.SEQ, n)] = sdat.name(Sdat.BANK, bank)
    if args.names:
        wanted = []
        for name in args.names:
            if name in banks:
                wanted.append(name)
            elif name in songs:
                wanted.append(songs[name])
            else:
                sys.exit(f"error: {name} is neither a bank nor a sequence")
    else:
        wanted = list(banks)
    args.output.mkdir(parents=True, exist_ok=True)
    waves = Waves(sdat)
    wanted = list(dict.fromkeys(wanted))
    for name in wanted:
        sbnk, slots = sdat.bank(banks[name])
        if sbnk[:4] != b"SBNK":
            print(f"warning: {name} is not a bank file", file=sys.stderr)
            continue
        data, problems = bank_dls(name, sbnk, slots, sdat, waves)
        (args.output / f"{name}.dls").write_bytes(data)
        for problem in problems:
            print(f"warning: {problem}", file=sys.stderr)
    lines = [f"{song} {bank}.dls" for song, bank in songs.items() if bank in wanted]
    (args.output / "songs.txt").write_text("\n".join(lines) + "\n")
    print(f"{len(wanted)} banks in {args.output}")


if __name__ == "__main__":
    main()
