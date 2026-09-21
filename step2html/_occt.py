"""Every OCP name the pipeline uses, imported once and behind one guard -
and numpy behind a guard of its own, for the same reason.

The guard names the interpreter that is running, because with several
Pythons on a machine that is the whole question - and it says "cadquery-ocp"
in the words pip wants, since "OCP" alone means nothing to pip.

Three modules use OCP - xcaf, meshing, tessellate - and each imports its
names from here rather than from OCP directly, so a missing OCP is reported
the same way whichever of them is reached first. numpy is imported where it
is used, tessellate and payload; the guard here runs first because meshing
is imported before either, and it is the message that matters.
"""
from __future__ import annotations

import importlib.util
import sys

if importlib.util.find_spec("numpy") is None:  # pragma: no cover - environment problem, not logic
    raise SystemExit(
        f"No module named 'numpy'\n\nstep2html needs numpy, which cadquery-ocp "
        f"brings with it, and the Python running this does not have it:\n  "
        f"{sys.executable}\n\nInstall it there:\n  pip install numpy"
    )

try:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.GCPnts import GCPnts_TangentialDeflection
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Message import Message_ProgressRange
    from OCP.RWGltf import RWGltf_CafWriter
    from OCP.RWMesh import RWMesh_CoordinateSystem
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.BRepTools import BRepTools
    from OCP.Quantity import Quantity_Color
    from OCP.ShapeUpgrade import ShapeUpgrade_ShapeDivideClosed
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_Tool
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import (TopAbs_EDGE, TopAbs_FACE, TopAbs_Orientation,
                            TopAbs_SOLID)
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    # TopoDS, whose casts are spelled WITHOUT the _s: 7.9 binds both Face
    # and Face_s, 8.0 only the bare one, so the bare one is the spelling
    # both understand. Every other _s in the pipeline survived 8.0 unchanged
    # - the suffix is the binding generator's way of separating a static
    # from an instance method of the same name, and TopoDS is the one class
    # here that stopped needing it.
    from OCP.TopoDS import TopoDS
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

    # The three NCollection instantiations, under their 7.9 names whichever
    # OCCT is installed. 8.0's bindings took them out of the per-package
    # modules and put every one of them in a single OCP.collections, named
    # after the template arguments instead: TDF_LabelSequence is
    # Sequence_TDF_Label there, and OCP.TDF no longer has the old name at
    # all. Bound here, so nothing downstream has to know which OCCT it got.
    #
    # The shape map is the one that needs care, because 8.0 binds TWO and
    # they are not interchangeable. IndexedMap_TopoDS_Shape keys on IsEqual,
    # which counts orientation; IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
    # keys on IsSame, which does not. 7.9's TopTools_IndexedMapOfShape is the
    # second - measured on a cube, whose 12 edges come back as 12 under the
    # hasher and as 24 under the default, because the two faces sharing an
    # edge see it with opposite orientations. collect_edges draws an edge
    # once by asking that map, so the default one would draw every shared
    # edge twice, silently and everywhere.
    try:
        from OCP.TColStd import TColStd_IndexedDataMapOfStringString
        from OCP.TDF import TDF_LabelSequence
        from OCP.TopTools import TopTools_IndexedMapOfShape
    except ImportError:
        from OCP.collections import (
            IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString
            as TColStd_IndexedDataMapOfStringString,
            IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
            as TopTools_IndexedMapOfShape,
            Sequence_TDF_Label as TDF_LabelSequence)
except ImportError as exc:  # pragma: no cover - environment problem, not logic
    # Two different failures end here, and they need different words. An
    # OCP that is installed but binds one of these names differently is not
    # "OCP is missing", and saying so sent one report in as "with a newer
    # cadquery it does not work" instead of the name of the symbol: 8.0.1
    # arrived with three renames, and this message blamed the interpreter.
    if importlib.util.find_spec("OCP") is None:
        raise SystemExit(
            f"{exc}\n\nstep2html needs OCP, the OpenCASCADE bindings, and the "
            f"Python running this does not have it:\n  {sys.executable}\n\n"
            f"Either install it there:\n  pip install cadquery-ocp\n"
            f"or start this with the Python that already has it."
        )
    import OCP as _ocp
    raise SystemExit(
        f"{exc}\n\nOCP {getattr(_ocp, '__version__', '(version unknown)')} is "
        f"installed in\n  {sys.executable}\nbut does not bind a name step2html "
        f"uses. This step2html knows the bindings of OCCT 7.7 to 8.0 "
        f"(cadquery-ocp 7.7 - 8.0.1); a newer one may have renamed it again. "
        f"Try:\n  pip install \"cadquery-ocp>=7.7,<9\""
    )

__all__ = [
    "BRep_Tool", "BRepAdaptor_Curve", "BRepMesh_IncrementalMesh",
    "GCPnts_TangentialDeflection", "GeomAbs_CurveType", "IFSelect_ReturnStatus",
    "Message_ProgressRange", "RWGltf_CafWriter", "RWMesh_CoordinateSystem",
    "TColStd_IndexedDataMapOfStringString",
    "Bnd_Box", "BRepBndLib", "BRepBuilderAPI_Copy", "BRepGProp", "GProp_GProps",
    "BRepTools", "Quantity_Color", "ShapeUpgrade_ShapeDivideClosed",
    "STEPCAFControl_Reader", "TCollection_AsciiString",
    "TCollection_ExtendedString", "TDataStd_Name", "TDF_Label",
    "TDF_LabelSequence", "TDF_Tool", "TDocStd_Document", "TopAbs_EDGE",
    "TopAbs_FACE", "TopAbs_Orientation", "TopAbs_SOLID", "TopExp_Explorer",
    "TopLoc_Location", "TopoDS", "TopTools_IndexedMapOfShape",
    "XCAFApp_Application", "XCAFDoc_ColorType", "XCAFDoc_DocumentTool",
]
