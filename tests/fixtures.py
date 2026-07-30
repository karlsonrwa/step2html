"""Coloured STEP assemblies built from nothing, so the suite carries no
binary fixtures and still exercises the paths that have actually broken.

The shapes are deliberately dull. What matters is the SHAPE OF THE DATA: a
part with a colour of its own, one face inside it painted differently, and a
second part placed away from the origin by a transform. Every colour bug this
tool has had needed exactly that combination to show up.
"""
from __future__ import annotations

from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

# What the fixture is painted with, as the sRGB bytes the reader must recover.
BODY = (0x1A, 0x59, 0x24)      # the box
RIM = (0xF2, 0x94, 0x40)       # one face of the box, painted over the body
PIN = (0xB8, 0x73, 0x33)       # the cylinder
PIN_AT = (40.0, 5.0, 2.0)      # and where it is placed


def _q(rgb):
    return Quantity_Color(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0,
                          Quantity_TypeOfColor.Quantity_TOC_sRGB)


def _faces(shape):
    out = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        out.append(TopoDS.Face_s(exp.Current()))
        exp.Next()
    return out


def coloured_assembly(path: Path) -> Path:
    """Write a two-part assembly: a box with one odd face, and a placed pin."""
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    assembly = shape_tool.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString("fixture"))

    box = BRepPrimAPI_MakeBox(60.0, 30.0, 1.6).Shape()
    box_label = shape_tool.AddShape(box, False)
    TDataStd_Name.Set_s(box_label, TCollection_ExtendedString("board"))
    color_tool.SetColor(box_label, _q(BODY), XCAFDoc_ColorType.XCAFDoc_ColorSurf)
    # One face painted over the part colour - the case that was silently lost
    # for a whole round, because a colour is found by the identity of a face.
    color_tool.SetColor(_faces(box)[0], _q(RIM), XCAFDoc_ColorType.XCAFDoc_ColorSurf)

    pin = BRepPrimAPI_MakeCylinder(1.5, 6.0).Shape()
    pin_label = shape_tool.AddShape(pin, False)
    TDataStd_Name.Set_s(pin_label, TCollection_ExtendedString("pin"))
    color_tool.SetColor(pin_label, _q(PIN), XCAFDoc_ColorType.XCAFDoc_ColorSurf)

    shape_tool.AddComponent(assembly, box_label, TopLoc_Location())
    moved = gp_Trsf()
    moved.SetTranslation(gp_Vec(*PIN_AT))
    shape_tool.AddComponent(assembly, pin_label, TopLoc_Location(moved))
    shape_tool.UpdateAssemblies()

    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    if not writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs):
        raise RuntimeError("could not transfer the fixture")
    if writer.Write(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError(f"could not write {path}")
    return path
