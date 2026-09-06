"""The mesh from OCCT in one piece: the document written as binary glTF by
OCCT itself, and the arrays read straight out of it with numpy.

Why. Tessellating by hand asks OCP for every node and every triangle one
call at a time - Node, X, Y, Z, Triangle, Get - and on a 525k-node board
those calls were 10 s of a 48 s build, with the arithmetic around them under
a second. RWGltf_CafWriter writes the very same triangulations, all of them,
in 1.6 s, and numpy reads the buffers back in 0.2 s (docs/performance.md).

What comes back is per PRIMITIVE, one per face, grouped per mesh instance in
the order the scene names them - measured on a 6,614-face board to be
exactly the order faces() walks the faces of the parts collect_parts
returns, with exactly their node counts, positions within a float32 of the
doubles, and the first triangle the same three nodes. None of that is taken
on trust: tessellate checks every face by count and by its first node before
using a primitive, and takes the face node by node when the check fails.

Positions are in each part's own frame - the instance placement is what the
glTF node carries, and tessellate applies it in double from the part's own
location - and float32, which is what glTF stores. So the payload differs
from the node walk by a float32 rounding of the world coordinate, no more.

The file. The writer knows nothing but a path, so a build writes a .glb -
18 MB for the board above - and reads it back at once. It goes beside the
result when that folder can be written to, and to the system temp folder
otherwise: the result's folder is where the user has put the work, and a
system temp folder on a small SSD is where nobody wants 50 MB a build.
"""
from __future__ import annotations

import json
import os
import struct
import tempfile
from pathlib import Path

import numpy as np

from ._occt import (Message_ProgressRange, RWGltf_CafWriter,
                    RWMesh_CoordinateSystem, TCollection_AsciiString,
                    TColStd_IndexedDataMapOfStringString)

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
DTYPE = {5121: "<u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
TRIANGLES = 4


def export_mesh(doc, workdir=None):
    """The document's triangulations -> [instance, ...] in scene order, each
    a list of (positions (n, 3) float32, triangles (m, 3) int64) per face, in
    face order. None when the writer declines, which tessellate treats as
    "walk every face by hand".

    Millimetres in and out, Z up on both sides: the writer's defaults are
    metres and Y up, which is right for a glTF viewer and wrong for a payload
    that is compared to the B-rep.
    """
    path = _scratch_path(workdir)
    try:
        writer = RWGltf_CafWriter(TCollection_AsciiString(str(path)), True)
        conv = writer.ChangeCoordinateSystemConverter()
        conv.SetInputLengthUnit(0.001)
        conv.SetOutputLengthUnit(0.001)
        conv.SetInputCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup)
        conv.SetOutputCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup)
        if not writer.Perform(doc, TColStd_IndexedDataMapOfStringString(),
                              Message_ProgressRange()):
            return None
        data = path.read_bytes()
    except Exception:
        return None
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    return parse_glb(data)


def _scratch_path(workdir) -> Path:
    """A file of our own in *workdir*, or in the system temp folder when that
    folder is missing or refuses; created empty so the name is ours."""
    for folder in (workdir, None):
        try:
            fd, name = tempfile.mkstemp(suffix=".glb", prefix="step2html-",
                                        dir=str(folder) if folder else None)
            os.close(fd)
            return Path(name)
        except OSError:
            continue
    raise OSError("no folder to write the mesh export to")


def parse_glb(data: bytes):
    """A binary glTF -> [instance, ...] as export_mesh describes. Only the
    triangle primitives; a writer that ever adds lines or points is ignored
    here rather than misread."""
    magic, _version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        return None
    view = memoryview(data)
    chunks = {}
    o = 12
    while o + 8 <= length:
        clen, ctype = struct.unpack_from("<II", data, o)
        chunks[ctype] = view[o + 8:o + 8 + clen]
        o += 8 + clen
    if JSON_CHUNK not in chunks or BIN_CHUNK not in chunks:
        return None
    meta = json.loads(bytes(chunks[JSON_CHUNK]))
    binary = chunks[BIN_CHUNK]
    views, accessors = meta.get("bufferViews", []), meta.get("accessors", [])

    def array(index):
        acc = accessors[index]
        bv = views[acc["bufferView"]]
        offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        count = acc["count"] * WIDTH[acc["type"]]
        return np.frombuffer(binary, dtype=DTYPE[acc["componentType"]],
                             count=count, offset=offset).reshape(acc["count"], -1)

    def primitives(mesh_index):
        out = []
        for prim in meta["meshes"][mesh_index].get("primitives", []):
            if prim.get("mode", TRIANGLES) != TRIANGLES or "indices" not in prim:
                continue
            positions = array(prim["attributes"]["POSITION"])
            triangles = array(prim["indices"]).reshape(-1, 3).astype(np.int64)
            out.append((positions, triangles))
        return out

    # Instances in scene order, depth first: a mesh used twice is two
    # instances, one per node, which is one per entry of collect_parts.
    nodes = meta.get("nodes", [])
    instances = []

    def walk(index):
        node = nodes[index]
        if "mesh" in node:
            instances.append(primitives(node["mesh"]))
        for child in node.get("children", []):
            walk(child)

    scenes = meta.get("scenes", [])
    roots = scenes[meta.get("scene", 0)].get("nodes", []) if scenes else []
    for root in roots:
        walk(root)
    return instances
