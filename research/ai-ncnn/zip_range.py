"""Fetch single files out of a remote ZIP with HTTP Range requests.

Research prototype for the NCNN migration plan (docs/AI_NCNN_MIGRATION_PLAN.md);
it is NOT used by the player. Upstream ships the ncnn-vulkan engines only inside
big release archives (RIFE: 431 MB, most of it old models we do not need), so
the planned downloader reads the archive's central directory from its tail and
then only the members it needs, verifying CRC-32, size and SHA-256.

    python zip_range.py list URL [substring]
    python zip_range.py get  URL OUTDIR member [member ...]

Standard library only. A server that ignores Range (answers 200) is refused
instead of silently downloading the whole archive.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import urllib.request
import zlib

UA = 'KryonyxMusic-research/73 (+zip-range)'
CHUNK = 1 << 20


class RangeNotSupported(RuntimeError):
    pass


class RemoteZip:
    def __init__(self, url, timeout=30, opener=None):
        self.timeout = timeout
        self.open = (opener or urllib.request.build_opener()).open
        self.transferred = 0
        self.requests = 0
        # A 1-byte request resolves redirects and tells the total size (GitHub's
        # asset storage refuses suffix ranges like "bytes=-N" with HTTP 501);
        # then the tail holds the end-of-central-directory record.
        _, self.size, self.url = self._range(url, 0, 0)
        start = max(0, self.size - 65557)
        self.entries = self._directory(self.read(start, self.size - start))

    # ------------------------------------------------------------------ HTTP
    def _request(self, url, a, b):
        req = urllib.request.Request(url, headers={'Range': 'bytes=%d-%d' % (a, b), 'User-Agent': UA})
        resp = self.open(req, timeout=self.timeout)
        self.requests += 1
        if resp.status != 206:
            resp.close()
            raise RangeNotSupported('server ignored the Range header (HTTP %d)' % resp.status)
        total = int(resp.headers.get('Content-Range', '/0').rsplit('/', 1)[1] or 0)
        return resp, total

    def _range(self, url, a, b):
        resp, total = self._request(url, a, b)
        with resp:
            data = resp.read()
            final = resp.geturl()
        self.transferred += len(data)
        return data, total, final

    def read(self, a, n):
        return self._range(self.url, a, a + n - 1)[0]

    # ----------------------------------------------------------- directory
    def _directory(self, tail):
        at = tail.rfind(b'PK\x05\x06')
        if at < 0:
            raise ValueError('not a ZIP archive (no end of central directory)')
        count, cd_size, cd_off = struct.unpack_from('<HII', tail, at + 10)
        if 0xFFFFFFFF in (cd_size, cd_off) or count == 0xFFFF:  # ZIP64
            loc = tail.rfind(b'PK\x06\x07', 0, at)
            if loc < 0:
                raise ValueError('ZIP64 locator missing')
            (eocd64,) = struct.unpack_from('<Q', tail, loc + 8)
            rec = self.read(eocd64, 56)
            count, cd_size, cd_off = struct.unpack_from('<QQQ', rec, 32)
        cd = self.read(cd_off, cd_size)
        entries, pos = {}, 0
        for _ in range(count):
            if cd[pos:pos + 4] != b'PK\x01\x02':
                raise ValueError('broken central directory')
            (flags, method, crc, csize, usize, nlen, xlen, clen) = struct.unpack_from('<HHxxxxIIIHHH', cd, pos + 8)
            (offset,) = struct.unpack_from('<I', cd, pos + 42)
            name = cd[pos + 46:pos + 46 + nlen].decode('utf-8' if flags & 0x800 else 'cp437')
            extra = cd[pos + 46 + nlen:pos + 46 + nlen + xlen]
            if 0xFFFFFFFF in (csize, usize, offset):
                usize, csize, offset = _zip64_extra(extra, usize, csize, offset)
            if not name.endswith('/'):
                entries[name] = {'method': method, 'flags': flags, 'crc': crc, 'csize': csize, 'size': usize,
                                 'offset': offset}
            pos += 46 + nlen + xlen + clen
        return entries

    # -------------------------------------------------------------- members
    def extract(self, name, target):
        """Stream one member to `target` (via .part); returns size and SHA-256."""
        e = self.entries[name]
        if e['flags'] & 0x1:
            raise ValueError('encrypted member: ' + name)
        if e['method'] not in (0, 8):
            raise ValueError('unsupported compression %d: %s' % (e['method'], name))
        head = self.read(e['offset'], 30)
        if head[:4] != b'PK\x03\x04':
            raise ValueError('bad local header: ' + name)
        nlen, xlen = struct.unpack_from('<HH', head, 26)
        start = e['offset'] + 30 + nlen + xlen
        inflate = zlib.decompressobj(-15) if e['method'] == 8 else None
        digest, crc, size = hashlib.sha256(), 0, 0
        part = target + '.part'
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        try:
            if e['csize']:
                resp, _ = self._request(self.url, start, start + e['csize'] - 1)
            else:
                resp = None
            with open(part, 'wb') as out:
                while resp is not None:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    self.transferred += len(chunk)
                    data = inflate.decompress(chunk) if inflate else chunk
                    out.write(data); digest.update(data); crc = zlib.crc32(data, crc); size += len(data)
                    if size > e['size']:
                        raise ValueError('member is larger than declared: ' + name)
                if inflate:
                    tail = inflate.flush(); out.write(tail); digest.update(tail)
                    crc = zlib.crc32(tail, crc); size += len(tail)
            if resp is not None:
                resp.close()
            if size != e['size'] or crc != e['crc']:
                raise ValueError('size/CRC mismatch: ' + name)
            os.replace(part, target)
        finally:
            if os.path.exists(part):
                os.unlink(part)
        return {'name': name, 'size': size, 'sha256': digest.hexdigest(), 'crc32': '%08x' % crc}


def _zip64_extra(extra, usize, csize, offset):
    pos = 0
    while pos + 4 <= len(extra):
        tag, ln = struct.unpack_from('<HH', extra, pos)
        if tag == 1:
            vals, at = [], pos + 4
            for cur in (usize, csize, offset):
                if cur == 0xFFFFFFFF:
                    (v,) = struct.unpack_from('<Q', extra, at); at += 8; vals.append(v)
                else:
                    vals.append(cur)
            return tuple(vals)
        pos += 4 + ln
    raise ValueError('ZIP64 extra field missing')


def main(argv):
    if len(argv) < 2 or argv[0] not in ('list', 'get'):
        print(__doc__); return 2
    z = RemoteZip(argv[1])
    if argv[0] == 'list':
        sub = argv[2] if len(argv) > 2 else ''
        rows = {k: {'size': v['size'], 'csize': v['csize']} for k, v in z.entries.items() if sub in k}
        print(json.dumps({'archive_size': z.size, 'members': len(z.entries), 'match': rows,
                          'transferred': z.transferred, 'requests': z.requests}, indent=1))
        return 0
    outdir, names = argv[2], argv[3:]
    got = [z.extract(n, os.path.join(outdir, n.replace('\\', '/'))) for n in names]
    print(json.dumps({'archive_size': z.size, 'files': got, 'transferred': z.transferred,
                      'requests': z.requests}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
