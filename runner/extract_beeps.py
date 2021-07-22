#!/usr/bin/env python3
# Extract beep information from an audio recording
import sys
import warnings
import json

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import librosa

import numpy as np

N_FFT = 4096
HOP_LENGTH = 1024

audio_filename = sys.argv[1]
audio_start_time = float(sys.argv[2])
output_filename = sys.argv[3]

y, _ = librosa.load(audio_filename, sr=22050, mono=True)

pitches, magnitudes = librosa.core.piptrack(y, hop_length=HOP_LENGTH, n_fft=N_FFT, threshold=.9)
magnitudes = magnitudes.sum(axis=0)

beep = magnitudes > 0

beep_start = np.where(np.diff(beep.astype(int)) == 1)[0] + 1
beep_end = np.where(np.diff(beep.astype(int)) == -1)[0] + 1

if len(beep_end) < len(beep_start):
    beep_end = np.concatenate([beep_end, [len(beep)]])
assert len(beep_end) == len(beep_start)

with open(output_filename, "w+") as f:
    for start, end in zip(beep_start, beep_end):
        freq = librosa.core.fft_frequencies(n_fft=N_FFT)[np.argmax((pitches[:, start:end] > 0).sum(axis=1))]
        start_time = librosa.core.frames_to_time(start, hop_length=HOP_LENGTH)
        end_time = librosa.core.frames_to_time(end, hop_length=HOP_LENGTH)
        start_time_absolute = start_time + audio_start_time
        event = {
            "time": start_time_absolute,
            "type": "beep",
            "duration-ms": int((end_time-start_time)*1000),
            "frequency": int(freq)
        }
        f.write(json.dumps(event) + "\n")
        
        #f.write(f'{(end_time-start_time)*1000.0:.0f} ms beep of {freq:.0f} Hz at {start_time_absolute:.2f} seconds\n')
