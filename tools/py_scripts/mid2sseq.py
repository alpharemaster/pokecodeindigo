#!/usr/bin/env python3
"""Convert a standard MIDI file to a sequence (SSEQ) the sound driver plays.

    mid2sseq.py IN.mid OUT.sseq

Each MIDI channel with notes becomes a track, in channel order; the first one also opens the others and takes the
tempo changes. The sequence is laid out as the Nitro SDK's converter lays out the game's own: every track turns off
note waiting and follows each note with a rest, at 48 ticks per quarter note.

Loops: a marker or text event "[" or "loopStart" (or controller 111) where the loop starts, and "]" or "loopEnd" where
it ends, as pokeemerald's mid2agb takes them. Every track then jumps back to the loop start at the loop end, notes
still held there are cut, and the controllers in effect at the loop start are set again after it so that each pass
plays the same. Without a loop end the loop ends with the song, at its last End of Track; without a loop start the
song plays once and stops.

Programs: program P of bank B (controller 0) plays the bank's instrument B * 128 + P, as the DLS files of
sound_dls.py number them; a drum kit is a program like any other, on any channel.

Controllers:
    1 modulation depth     5 portamento time      6 data entry (RPN 0, the pitch bend range)
    7 volume              10 pan                 11 expression
   21 modulation speed    22 modulation type (0 pitch, 1 volume, 2 pan)    23 modulation range
   26 modulation delay    64 sustain pedal (held notes are lengthened)     65 portamento on/off
   72 release             73 attack              75 decay                  79 sustain
The pitch bend is scaled to the driver's -128..127. A track starts at volume 100 like a MIDI channel, unless the MIDI
sets its volume at tick 0; the other defaults are the same.
"""
import argparse
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

TICKS_PER_QUARTER = 48

# Sequence commands
REST, PROGRAM, OPEN_TRACK, JUMP = 0x80, 0x81, 0x93, 0x94
PAN, VOLUME, BEND, BEND_RANGE, NOTE_WAIT = 0xC0, 0xC1, 0xC4, 0xC5, 0xC7
MOD_DEPTH, MOD_SPEED, MOD_TYPE, MOD_RANGE = 0xCA, 0xCB, 0xCC, 0xCD
PORTAMENTO, PORTAMENTO_TIME = 0xCE, 0xCF
ATTACK, DECAY, SUSTAIN, RELEASE, EXPRESSION = 0xD0, 0xD1, 0xD2, 0xD3, 0xD5
MOD_DELAY, TEMPO = 0xE0, 0xE1
ALLOCATE_TRACKS, END = 0xFE, 0xFF

# MIDI controllers that map to a one-byte command
CONTROLLERS = {
    1: MOD_DEPTH, 5: PORTAMENTO_TIME, 7: VOLUME, 10: PAN, 11: EXPRESSION, 21: MOD_SPEED, 22: MOD_TYPE,
    23: MOD_RANGE, 72: RELEASE, 73: ATTACK, 75: DECAY, 79: SUSTAIN,
}
CC_BANK, CC_DATA_ENTRY, CC_MOD_DELAY, CC_PEDAL, CC_PORTAMENTO = 0, 6, 26, 64, 65
CC_LOOP_START, CC_RPN_LSB, CC_RPN_MSB = 111, 100, 101
# What a track starts with, as a MIDI channel does, to set again at the loop start when the loop changes it
DEFAULTS = {
    PROGRAM: [PROGRAM, 0], VOLUME: [VOLUME, 100], PAN: [PAN, 64], EXPRESSION: [EXPRESSION, 127], BEND: [BEND, 0],
    BEND_RANGE: [BEND_RANGE, 2], MOD_DEPTH: [MOD_DEPTH, 0], MOD_SPEED: [MOD_SPEED, 16], MOD_TYPE: [MOD_TYPE, 0],
    MOD_RANGE: [MOD_RANGE, 1], MOD_DELAY: [MOD_DELAY, 0, 0], PORTAMENTO: [PORTAMENTO, 0],
    PORTAMENTO_TIME: [PORTAMENTO_TIME, 0], ATTACK: [ATTACK, 255], DECAY: [DECAY, 255], SUSTAIN: [SUSTAIN, 255],
    RELEASE: [RELEASE, 255], TEMPO: [TEMPO, 120, 0],
}
# Controllers left out without a warning: they mean nothing to the driver
QUIET_CONTROLLERS = {32, 38, 91, 93, 98, 99, 120, 121, 123}

LOOP_STARTS = {"[", "loopstart", "loop_start", "loop start"}
LOOP_ENDS = {"]", "loopend", "loop_end", "loop end"}


def error(message: str):
    raise SystemExit(f"error: {message}")


# Reading the MIDI file


@dataclass(order=True)
class Event:
    tick: int
    order: int                                   # The event's place in the file, to keep the file's order
    kind: str = field(compare=False)             # "on", "off", "cc", "program", "bend", "tempo", "loop_start", ...
    channel: int = field(compare=False, default=0)
    a: int = field(compare=False, default=0)
    b: int = field(compare=False, default=0)


def read_varlen(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    while True:
        if pos >= len(data):
            error("truncated MIDI track")
        byte = data[pos]
        pos += 1
        value = value << 7 | byte & 0x7F
        if not byte & 0x80:
            return value, pos


def read_midi(data: bytes) -> tuple[int, list[Event]]:
    """Returns the MIDI file's ticks per quarter note and its events, from all tracks, in time order."""
    if data[:4] != b"MThd":
        error("not a MIDI file")
    length, _, track_count, division = struct.unpack_from(">IHHH", data, 4)
    if division & 0x8000:
        error("MIDI files timed in SMPTE frames aren't supported")
    pos = 8 + length
    events = []
    for _ in range(track_count):
        while data[pos:pos + 4] not in (b"MTrk", b""):        # Skip unknown chunks
            pos += 8 + struct.unpack_from(">I", data, pos + 4)[0]
        if data[pos:pos + 4] != b"MTrk":
            break
        end = pos + 8 + struct.unpack_from(">I", data, pos + 4)[0]
        pos += 8
        tick = 0
        status = 0
        while pos < end:
            delta, pos = read_varlen(data, pos)
            tick += delta
            if data[pos] & 0x80:
                status = data[pos]
                pos += 1
            elif not status:
                error("MIDI data byte without a status")

            def add(kind, channel=0, a=0, b=0):
                events.append(Event(tick, len(events), kind, channel, a, b))

            if status == 0xFF:
                meta = data[pos]
                length, pos = read_varlen(data, pos + 1)
                body = data[pos:pos + length]
                pos += length
                if meta == 0x51:
                    add("tempo", a=int.from_bytes(body, "big"))
                elif meta in (0x01, 0x06):
                    text = body.decode("latin-1").strip().lower()
                    if text in LOOP_STARTS:
                        add("loop_start")
                    elif text in LOOP_ENDS:
                        add("loop_end")
                elif meta == 0x2F:
                    add("track_end")
                    break
                status = 0
            elif status in (0xF0, 0xF7):
                length, pos = read_varlen(data, pos)
                pos += length
                status = 0
            else:
                kind, channel = status & 0xF0, status & 0x0F
                if kind in (0xC0, 0xD0):
                    a = data[pos]
                    pos += 1
                    if kind == 0xC0:
                        add("program", channel, a)
                    continue
                a, b = data[pos], data[pos + 1]
                pos += 2
                if kind == 0x90 and b:
                    add("on", channel, a, b)
                elif kind in (0x80, 0x90):
                    add("off", channel, a)
                elif kind == 0xB0:
                    add("loop_start" if a == CC_LOOP_START else "cc", channel, a, b)
                elif kind == 0xE0:
                    add("bend", channel, a | b << 7)
        pos = end
    events.sort()
    return division, events


# Writing the sequence


def varlen(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(value & 0x7F | 0x80)
        value >>= 7
    return bytes(reversed(out))


@dataclass
class Note:
    start: int
    key: int
    velocity: int
    end: int | None = None


@dataclass
class Track:
    channel: int
    items: list = field(default_factory=list)    # (tick, order, bytes or Note)
    notes: list = field(default_factory=list)


def convert(midi: bytes, warn=lambda message: print(f"warning: {message}", file=sys.stderr)) -> bytes:
    """Returns the sequence file of a MIDI file."""
    division, events = read_midi(midi)
    for event in events:                         # To the sequence's ticks, rounding each time and not each delta
        event.tick = (event.tick * TICKS_PER_QUARTER * 2 + division) // (2 * division)

    loop_start = next((e.tick for e in events if e.kind == "loop_start"), None)
    loop_end = next((e.tick for e in events if e.kind == "loop_end"), None)
    song_end = max((e.tick for e in events), default=0)
    if loop_start is not None and loop_end is None:
        loop_end = song_end
    if loop_end is not None and (loop_start is None or loop_end <= loop_start):
        error("the loop end must come after a loop start")

    tracks: dict[int, Track] = {}
    ignored = set()
    bank = [0] * 16
    rpn = [(127, 127)] * 16
    pedal = [False] * 16
    held: dict[int, list[Note]] = {}             # The channel's notes held by the sustain pedal
    playing: dict[tuple[int, int], list[Note]] = {}
    tempo_items = []
    for event in events:
        if loop_end is not None and event.tick >= loop_end:
            break
        channel = event.channel
        track = tracks.setdefault(channel, Track(channel))

        def put(*command):
            track.items.append((event.tick, event.order, bytes(command)))

        if event.kind == "on":
            for note in held.get(channel, []):   # A held note ends when its key is struck again
                if note.key == event.a and note.end is None:
                    note.end = event.tick
            note = Note(event.tick, event.a, event.b)
            playing.setdefault((channel, event.a), []).append(note)
            track.notes.append(note)
            track.items.append((event.tick, event.order, note))
        elif event.kind == "off":
            notes = playing.get((channel, event.a))
            if notes:
                note = notes.pop(0)
                if pedal[channel]:
                    held.setdefault(channel, []).append(note)
                else:
                    note.end = event.tick
        elif event.kind == "program":
            put(PROGRAM, *varlen(bank[channel] * 128 + event.a))
        elif event.kind == "bend":
            put(BEND, max(-128, min(127, round((event.a - 0x2000) / 64))) & 0xFF)
        elif event.kind == "tempo":
            bpm = max(1, min(0xFFFF, round(60_000_000 / max(1, event.a))))
            tempo_items.append((event.tick, event.order, bytes([TEMPO, *struct.pack("<H", bpm)])))
        elif event.kind == "cc":
            number, value = event.a, event.b
            if number in CONTROLLERS:
                put(CONTROLLERS[number], value)
            elif number == CC_BANK:
                bank[channel] = value
            elif number == CC_RPN_MSB:
                rpn[channel] = (value, rpn[channel][1])
            elif number == CC_RPN_LSB:
                rpn[channel] = (rpn[channel][0], value)
            elif number == CC_DATA_ENTRY:
                if rpn[channel] == (0, 0):
                    put(BEND_RANGE, value)
            elif number == CC_MOD_DELAY:
                put(MOD_DELAY, *struct.pack("<H", value))
            elif number == CC_PORTAMENTO:
                put(PORTAMENTO, int(value >= 64))
            elif number == CC_PEDAL:
                pedal[channel] = value >= 64
                if not pedal[channel]:
                    for note in held.pop(channel, []):
                        if note.end is None:
                            note.end = event.tick
            elif number not in QUIET_CONTROLLERS:
                ignored.add(number)
    if ignored:
        warn(f"controller(s) {', '.join(map(str, sorted(ignored)))} have no sequence command and were left out")

    end = loop_end if loop_end is not None else song_end
    tracks = [t for _, t in sorted(tracks.items()) if t.notes]
    if not tracks:
        error("the MIDI file has no notes")
    if len(tracks) > 16:
        error("a sequence has at most 16 tracks")
    for track in tracks:
        for note in track.notes:
            note.end = end if note.end is None else min(note.end, end)
    tracks[0].items += tempo_items

    bodies = []
    for number, track in enumerate(tracks):
        items = sorted(track.items, key=lambda item: item[:2])
        body = bytearray([NOTE_WAIT, 0])
        if not any(i[0] == 0 and isinstance(i[2], bytes) and i[2][0] == VOLUME for i in items):
            body += bytes([VOLUME, 100])
        used = {i[2][0] for i in items if isinstance(i[2], bytes)}
        state = {c: bytes(v) for c, v in DEFAULTS.items() if c in used}  # Each command's value, for the loop start
        label = None
        now = 0

        def wait(tick):
            nonlocal now
            if tick > now:
                body.extend([REST, *varlen(tick - now)])
                now = tick

        def mark_loop():
            nonlocal label
            label = len(body)
            for command in state.values():
                body.extend(command)

        for tick, _, item in items:
            if label is None and loop_start is not None and tick >= loop_start:
                wait(loop_start)
                mark_loop()
            wait(tick)
            if isinstance(item, Note):
                body.extend([item.key, item.velocity, *varlen(max(1, item.end - item.start))])
            else:
                body.extend(item)
                state[item[0]] = item
        if label is None and loop_start is not None:
            wait(loop_start)
            mark_loop()
        wait(end)
        bodies.append((body, label))

    header = 3 + 5 * (len(tracks) - 1)
    starts = []
    pos = header
    for body, _ in bodies:
        starts.append(pos)
        pos += len(body) + (4 if loop_start is not None else 0) + 1
    data = bytearray([ALLOCATE_TRACKS, *struct.pack("<H", (1 << len(tracks)) - 1)])
    for number in range(1, len(tracks)):
        data += bytes([OPEN_TRACK, number]) + starts[number].to_bytes(3, "little")
    for start, (body, label) in zip(starts, bodies):
        data += body
        if label is not None:
            data += bytes([JUMP]) + (start + label).to_bytes(3, "little")
        data.append(END)
    data += bytes(-len(data) % 4)
    return (b"SSEQ" + struct.pack("<HHIHH", 0xFEFF, 0x0100, 0x1C + len(data), 0x10, 1)
            + b"DATA" + struct.pack("<II", 0xC + len(data), 0x1C) + data)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("midi", type=Path)
    parser.add_argument("sseq", type=Path)
    args = parser.parse_args()
    args.sseq.write_bytes(convert(args.midi.read_bytes()))


if __name__ == "__main__":
    main()
