"""Optional AI worker: Real-ESRGAN upscaling and RIFE frame interpolation.

Runs in a separate Python environment (".ai-venv", see setup-ai.bat) so the
player itself never imports torch. Protocol: one JSON request on stdin, JSON
progress lines on stdout; the last line carries "result" or "error". The
worker opens no ports and reads only the files named in the request.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time

_last_emit = 0.0


def emit(force=True, **message):
    global _last_emit
    now = time.monotonic()
    if not force and now - _last_emit < .5:
        return
    _last_emit = now
    sys.stdout.write(json.dumps(message) + '\n'); sys.stdout.flush()


def probe():
    info = {'python': sys.version.split()[0], 'torch': None, 'cuda': False, 'device': 'cpu',
            'device_name': '', 'vram_gb': 0, 'cpu_threads': os.cpu_count() or 1, 'numpy': False, 'pillow': False}
    try:
        import numpy  # noqa: F401
        info['numpy'] = True
    except Exception:
        pass
    try:
        import PIL  # noqa: F401
        info['pillow'] = True
    except Exception:
        pass
    try:
        import torch
        info['torch'] = torch.__version__
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info.update(cuda=True, device='cuda', device_name=props.name, vram_gb=round(props.total_memory / 2 ** 30, 1))
    except Exception as exc:  # broken/partial installs are reported, not raised
        info['error'] = str(exc)[:200]
    return info


# ------------------------------------------------------------------ models
def _state_dict(path):
    import torch
    data = torch.load(path, map_location='cpu', weights_only=True)
    if isinstance(data, dict):
        for key in ('params_ema', 'params'):
            if key in data:
                return data[key]
    return data


def load_upscaler(spec, device, half):
    from kryonyx import ai_arch
    if spec['arch'] == 'rrdb':
        net = ai_arch.RRDBNet()
    else:
        net = ai_arch.SRVGGNetCompact(num_conv=int(spec.get('num_conv', 32)))
    net.load_state_dict(_state_dict(spec['path']), strict=True)
    net.eval().to(device)
    return net.half() if half else net


def load_rife(spec, device, half):
    from kryonyx import ai_arch
    state = _state_dict(spec['path'])
    state = {k.replace('module.', '', 1): v for k, v in state.items() if k.startswith('module.')} or state
    net = ai_arch.IFNet()
    net.load_state_dict(state, strict=True)
    net.eval().to(device)
    return net.half() if half else net


def pick_device(name):
    import torch
    if name in ('auto', 'cuda') and torch.cuda.is_available():
        return 'cuda'
    if name == 'cuda':
        raise RuntimeError('CUDA was requested but no NVIDIA GPU is available')
    return 'cpu'


def sr_x4(net, x, tile, pad=10):
    """x: 1x3xHxW float on device -> 1x3x4Hx4W, tiled to bound memory."""
    _, c, h, w = x.shape
    if not tile or (h <= tile and w <= tile):
        return net(x)
    out = x.new_empty((1, c, h * 4, w * 4))
    for y0 in range(0, h, tile):
        for x0 in range(0, w, tile):
            y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
            py0, py1, px0, px1 = max(y0 - pad, 0), min(y1 + pad, h), max(x0 - pad, 0), min(x1 + pad, w)
            part = net(x[:, :, py0:py1, px0:px1])
            oy, ox = (y0 - py0) * 4, (x0 - px0) * 4
            out[:, :, y0 * 4:y1 * 4, x0 * 4:x1 * 4] = part[:, :, oy:oy + (y1 - y0) * 4, ox:ox + (x1 - x0) * 4]
    return out


# ------------------------------------------------------------------ image
def run_image(req):
    import torch
    import numpy as np
    from PIL import Image
    device = pick_device(req.get('device', 'auto')); half = device == 'cuda'
    torch.set_num_threads(max(1, int(req.get('threads') or 2)))
    emit(stage='loading', device=device)
    net = load_upscaler(req['upscale'], device, half)
    with Image.open(req['input']) as im:
        im = im.convert('RGB')
        out_w, out_h = int(req['out_w']), int(req['out_h'])
        limit = int(req.get('max_input', 2560))
        if max(im.size) > limit:  # bounded memory; output size is unchanged
            k = limit / max(im.size)
            im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.Resampling.LANCZOS)
        src = np.asarray(im, dtype=np.uint8)
    h, w = src.shape[:2]
    tile = int(req.get('tile') or (384 if device == 'cuda' else 256))
    canvas = np.empty((h * 4, w * 4, 3), dtype=np.uint8)
    tiles = [(y, x) for y in range(0, h, tile) for x in range(0, w, tile)]
    started = time.monotonic(); pad = 10
    with torch.inference_mode():
        for i, (y0, x0) in enumerate(tiles):
            y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
            py0, py1, px0, px1 = max(y0 - pad, 0), min(y1 + pad, h), max(x0 - pad, 0), min(x1 + pad, w)
            part = torch.from_numpy(np.ascontiguousarray(src[py0:py1, px0:px1])).to(device)
            part = part.permute(2, 0, 1).unsqueeze(0).to(torch.float16 if half else torch.float32) / 255
            y = net(part)[0].clamp_(0, 1).mul_(255).round_().to(torch.uint8).permute(1, 2, 0).cpu().numpy()
            oy, ox = (y0 - py0) * 4, (x0 - px0) * 4
            canvas[y0 * 4:y1 * 4, x0 * 4:x1 * 4] = y[oy:oy + (y1 - y0) * 4, ox:ox + (x1 - x0) * 4]
            done = i + 1; elapsed = time.monotonic() - started
            emit(force=done == len(tiles), stage='processing', done=done, total=len(tiles),
                 eta=round(elapsed / done * (len(tiles) - done)), unit='tiles')
    emit(stage='saving')
    result = Image.fromarray(canvas)
    if result.size != (out_w, out_h):
        result = result.resize((out_w, out_h), Image.Resampling.LANCZOS)
    tmp = req['output'] + '.part'
    result.save(tmp, 'JPEG', quality=97, subsampling=0)
    os.replace(tmp, req['output'])
    emit(stage='done', result=req['output'], width=out_w, height=out_h)


# ------------------------------------------------------------------ video
_COMMON = {'23.98': '24000/1001', '23.976': '24000/1001', '29.97': '30000/1001', '47.95': '48000/1001',
           '59.94': '60000/1001', '119.88': '120000/1001'}


def video_info(ffmpeg, src):
    proc = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-i', src], capture_output=True, text=True,
                          errors='replace', timeout=120)
    text = proc.stderr
    line = next((l for l in text.splitlines() if re.search(r'Stream #\S+.*: Video:', l)), '')
    size = re.search(r'[ ,](\d{2,5})x(\d{2,5})(?=[ ,\[]|$)', line)
    if not size:
        raise RuntimeError('No video stream in the source file')
    rate = re.search(r'([\d.]+) fps', line) or re.search(r'([\d.]+) tbr', line)
    fps = float(rate.group(1)) if rate else 30.0
    if not 1 <= fps <= 240:
        fps = 30.0
    width, height = int(size.group(1)), int(size.group(2))
    rot = re.search(r'rotation of (-?[\d.]+) degrees', text) or re.search(r'rotate\s*:\s*(-?\d+)', text)
    if rot and abs(round(float(rot.group(1)))) % 180 == 90:
        width, height = height, width
    dur = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', text)
    duration = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0.0
    audio = bool(re.search(r'Stream #\S+.*: Audio:', text))
    return {'width': width, 'height': height, 'fps': fps, 'duration': duration, 'audio': audio}


def rate_expr(fps):
    text = ('%.3f' % fps).rstrip('0').rstrip('.')
    return _COMMON.get(text, text)


def rate_value(expr):
    """Numeric frames per second for an ffmpeg rate such as '24' or '30000/1001'."""
    try:
        if '/' in str(expr):
            num, den = str(expr).split('/')
            return round(float(num) / float(den), 3)
        return round(float(expr), 3)
    except (ValueError, ZeroDivisionError):
        return None


def double_rate(expr):
    if '/' in expr:
        num, den = expr.split('/')
        return '%d/%s' % (int(num) * 2, den)
    return ('%.3f' % (float(expr) * 2)).rstrip('0').rstrip('.')


class _Drain(threading.Thread):
    """Keeps a child's stderr pipe empty; remembers the tail for error reports."""
    def __init__(self, stream):
        super().__init__(daemon=True); self.stream = stream; self.tail = b''; self.start()

    def run(self):
        for chunk in iter(lambda: self.stream.read(4096), b''):
            self.tail = (self.tail + chunk)[-2000:]

    def text(self):
        return self.tail.decode('utf-8', 'replace').strip().splitlines()[-1:] or ['']


def nvenc_ok(ffmpeg):
    try:
        p = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=black:s=256x256:d=0.2', '-c:v', 'h264_nvenc', '-f', 'null', '-'],
                           capture_output=True, timeout=30)
        return p.returncode == 0
    except Exception:
        return False


def run_video(req):
    import torch
    import numpy as np
    from torch.nn import functional as F
    ffmpeg = req['ffmpeg']; src = req['input']
    device = pick_device(req.get('device', 'auto')); half = device == 'cuda'
    dtype = torch.float16 if half else torch.float32
    torch.set_num_threads(max(1, int(req.get('threads') or 2)))
    info = video_info(ffmpeg, src)
    w, h = info['width'], info['height']
    emit(stage='loading', device=device, source=info)
    upscaler = load_upscaler(req['upscale'], device, half) if req.get('upscale') else None
    rife = load_rife(req['interpolate'], device, half) if req.get('interpolate') else None
    if not upscaler and not rife:
        raise RuntimeError('Choose upscaling, smoother motion or both')
    if upscaler:
        out_h = min(int(req.get('height') or h * 2), h * 4)
        out_h -= out_h % 2
        out_w = int(round(w * out_h / h / 2)) * 2
    else:
        out_w, out_h = w - w % 2, h - h % 2
    in_rate = rate_expr(info['fps']); out_rate = double_rate(in_rate) if rife else in_rate
    total = max(1, round(info['duration'] * info['fps'])) if info['duration'] else 0
    tile = int(req.get('tile') or 0) or (0 if device == 'cuda' and w * h <= 1280 * 720 else 512)
    decoder = subprocess.Popen([ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-i', src, '-map', '0:v:0',
                                '-an', '-sn', '-dn', '-vf', 'fps=' + in_rate, '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    dec_err = _Drain(decoder.stderr)
    audio = req.get('audio') or (src if info['audio'] else None)
    codec = ['-c:v', 'h264_nvenc', '-preset', 'p5', '-tune', 'hq', '-rc', 'vbr', '-cq', '19', '-b:v', '0'] \
        if device == 'cuda' and nvenc_ok(ffmpeg) else ['-c:v', 'libx264', '-preset', req.get('preset', 'faster'), '-crf', '17']
    part = req['output'] + '.part.mp4'
    cmd = [ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
           '-s', '%dx%d' % (out_w, out_h), '-framerate', out_rate, '-i', 'pipe:0']
    if audio:
        cmd += ['-i', audio, '-map', '0:v:0', '-map', '1:a:0?', '-c:a', 'aac', '-b:a', '192k']
    else:
        cmd += ['-map', '0:v:0']
    cmd += codec + ['-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p', '-colorspace', 'bt709',
                    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart', part]
    encoder = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    enc_err = _Drain(encoder.stderr)
    frames = queue.Queue(maxsize=6); failure = []

    def writer():
        try:
            while True:
                data = frames.get()
                if data is None:
                    break
                encoder.stdin.write(data)
        except (BrokenPipeError, OSError) as exc:
            failure.append(exc)
        finally:
            try: encoder.stdin.close()
            except OSError: pass
    out_thread = threading.Thread(target=writer, daemon=True); out_thread.start()

    def put(t):
        if failure:
            raise RuntimeError('Encoder stopped: ' + enc_err.text()[0])
        frames.put(t.clamp(0, 1).mul(255).round().to(torch.uint8)[0].permute(1, 2, 0).contiguous().cpu().numpy().tobytes())

    pad_unit = 64 if out_h > 1080 else 32
    rife_scale = (8, 4, 2) if out_h > 1080 else (4, 2, 1)
    ph, pw = -(-out_h // pad_unit) * pad_unit, -(-out_w // pad_unit) * pad_unit

    def interpolate(a, b):
        small_a = F.interpolate(a, size=(36, 64), mode='area'); small_b = F.interpolate(b, size=(36, 64), mode='area')
        change = float((small_a - small_b).abs().mean())
        if change < .002 or change > .16:  # static shot or scene cut: no ghosting
            return a
        pa = F.pad(a, (0, pw - out_w, 0, ph - out_h)); pb = F.pad(b, (0, pw - out_w, 0, ph - out_h))
        return rife(pa, pb, scale=rife_scale)[:, :, :out_h, :out_w]

    frame_bytes = w * h * 3; buf = bytearray(frame_bytes); view = memoryview(buf)
    done = 0; started = time.monotonic(); prev = None
    emit(stage='processing', done=0, total=total, out_width=out_w, out_height=out_h, out_fps=rate_value(out_rate))
    try:
        with torch.inference_mode():
            while True:
                got = 0
                while got < frame_bytes:
                    n = decoder.stdout.readinto(view[got:])
                    if not n:
                        break
                    got += n
                if got < frame_bytes:
                    break
                x = torch.frombuffer(buf, dtype=torch.uint8).view(h, w, 3).to(device).permute(2, 0, 1).unsqueeze(0).to(dtype) / 255
                if upscaler:
                    try:
                        y = sr_x4(upscaler, x, tile)
                    except RuntimeError as exc:
                        if 'out of memory' not in str(exc).lower() or tile == 256:
                            raise
                        if device == 'cuda':
                            torch.cuda.empty_cache()
                        tile = 256; y = sr_x4(upscaler, x, tile)
                    if y.shape[2] != out_h or y.shape[3] != out_w:
                        y = F.interpolate(y.float(), size=(out_h, out_w), mode='bicubic', antialias=True, align_corners=False).to(dtype)
                else:
                    y = x[:, :, :out_h, :out_w]
                if rife:
                    if prev is not None:
                        put(prev); put(interpolate(prev, y))
                    prev = y
                else:
                    put(y)
                done += 1
                elapsed = max(.001, time.monotonic() - started); speed = done / elapsed
                emit(force=False, stage='processing', done=done, total=max(total, done), fps=round(speed, 2),
                     eta=round(max(0, total - done) / speed) if total else None)
            if done == 0:
                raise RuntimeError('Could not decode the video: ' + dec_err.text()[0])
            if prev is not None:
                put(prev); put(prev)
    finally:
        frames.put(None); out_thread.join()
        if decoder.poll() is None:
            decoder.kill()
        decoder.wait()
    emit(stage='encoding', done=done, total=done)
    code = encoder.wait()
    if code or failure:
        try: os.remove(part)
        except OSError: pass
        raise RuntimeError('Video encoding failed: ' + enc_err.text()[0])
    os.replace(part, req['output'])
    emit(stage='done', result=req['output'], frames=done, width=out_w, height=out_h, fps=rate_value(out_rate))


def main():
    if '--probe' in sys.argv:
        print(json.dumps(probe())); return 0
    try:
        req = json.loads(sys.stdin.readline())
        if req.get('mode') == 'image':
            run_image(req)
        elif req.get('mode') == 'video':
            run_video(req)
        else:
            raise RuntimeError('Unknown AI job')
        return 0
    except Exception as exc:
        text = str(exc) or exc.__class__.__name__
        if 'out of memory' in text.lower():
            text = 'Not enough memory for this resolution; choose a lower target'
        emit(stage='error', error=text[:400])
        return 1


if __name__ == '__main__':
    sys.exit(main())
