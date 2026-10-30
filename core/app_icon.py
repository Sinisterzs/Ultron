"""Separate application and setup branding, in source and frozen bundles."""
from core.app_paths import resource_root


def apply_app_icon(app, *, setup=False):
    from PyQt6.QtGui import QIcon
    root = resource_root()
    # Bootstrap bundles the source payload in a separate resource subtree.
    name = "setup.ico" if setup else "jarvis.ico"
    for path in (root / "config" / name, root / "payload/app/config" / name):
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                app.setWindowIcon(icon)
                return True
    return False
