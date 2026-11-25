"""End-to-end check of the planned ncnn clip pipeline (research prototype, not wired in).

    source -> ffmpeg PNG frames -> realesrgan-ncnn-vulkan (x2) -> rife-ncnn-vulkan (2x fps)
           -> ffmpeg H.264 + the original audio -> result.mp4

    python pipeline_demo.py selftest --esr DIR --rife DIR [--gpu N]
    python pipeline_demo.py clip --esr DIR --rife DIR --src IN --out OUT [--scale 2] [--no-rife]

DIR is a folder with the engine binary and its models exactly as fetched by
zip_range.py. Every external step has a timeout and is checked: a missing or
broken Vulkan driver shows up as a failed self-test, never as a hang.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXE = '.exe' if os.name == 'nt' else ''


def run(cmd, timeout, **kw):
    t = time.monotonic()
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout, **kw)
    if proc.returncode:
        raise RuntimeError('%s failed (%d): %s' % (Path(str(cmd[0])).name, proc.returncode,
                                                  (proc.stderr or proc.stdout)[-400:].strip()))
    return time.monotonic() - t, proc


def probe(path):
    _, p = run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,avg_frame_rate,nb_frames'
                ':format=duration', '-of', 'json', path], 30)
    return json.loads(p.stdout)


def engines(esr, rife):
    e = Path(esr) / ('realesrgan-ncnn-vulkan' + EXE)
    r = next(Path(rife).rglob('rife-ncnn-vulkan' + EXE), None) if rife else None
    return e, r


def selftest(esr, rife, gpu):
    """64x64 upscale + one interpolated frame: proves loader, driver and shaders work."""
    e, r = engines(esr, rife)
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i, color in enumerate(('red', 'blue')):
            run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=64x64:d=1,drawbox=c=%s:t=8' % color,
                 '-frames:v', '1', '-y', tmp / ('f%d.png' % i)], 30)
        sec, _ = run([e, '-i', tmp / 'f0.png', '-o', tmp / 'up.png', '-s', '2', '-n', 'realesr-animevideov3',
                      '-m', Path(esr) / 'models', '-g', str(gpu)], 120)
        st = probe(tmp / 'up.png')['streams'][0]
        out['upscale'] = {'ok': (st['width'], st['height']) == (128, 128), 'seconds': round(sec, 2)}
        if r:
            sec, _ = run([r, '-0', tmp / 'f0.png', '-1', tmp / 'f1.png', '-o', tmp / 'mid.png',
                          '-m', r.parent / 'rife-v4.6', '-g', str(gpu)], 120)
            st = probe(tmp / 'mid.png')['streams'][0]
            out['interpolate'] = {'ok': (st['width'], st['height']) == (64, 64), 'seconds': round(sec, 2)}
    out['ok'] = all(v['ok'] for v in out.values())
    return out


def clip(esr, rife, src, dst, scale, gpu, use_rife=True):
    e, r = engines(esr, rife)
    info = probe(src)
    v = next(s for s in info['streams'] if s['codec_type'] == 'video')
    has_audio = any(s['codec_type'] == 'audio' for s in info['streams'])
    num, den = (int(x) for x in v['avg_frame_rate'].split('/'))
    rate = '%d/%d' % (num * 2, den) if use_rife else v['avg_frame_rate']
    times = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for d in ('src', 'up', 'mid'):
            (tmp / d).mkdir()
        times['decode'], _ = run(['ffmpeg', '-v', 'error', '-i', src, '-map', '0:v:0', '-vsync', 'passthrough',
                                  tmp / 'src' / '%08d.png'], 600)
        frames = len(list((tmp / 'src').iterdir()))
        times['upscale'], _ = run([e, '-i', tmp / 'src', '-o', tmp / 'up', '-s', str(scale), '-n',
                                   'realesr-animevideov3', '-m', Path(esr) / 'models', '-g', str(gpu), '-f', 'png'], 3600)
        last = tmp / 'up'
        if use_rife:
            times['interpolate'], _ = run([r, '-i', tmp / 'up', '-o', tmp / 'mid', '-m', r.parent / 'rife-v4.6',
                                           '-g', str(gpu), '-f', '%08d.png'], 3600)
            last = tmp / 'mid'
        out_frames = len(list(last.iterdir()))
        cmd = ['ffmpeg', '-v', 'error', '-y', '-framerate', rate, '-i', last / '%08d.png']
        if has_audio:
            cmd += ['-i', src, '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac', '-b:a', '192k', '-shortest']
        cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags',
                '+faststart', dst]
        times['encode'], _ = run(cmd, 3600)
    res = probe(dst)
    ov = next(s for s in res['streams'] if s['codec_type'] == 'video')
    return {'source': {'size': [v['width'], v['height']], 'fps': v['avg_frame_rate'], 'frames': frames,
                       'audio': has_audio, 'duration': float(info['format']['duration'])},
            'result': {'size': [ov['width'], ov['height']], 'fps': ov['avg_frame_rate'], 'frames': out_frames,
                       'audio': any(s['codec_type'] == 'audio' for s in res['streams']),
                       'duration': float(res['format']['duration'])},
            'seconds': {k: round(t, 2) for k, t in times.items()},
            'upscale_fps': round(frames / times['upscale'], 2)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['selftest', 'clip'])
    ap.add_argument('--esr', required=True); ap.add_argument('--rife')
    ap.add_argument('--src'); ap.add_argument('--out'); ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--gpu', default='0'); ap.add_argument('--no-rife', action='store_true')
    a = ap.parse_args(argv)
    if not shutil.which('ffmpeg'):
        print(json.dumps({'error': 'ffmpeg not found'})); return 2
    if a.mode == 'selftest':
        print(json.dumps(selftest(a.esr, a.rife, a.gpu)))
    else:
        print(json.dumps(clip(a.esr, a.rife, a.src, a.out, a.scale, a.gpu, not a.no_rife)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
