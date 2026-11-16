"""Technical audio checks (not artistic judgements)."""
from __future__ import annotations

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import resample_poly


def _db(x: float) -> float | None:
    return round(float(20 * np.log10(x)), 2) if x > 0 else None


def analyze_file(path: str) -> dict:
    data, sr = sf.read(path, always_2d=True, dtype="float64")
    n, ch = data.shape
    peak = float(np.max(np.abs(data))) if n else 0.0
    # true peak estimate: 4x oversampling (ITU-R BS.1770 style approximation)
    tp = float(np.max(np.abs(resample_poly(data, 4, 1, axis=0)))) if n else 0.0
    rms = float(np.sqrt(np.mean(data ** 2))) if n else 0.0
    clipped = int(np.sum(np.abs(data) >= 0.9999))
    res: dict = {
        "path": path,
        "sample_rate": sr,
        "channels": ch,
        "duration_s": round(n / sr, 3),
        "sample_peak_dbfs": _db(peak),
        "true_peak_dbtp_est": _db(tp),
        "rms_dbfs": _db(rms),
        "rms_per_channel_dbfs": [_db(float(np.sqrt(np.mean(data[:, c] ** 2)))) if n else None for c in range(ch)],
        "clipped_samples": clipped,
        "dc_offset": [round(float(v), 6) for v in np.mean(data, axis=0)],
    }
    if n >= int(0.4 * sr):
        meter = pyln.Meter(sr)
        lufs = meter.integrated_loudness(data)
        res["integrated_lufs"] = round(float(lufs), 2) if np.isfinite(lufs) else None
    if ch == 2 and n:
        l, r = data[:, 0], data[:, 1]
        denom = np.sqrt(np.sum(l * l) * np.sum(r * r))
        res["stereo_correlation"] = round(float(np.sum(l * r) / denom), 3) if denom > 0 else None
    # 1-second window loudness profile (short-term RMS) to spot dropouts / silence
    win = sr
    prof = []
    for i in range(0, n, win):
        seg = data[i:i + win]
        v = float(np.sqrt(np.mean(seg ** 2)))
        prof.append(_db(v) if v > 0 else -120.0)
    res["rms_per_second_dbfs"] = prof[:600]
    warnings = []
    if clipped:
        warnings.append(f"{clipped} clipped samples")
    if res["true_peak_dbtp_est"] is not None and res["true_peak_dbtp_est"] > -1.0:
        warnings.append("true peak above -1 dBTP (streaming platforms recommend <= -1)")
    if peak == 0:
        warnings.append("file is digital silence")
    silent_secs = sum(1 for v in prof if v is not None and v < -70)
    if prof and silent_secs > 0.5 * len(prof):
        warnings.append(f"{silent_secs}/{len(prof)} seconds below -70 dBFS (possible demo-mode silence or muted output)")
    res["warnings"] = warnings
    return res
