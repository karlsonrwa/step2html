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

import numpy as np

MAGIC = b"S3DH"
FORMAT_VERSION = 4
# Count the letters against the arguments when touching this: 4s, then
# SEVEN integers, then four floats.
HEADER = "<4sIIIIIIIffff"
HEADER_SIZE = struct.calcsize(HEADER)          # 48


def pack(pos, nrm, col, idx, epos=(), eidx=(), face_starts=(), circles=()):
    """-> (base64 payload, crc32, uncompressed length).

    The arrays go through numpy: the centring, the float32 conversion, the
    normals quantised to a byte and the indices to uint32 are each one
    call over the whole array instead of a Python loop over every value.
    The bytes are the ones struct.pack produced before - the float32
    rounding is the same C cast, np.rint rounds half to even as round()
    does - and the golden payload holds that (docs/performance.md, where
    the 25 MB board measured 3.6 s -> 2.6 s for this).
    """
    P = np.asarray(pos, dtype=np.float64).reshape(-1, 3)
    E = np.asarray(epos, dtype=np.float64).reshape(-1, 3)
    nv = len(P)
    ni = len(idx)
    nev = len(E)
    nfa = len(face_starts)
    ncr = len(circles)
    lo = P.min(axis=0) if nv else np.zeros(3)
    hi = P.max(axis=0) if nv else np.zeros(3)
    centre = (lo + hi) / 2
    hx, hy, hz = (hi - lo) / 2

    centred = P - centre
    r2 = ((centred[:, 0] * centred[:, 0] + centred[:, 1] * centred[:, 1]
           + centred[:, 2] * centred[:, 2]).max() if nv else 0.0)
    span = (float(r2) ** 0.5) or 1.0

    # Edge points ride in the same frame as the surface points, and so do
    # the circle centres; a circle's axis is a direction and its radius a
    # length, so neither moves.
    ecentred = E - centre
    cx, cy, cz = centre
    flat_circles = []
    for cxc, cyc, czc, nx, ny, nz, r in circles:
        flat_circles.extend((cxc - cx, cyc - cy, czc - cz, nx, ny, nz, r))

    # Version 3 adds nfa and the face table; version 4 adds ncr and the
    # circles. Count the letters against the arguments when touching this:
    # 4s, then SEVEN integers, then four floats.
    body = b"".join((
        struct.pack(HEADER, MAGIC, FORMAT_VERSION, nv, ni, nev, len(eidx),
                    nfa, ncr, span, hx, hy, hz),
        centred.astype("<f4").tobytes(),
        np.clip(np.rint(np.asarray(nrm, dtype=np.float64) * 127) + 128,
                0, 255).astype(np.uint8).tobytes(),
        bytes(col),
        np.asarray(idx, dtype="<u4").tobytes(),
        ecentred.astype("<f4").tobytes(),
        np.asarray(eidx, dtype="<u4").tobytes(),
        np.asarray(face_starts, dtype="<u4").tobytes(),
        np.asarray(flat_circles, dtype=np.float64).astype("<f4").tobytes(),
    ))

    crc = zlib.crc32(body) & 0xFFFFFFFF
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)   # raw deflate = deflate-raw
    blob = comp.compress(body) + comp.flush()
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
