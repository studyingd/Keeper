"""Prune Qt modules the app never loads from a frozen Keeper bundle.

PyInstaller's PySide6 QtQml hook collects *every* QML plugin directory in the
PySide6 wheel, and each plugin drags in its Qt DLLs - including a 194 MB
Qt6WebEngineCore.dll for a WebEngine this app never opens. Keeper's QML only
imports QtQuick, QtQuick.Controls.Basic, QtQuick.Layouts and QtQuick.Dialogs,
so everything else under PySide6/qml (and the DLLs only those modules load)
can go.

Usage:
    python scripts/trim_dist.py <path-to-_internal-or-.app>

Safe by construction: only names on the explicit kill lists below are
removed, and the build scripts smoke-test the exe right after. If a future
QML file grows a new import (say QtQuick.Shapes), add its module to
QML_KEEP and its DLL pattern to the keep side, then rebuild.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# QML import trees Keeper actually uses (import QtQuick / .Controls.Basic /
# .Layouts / .Dialogs; qml/Qt and qml/QtQml are the mandatory base).
QML_KEEP = {"Qt", "QtQml", "QtQuick"}

# QtQuick/Controls style directories; QQuickStyle.setStyle("Basic") pins the
# style, the others are dead weight (FluentWinUI3 alone is ~3.4 MB).
CONTROLS_STYLE_KEEP = {"Basic"}

# Qt DLL families reachable only from the removed QML modules. Matched as
# substrings against the file stem, case-insensitive.
DLL_KILL_SUBSTRINGS = (
    "3d",  # Qt63DCore, Qt63DRender, Qt6Quick3D*, ... (not QuickShapes2!)
    "webengine",
    "webchannel",
    "websockets",
    "webview",
    "charts",
    "datavisualization",
    "graphs",
    "graphsutils",
    "multimedia",
    "spatialaudio",
    "pdf",
    "scxml",
    "sensors",
    "positioning",
    "location",
    "remoteobjects",
    "texttospeech",
    "quicktest",
    "6test",  # Qt6Test.dll (stem qt6test; "qttest" would not match)
    "labs_folderlistmodel",
    "labs_sharedimage",
    "labs_wavefrontmesh",
)

# Deliberately kept despite looking removable:
# - opengl32sw.dll  : software-GL fallback for Qt Quick on RDP / GPU-less boxes
# - Qt6Labs*.dll    : Quick.Dialogs' style machinery may pull LabsStyleKit
# - Qt6Sql.dll      : small, and referenced from the Qt plugin registry
# - translations/   : locale data, a few MB, harmless

# Python packages pulled in only through optional import chains:
# openpyxl.drawing.image -> PIL, openpyxl.xml -> lxml, setuptools'
# distutils shim -> numpy. The export path writes plain cells and needs none.
EXCLUDE_MODULES = (
    "numpy",
    "PIL",
    "lxml",
    "setuptools",
    "lark",
    "distutils",
)


def _fmt_mb(bytes_: int) -> str:
    return f"{bytes_ / 1024 / 1024:7.1f} MB"


def prune(internal: Path) -> int:
    """Delete unneeded QML trees and Qt DLLs; return bytes freed."""
    freed = 0

    def remove(path: Path) -> None:
        nonlocal freed
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
        try:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        except OSError as error:
            print(f"  !! could not remove {path}: {error}", file=sys.stderr)
            return
        freed += size
        print(f"  {_fmt_mb(size)}  {path.relative_to(internal.parent.parent.parent) if len(path.parts) > 3 else path}")

    qml_dir = internal / "PySide6" / "qml"
    if qml_dir.is_dir():
        for entry in sorted(qml_dir.iterdir()):
            if entry.name not in QML_KEEP:
                remove(entry)
        controls = qml_dir / "QtQuick" / "Controls"
        if controls.is_dir():
            for style in sorted(controls.iterdir()):
                if style.is_dir() and style.name not in CONTROLS_STYLE_KEEP:
                    remove(style)

    # DLL families: match only inside PySide6's top level so e.g. our own
    # assets or sqlcipher3 files can never be caught by a pattern.
    pyside = internal / "PySide6"
    if pyside.is_dir():
        for dll in sorted(pyside.glob("*.dll")) + sorted(pyside.glob("*.dylib")):
            stem = dll.stem.lower()
            if any(part in stem for part in DLL_KILL_SUBSTRINGS):
                remove(dll)

    return freed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path, help="path to the bundle's _internal dir (or the .app on macOS)")
    args = parser.parse_args()

    internal = args.bundle
    if internal.suffix == ".app":  # PyInstaller .app bundles keep _internal under Contents/MacOS
        internal = internal / "Contents" / "MacOS" / "_internal"
    if not (internal / "PySide6").is_dir():
        parser.error(f"no PySide6 tree under {internal} - pass the frozen bundle's _internal directory")

    print(f"Trimming {internal} ...")
    freed = prune(internal)
    print(f"Freed {_fmt_mb(freed)} total")


if __name__ == "__main__":
    main()
