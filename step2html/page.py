"""The page: the viewer as a template, and the words on it.

Everything the page says is in TEXT, in one place; build_page substitutes
it and the payload into PAGE in ONE pass, so nothing substituted is ever
read as template again.
"""
from __future__ import annotations

import html
import re
from importlib import resources

from .meta import tool_version


# Everything the page says, in one place. Change the language here.
TEXT = {
    "stats": "{parts} parts · {faces} faces · {triangles} triangles",
    "old_browser": "This browser is too old: no DecompressionStream. "
                   "Needs Chrome/Edge 103+, Firefox 113+ or Safari 16.4+.",
    "no_webgl": "WebGL2 is not available in this browser.",
    "unpack_failed": "Damaged file: the model data could not be decompressed. "
                     "Get an undamaged copy.",
    "crc_failed": "Damaged file: the model checksum does not match. Nothing is "
                  "drawn, rather than drawing something untrue. Get an "
                  "undamaged copy.",
    "projection": "Projection",
    "perspective": "Perspective",
    "orthographic": "Orthographic",
    "edges": "Edges",
    "on": "On",
    "off": "Off",
    "theme": "Theme",
    "system": "System",
    "light": "Light",
    "dark": "Dark",
    "help": "Help",
    "help_title": "Controls",
    "k_rotate": "Left button, or one finger",
    "v_rotate": "Rotate",
    "k_zoom": "Wheel, or pinch",
    "v_zoom": "Zoom",
    "k_pan": "Right button, Shift-drag, or two fingers",
    "v_pan": "Pan",
    "k_click": "Single click on the model",
    "v_click": "Turn about that point from now on",
    "k_reset": "Double click",
    "v_reset": "Reset the view and the centre of rotation",
    "close": "Close",
    "about_source": "Source",
    "about_mesh": "Mesh",
    "about_made": "Made",
    "about_size": "Size",
    "k_keys": "1-8 · E · P · M",
    "v_keys": "Views, edges, projection, measure",
    "tools": "Tools",
    "measure": "Measure",
    "save_png": "Save PNG",
    "views": "Standard views",
    "view_top": "Top",
    "view_bottom": "Bottom",
    "view_front": "Front",
    "view_back": "Back",
    "view_left": "Left",
    "view_right": "Right",
    "view_iso_top": "Top isometric",
    "view_iso_bottom": "Bottom isometric",
}


def _read(name: str) -> str:
    return (resources.files("step2html").joinpath("viewer", name)
            .read_text(encoding="utf-8"))


# The template lives in three files under viewer/ - markup, stylesheet,
# script - and is put together ONCE, here, when the module is imported.
# The stylesheet and the script are the tool's own text and go in ahead of
# the one substitution pass build_page makes; only the user's values pass
# through that, which is what keeps a title from ever being read as
# template. A frozen build carries viewer/ as data (packaging/step2html.spec).
PAGE = (_read("viewer.html")
        .replace("__CSS__", _read("viewer.css"))
        .replace("__JS__", _read("viewer.js")))


def build_page(title: str, stats: dict, data: str, crc: int, raw: int,
               edge_bias: float = 1.0e-5, meta: dict | None = None) -> str:
    meta = meta or {}
    stat_line = TEXT["stats"].format(
        parts=stats["parts"], faces=stats["faces"],
        triangles=f"{stats['triangles']:,}".replace(",", "\u00a0"),
    )
    # Every substitution is escaped: a title with & or < in it would otherwise
    # break the page, and the message strings sit inside JS string literals.
    subs = {
        "__TITLE__": html.escape(title),
        "__STATS__": html.escape(stat_line),
        "__OLD_BROWSER__": js_escape(TEXT["old_browser"]),
        "__NO_WEBGL__": js_escape(TEXT["no_webgl"]),
        "__UNPACK_FAILED__": js_escape(TEXT["unpack_failed"]),
        "__CRC_FAILED__": js_escape(TEXT["crc_failed"]),
        "__CRC__": str(crc),
        "__RAW__": str(raw),
        "__EDGE_BIAS__": repr(round(edge_bias, 8)),
        "__M_GENERATOR__": html.escape(f"step2html {tool_version()}"),
        "__M_VERSION__": html.escape(f"step2html {tool_version()}"),
        "__M_SOURCE__": html.escape(meta.get("source", "")),
        "__M_MESH__": html.escape(meta.get("mesh", "")),
        "__M_MADE__": html.escape(meta.get("made", "")),
        "__L_PROJECTION__": html.escape(TEXT["projection"]),
        "__L_PERSPECTIVE__": html.escape(TEXT["perspective"]),
        "__L_ORTHOGRAPHIC__": html.escape(TEXT["orthographic"]),
        "__L_EDGES__": html.escape(TEXT["edges"]),
        "__L_ON__": html.escape(TEXT["on"]),
        "__L_OFF__": html.escape(TEXT["off"]),
        "__L_THEME__": html.escape(TEXT["theme"]),
        "__L_SYSTEM__": html.escape(TEXT["system"]),
        "__L_LIGHT__": html.escape(TEXT["light"]),
        "__L_DARK__": html.escape(TEXT["dark"]),
        "__L_HELP__": html.escape(TEXT["help"]),
        "__L_HELP_TITLE__": html.escape(TEXT["help_title"]),
        "__L_K_ROTATE__": html.escape(TEXT["k_rotate"]),
        "__L_V_ROTATE__": html.escape(TEXT["v_rotate"]),
        "__L_K_ZOOM__": html.escape(TEXT["k_zoom"]),
        "__L_V_ZOOM__": html.escape(TEXT["v_zoom"]),
        "__L_K_PAN__": html.escape(TEXT["k_pan"]),
        "__L_V_PAN__": html.escape(TEXT["v_pan"]),
        "__L_K_CLICK__": html.escape(TEXT["k_click"]),
        "__L_V_CLICK__": html.escape(TEXT["v_click"]),
        "__L_K_RESET__": html.escape(TEXT["k_reset"]),
        "__L_V_RESET__": html.escape(TEXT["v_reset"]),
        "__L_CLOSE__": html.escape(TEXT["close"]),
        "__L_ABOUT_SOURCE__": html.escape(TEXT["about_source"]),
        "__L_ABOUT_MESH__": html.escape(TEXT["about_mesh"]),
        "__L_ABOUT_MADE__": html.escape(TEXT["about_made"]),
        "__L_ABOUT_SIZE__": html.escape(TEXT["about_size"]),
        "__L_K_KEYS__": html.escape(TEXT["k_keys"]),
        "__L_V_KEYS__": html.escape(TEXT["v_keys"]),
        "__L_TOOLS__": html.escape(TEXT["tools"]),
        "__L_MEASURE__": html.escape(TEXT["measure"]),
        "__L_SAVE_PNG__": html.escape(TEXT["save_png"]),
        "__M_SIZE__": html.escape(meta.get("size", "")),
        "__L_VIEWS__": html.escape(TEXT["views"]),
        "__L_VIEW_TOP__": html.escape(TEXT["view_top"]),
        "__L_VIEW_BOTTOM__": html.escape(TEXT["view_bottom"]),
        "__L_VIEW_FRONT__": html.escape(TEXT["view_front"]),
        "__L_VIEW_BACK__": html.escape(TEXT["view_back"]),
        "__L_VIEW_LEFT__": html.escape(TEXT["view_left"]),
        "__L_VIEW_RIGHT__": html.escape(TEXT["view_right"]),
        "__L_VIEW_ISO_TOP__": html.escape(TEXT["view_iso_top"]),
        "__L_VIEW_ISO_BOTTOM__": html.escape(TEXT["view_iso_bottom"]),
        "__DATA__": data,          # base64 cannot contain < or &
    }
    # ONE pass, so nothing substituted is ever scanned again. Replacing key by
    # key in a loop lets a value contain what looks like a later placeholder
    # and be rewritten by it: a title of "__L_ON__" - and a title is user text,
    # a --title or the STEP's own stem - came out on the page as "On".
    return re.sub(r"__[A-Z_0-9]+__",
                  lambda m: subs.get(m.group(0), m.group(0)), PAGE)


def js_escape(s: str) -> str:
    """Escape for a double-quoted JS string literal inside <script>."""
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("<", "\\x3c").replace("\n", "\\n"))
