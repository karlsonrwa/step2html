"""Reading the STEP, and finding the colours in it.

Colours are read per FACE, falling back to the part, so boardMode "layers"
comes out coloured by layer kind the way it does in the STEP. See the notes
on each function: several of the obvious simplifications here are wrong,
and each one was found by a board coming out grey.
"""
from __future__ import annotations

from pathlib import Path

from . import ConvertError
from ._occt import (IFSelect_ReturnStatus, Quantity_Color,
                    STEPCAFControl_Reader, TCollection_AsciiString,
                    TCollection_ExtendedString, TDataStd_Name, TDF_Label,
                    TDF_LabelSequence, TDF_Tool, TDocStd_Document,
                    TopLoc_Location, XCAFApp_Application, XCAFDoc_ColorType,
                    XCAFDoc_DocumentTool)


DEFAULT_RGB = (170, 170, 170)


def read_step(path: Path):
    """-> an XCAF document. ConvertError, and never SystemExit.

    SystemExit derives from BaseException, so neither `except ConvertError`
    nor `except Exception` in the worker catches it: a STEP that OCCT refuses
    to read killed the child process with nothing said, and the window then
    reported the one thing it knows about a silent death - "usually a crash
    inside OCCT" - which is both alarming and wrong. The CLI is unchanged,
    because main() turns a ConvertError into the same SystemExit it was.
    """
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    if reader.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ConvertError(f"could not read {path} - is it a STEP file?")
    if not reader.Transfer(doc):
        raise ConvertError(f"could not transfer the contents of {path}")
    return doc


def label_name(label: TDF_Label) -> str:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def srgb_byte(v: float) -> int:
    """OCCT hands back LINEAR components. Encode to sRGB so the byte matches
    the #RRGGBB the STEP was written with - read raw, #B87333 copper arrives
    as (122, 44, 8). The shader linearises again before lighting."""
    s = 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055
    return max(0, min(255, round(s * 255)))


def get_color(color_tool, shape, fallback):
    """Colour of a SHAPE, Surf then Gen, else the fallback.

    By shape, not by label: OCP binds only the TopoDS_Shape overload of
    GetColor, and GetColor_s is the unrelated "this label IS a colour entry"
    call. Passing a label raises TypeError - and an except that swallows it
    paints the whole board grey, which is exactly how this was first written.
    """
    if shape is None or shape.IsNull():
        return fallback
    col = Quantity_Color()
    for kind in (XCAFDoc_ColorType.XCAFDoc_ColorSurf,
                 XCAFDoc_ColorType.XCAFDoc_ColorGen):
        if color_tool.GetColor(shape, kind, col):
            return tuple(srgb_byte(v) for v in (col.Red(), col.Green(), col.Blue()))
    return fallback


def collect_parts(doc):
    """[(name, rgb, shape IN ITS OWN FRAME, location to the world)].

    The shape is deliberately NOT moved into place here. XCAF finds a colour
    by the identity of the shape, and a moved copy is a different object: on
    the m_custom test board all 69 faces resolve on the stored shape and NONE
    of them resolve after .Moved(), which paints the whole board one colour -
    board rim and every component alike. So the location travels alongside
    and gets applied to the tessellated points instead.
    """
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    out = []

    def walk(label, loc, inherited, name_hint):
        shape = shape_tool.GetShape_s(label)
        colour = get_color(color_tool, shape, inherited)
        name = label_name(label) or name_hint
        if shape_tool.IsAssembly_s(label):
            comps = TDF_LabelSequence()
            shape_tool.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                comp = comps.Value(i)
                sub_loc = loc.Multiplied(shape_tool.GetLocation_s(comp))
                sub_col = instance_color(color_tool, shape_tool, comp, colour)
                ref = TDF_Label()
                if shape_tool.GetReferredShape_s(comp, ref):
                    walk(ref, sub_loc, sub_col, label_name(comp) or name)
                else:
                    walk(comp, sub_loc, sub_col, name)
            return
        if shape is None or shape.IsNull():
            return
        out.append((name, colour, shape, loc))

    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), TopLoc_Location(), DEFAULT_RGB, f"part{i}")
    return out, color_tool


def instance_color(color_tool, shape_tool, comp_label, fallback):
    """Colour set on one PLACEMENT of a shared part, if there is one.

    Same part used twice with two colours is legal in XCAF, and that override
    lives on the component label, not on the part - GetInstanceColor is the
    only way to it.
    """
    shape = shape_tool.GetShape_s(comp_label)
    if shape is None or shape.IsNull():
        return fallback
    col = Quantity_Color()
    for kind in (XCAFDoc_ColorType.XCAFDoc_ColorSurf,
                 XCAFDoc_ColorType.XCAFDoc_ColorGen):
        try:
            if color_tool.GetInstanceColor(shape, kind, col):
                return tuple(srgb_byte(v)
                             for v in (col.Red(), col.Green(), col.Blue()))
        except Exception:
            break
    return fallback


def colour_lookup(color_tool):
    """The one question the rest of the pipeline asks of XCAF, as a function.

    tessellate and repair_parts want "the colour on THIS shape, or nothing",
    and nothing else about the document. Handing them this instead of the
    colour tool is what lets them be read, tested and carried elsewhere
    without XCAF in the room.
    """
    return lambda shape: get_color(color_tool, shape, None)
