"""Single dispatch point for the Keeper entry script.

QML is the primary UI (``python main.py`` / ``password-manager``); the
pre-QML widgets implementation stays available as a fallback via
``KEEPER_UI=widgets`` until it is retired.
"""

from __future__ import annotations

import os


def main() -> None:
    if os.environ.get("KEEPER_UI") == "widgets":
        from password_manager.app import main as widgets_main
        widgets_main()
    else:
        from password_manager.app_qml import main as qml_main
        qml_main()


if __name__ == "__main__":
    main()
