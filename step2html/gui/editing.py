"""Editing a text field: a right-click menu, and Ctrl+C/V/X/A whatever the
keyboard layout. Mirrors Simple 3D's window (stepbuilder/gui.py, rounds 78
and 83), for the same two reasons.

Tk's Entry and Text know the keyboard shortcuts but offer no menu of their
own on Windows, and a path is the one thing everyone pastes.

And the shortcuts themselves are bound to the KEYSYM - the Latin letter - so
under a Russian, or any non-Latin, layout the same key produces Cyrillic_ve
(or "??", which is what Tk 9.0 reports), the binding does not match, and the
key is swallowed by the class's own <Control-KeyPress> no-op. Measured on
this Tk with the layout really switched, on every field of the window
(tests/test_editing.py). The virtual-key code (event.keycode) names the
PHYSICAL key whatever the layout - 67 is the C key, 86 the V key - so the
handler goes by that and generates the virtual event Tk would have. Two
refusals keep it honest: when the keysym IS the Latin letter of the key,
Tk's own binding has already run and this declines - or every paste would
happen twice; and a key that typed a printable character (AltGr is Ctrl+Alt
on some layouts) is not a shortcut. The widget binding runs before the class
binding and returns "break", so the class's no-op never sees the key.

Nothing here knows the window: attach() takes the widget and a callable that
says whether the field is frozen - a build running - and that is all.
"""
from __future__ import annotations

import tkinter as tk

LAYOUT_BLIND_KEYS = {67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>", 65: "<<SelectAll>>"}

EDIT_MENU = (("Cut", "<<Cut>>"), ("Copy", "<<Copy>>"), ("Paste", "<<Paste>>"),
             (None, None), ("Select all", "<<SelectAll>>"))


def layout_blind_shortcut(event):
    """Ctrl+C/V/X/A by physical key; "break" when it acted, None to let Tk on."""
    keycode = getattr(event, "keycode", None)
    action = LAYOUT_BLIND_KEYS.get(keycode)
    if action is None:
        return None
    if str(getattr(event, "keysym", "")).lower() == chr(keycode).lower():
        return None                       # a Latin layout: Tk's own binding handles it
    char = getattr(event, "char", "") or ""
    if char.isprintable() and char.strip():
        return None                       # the key typed a character, not a control
    event.widget.event_generate(action)
    return "break"


def edit_menu(widget) -> tk.Menu:
    """The menu for *widget*, built fresh: it is four entries, and a menu
    that outlives the click would have to be told when the field is frozen."""
    menu = tk.Menu(widget.winfo_toplevel(), tearoff=0)
    for label, event in EDIT_MENU:
        if label is None:
            menu.add_separator()
            continue
        menu.add_command(label=label,
                         command=lambda w=widget, e=event: (w.focus_set(), w.event_generate(e)))
    return menu


def show_edit_menu(event, widget, frozen) -> tk.Menu | None:
    """Pop the menu at the click - or nothing while the field is frozen: a
    build is running, the field takes no edits, so no menu either."""
    if frozen():
        return None
    menu = edit_menu(widget)
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()
    return menu


def attach_shortcuts(widget) -> None:
    """Ctrl+C/V/X/A whatever the layout, and no menu: for a read-only Text
    such as the log, where Copy and Select all are what matters and Cut and
    Paste do nothing, exactly as Tk's own would."""
    widget.bind("<Control-KeyPress>", layout_blind_shortcut)


def attach(widget, frozen=lambda: False) -> None:
    """The right-click menu and the layout-blind shortcuts, on a field that
    can be edited."""
    widget.bind("<Button-3>", lambda event, w=widget: show_edit_menu(event, w, frozen))
    attach_shortcuts(widget)
