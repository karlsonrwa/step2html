"""The S3DH payload: what the geometry travels as.

One raw-deflated, base64 block with its length and CRC32 written beside it
in the page. The header is 48 bytes: the magic, the format version, seven
counts and four floats; then the arrays, in the order the counts name them.
Version 3 added the face table, version 4 the circles. The format version
answers one question only - can the viewer read these bytes at all - and
is separate from the tool version stamped on the page.
"""
from __future__ import annotations

import base64
import struct
import zlib

MAGIC = b"S3DH"
FORMAT_VERSION = 4
# Count the letters against the arguments when touching this: 4s, then
# SEVEN integers, then four floats.
HEADER = "<4sIIIIIIIffff"
HEADER_SIZE = struct.calcsize(HEADER)          # 48


def pack(pos, nrm, col, idx, epos=(), eidx=(), face_starts=(), circles=()):
    """-> (base64 payload, crc32, uncompressed length)."""
    nv = len(pos) // 3
    ni = len(idx)
    nev = len(epos) // 3
    nei = len(eidx)
    nfa = len(face_starts)
    ncr = len(circles)
    cx = (min(pos[0::3]) + max(pos[0::3])) / 2
    cy = (min(pos[1::3]) + max(pos[1::3])) / 2
    cz = (min(pos[2::3]) + max(pos[2::3])) / 2

    centred = []
    r2 = 0.0
    for i in range(nv):
        x, y, z = pos[3 * i] - cx, pos[3 * i + 1] - cy, pos[3 * i + 2] - cz
        centred.extend((x, y, z))
        r2 = max(r2, x * x + y * y + z * z)
    span = (r2 ** 0.5) or 1.0

    # Edge points ride in the same frame as the surface points.
    ecentred = []
    for i in range(nev):
        ecentred.extend((epos[3 * i] - cx, epos[3 * i + 1] - cy, epos[3 * i + 2] - cz))

    hx = (max(pos[0::3]) - min(pos[0::3])) / 2
    hy = (max(pos[1::3]) - min(pos[1::3])) / 2
    hz = (max(pos[2::3]) - min(pos[2::3])) / 2

    # Circle centres ride in the same centred frame as everything else; the
    # axis is a direction and the radius a length, so neither moves.
    flat_circles = []
    for cxc, cyc, czc, nx, ny, nz, r in circles:
        flat_circles.extend((cxc - cx, cyc - cy, czc - cz, nx, ny, nz, r))

    body = bytearray()
    # Version 3 adds nfa and the face table; version 4 adds ncr and the
    # circles. Count the letters against the arguments when touching this:
    # 4s, then SEVEN integers, then four floats.
    body += struct.pack(HEADER, MAGIC, FORMAT_VERSION, nv, ni, nev, nei,
                        nfa, ncr, span, hx, hy, hz)
    body += struct.pack(f"<{nv * 3}f", *centred)
    body += bytes(max(0, min(255, int(round(v * 127)) + 128)) for v in nrm)
    body += bytes(col)
    body += struct.pack(f"<{ni}I", *idx)
    body += struct.pack(f"<{nev * 3}f", *ecentred)
    body += struct.pack(f"<{nei}I", *eidx)
    body += struct.pack(f"<{nfa}I", *face_starts)
    body += struct.pack(f"<{ncr * 7}f", *flat_circles)

    crc = zlib.crc32(bytes(body)) & 0xFFFFFFFF
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)   # raw deflate = deflate-raw
    blob = comp.compress(bytes(body)) + comp.flush()
    return base64.b64encode(blob).decode("ascii"), crc, len(body)


def decode(b64: str) -> bytes:
    """base64 and raw deflate undone: the first thing the page does too."""
    return zlib.decompress(base64.b64decode(b64), -15)


def unpack(body: bytes) -> dict:
    """The reverse of pack.

    The page reads these bytes in JavaScript, and the two must agree on
    every offset; this is the Python half of that agreement, so a test can
    say so instead of hand-counting struct letters. Everything comes back
    as plain tuples in the same order pack was given it.
    """
    fields = struct.unpack_from(HEADER, body, 0)
    magic, version, nv, ni, nev, nei, nfa, ncr, span, hx, hy, hz = fields
    if magic != MAGIC:
        raise ValueError(f"not a payload: magic {magic!r}")
    if version != FORMAT_VERSION:
        raise ValueError(f"payload version {version}, expected {FORMAT_VERSION}")
    o = HEADER_SIZE

    def take(fmt, count, width):
        nonlocal o
        got = struct.unpack_from(f"<{count}{fmt}", body, o)
        o += count * width
        return got

    pos = take("f", nv * 3, 4)
    nrm = bytes(body[o:o + nv * 3]); o += nv * 3
    col = bytes(body[o:o + nv * 3]); o += nv * 3
    idx = take("I", ni, 4)
    epos = take("f", nev * 3, 4)
    eidx = take("I", nei, 4)
    face_starts = take("I", nfa, 4)
    flat = take("f", ncr * 7, 4)
    if o != len(body):
        raise ValueError(f"{len(body) - o} bytes after the last array")
    return {"version": version, "span": span, "half": (hx, hy, hz),
            "counts": (nv, ni, nev, nei, nfa, ncr),
            "pos": pos, "nrm": nrm, "col": col, "idx": idx,
            "epos": epos, "eidx": eidx, "face_starts": face_starts,
            "circles": [flat[i * 7:i * 7 + 7] for i in range(ncr)]}
