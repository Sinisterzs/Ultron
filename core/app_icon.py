"""The same bundled icon for the app, splash and standalone setup windows."""
from core.app_paths import resource_root


def apply_app_icon(app):
    from PyQt6.QtGui import QIcon
    root = resource_root()
    # Bootstrap bundles the source payload in a separate resource subtree.
    for path in (root / "config/jarvis.ico", root / "payload/app/config/jarvis.ico"):
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                app.setWindowIcon(icon)
                return True
    return False
