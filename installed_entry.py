"""Small installed executable: launch the private runtime, keeping the app icon."""
from pathlib import Path
import sys

from core.installed_launcher import launch_installed


def main():
    try:
        launch_installed(Path(sys.executable).resolve().parent)
        return 0
    except (OSError, RuntimeError):
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                "Não foi possível abrir o ULTRON. Execute o Setup novamente para reparar a instalação.",
                "ULTRON", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
