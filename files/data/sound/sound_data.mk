SDAT := files/data/sound/gs_sound_data.sdat
SDAT_BASE := files/data/sound/gs_sound_data.base.sdat
SOUND_MIDI_DIR := files/data/sound/midi
SOUND_MIDIS := $(wildcard $(SOUND_MIDI_DIR)/*.mid)
SOUND_PYTHON := $(if $(PYTHON),$(PYTHON),python3)
SDAT_BUILD := tools/py_scripts/sdat_build.py
MID2SSEQ := tools/py_scripts/mid2sseq.py

# Each $(SOUND_MIDI_DIR)/<SEQUENCE>.mid replaces that sequence; the directory itself is a dependency so that
# removing a MIDI file rebuilds the archive too
$(SDAT): $(SDAT_BASE) $(SOUND_MIDI_DIR) $(SOUND_MIDIS) $(wildcard $(SOUND_MIDI_DIR)/midi.cfg) $(SDAT_BUILD) $(MID2SSEQ)
	$(SOUND_PYTHON) $(SDAT_BUILD) $(SDAT_BASE) $(SOUND_MIDI_DIR) $@

FS_RULE_OVERRIDES += $(SDAT)

clean-sound-data:
	$(RM) $(SDAT)

.PHONY: clean-sound-data
clean-filesystem: clean-sound-data
