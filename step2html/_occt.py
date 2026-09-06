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
    from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import (TopAbs_EDGE, TopAbs_FACE, TopAbs_Orientation,
                            TopAbs_SOLID)
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool
except ImportError as exc:  # pragma: no cover - environment problem, not logic
    raise SystemExit(
        f"{exc}\n\nstep2html needs OCP, the OpenCASCADE bindings, and the "
        f"Python running this does not have it:\n  {sys.executable}\n\n"
        f"Either install it there:\n  pip install cadquery-ocp\n"
        f"or start this with the Python that already has it."
    )

__all__ = [
    "BRep_Tool", "BRepAdaptor_Curve", "BRepMesh_IncrementalMesh",
    "GCPnts_TangentialDeflection", "GeomAbs_CurveType", "IFSelect_ReturnStatus",
    "Bnd_Box", "BRepBndLib", "BRepBuilderAPI_Copy", "BRepGProp", "GProp_GProps",
    "BRepTools", "Quantity_Color", "ShapeUpgrade_ShapeDivideClosed",
    "STEPCAFControl_Reader", "TCollection_AsciiString",
    "TCollection_ExtendedString", "TDataStd_Name", "TDF_Label",
    "TDF_LabelSequence", "TDF_Tool", "TDocStd_Document", "TopAbs_EDGE",
    "TopAbs_FACE", "TopAbs_Orientation", "TopAbs_SOLID", "TopExp_Explorer",
    "TopLoc_Location", "TopoDS", "TopTools_IndexedMapOfShape",
    "XCAFApp_Application", "XCAFDoc_ColorType", "XCAFDoc_DocumentTool",
]
