"""Launch the private installed runtime without inheriting bundle DLL paths."""
import os
import subprocess
import sys
from pathlib import Path


def launch_installed(root):
    root = Path(root)
    python = root / "runtime/pythonw.exe"
    script = root / "app/ultron_entry.py"
    if not python.is_file() or not script.is_file():
        raise RuntimeError("A instalação está incompleta. Execute o Setup novamente.")
    from core.app_paths import data_root
    env = os.environ.copy()
    env.pop("PYTHONPATH", None); env.pop("PYTHONHOME", None)
    # The installed runtime must not load Qt plugins/DLLs from this onefile
    # setup's temporary directory, which disappears when the setup exits.
    for name in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(name, None)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        prefix = os.path.normcase(os.path.abspath(bundle))
        env["PATH"] = os.pathsep.join(part for part in env.get("PATH", "").split(os.pathsep)
            if not (os.path.normcase(os.path.abspath(part)) == prefix or
                    os.path.normcase(os.path.abspath(part)).startswith(prefix + os.sep)))
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(data_root() / "browsers")
    # PyInstaller modifies the Windows DLL search path; children inherit it.
    # Restore it immediately after spawning so the setup can continue using Qt.
    if os.name == "nt" and bundle:
        import ctypes
        set_directory = ctypes.windll.kernel32.SetDllDirectoryW
        set_directory.argtypes = [ctypes.c_wchar_p]
        set_directory.restype = ctypes.c_int
        if not set_directory(None):
            raise ctypes.WinError()
        try:
            subprocess.Popen([str(python), str(script)], cwd=root / "app", env=env,
                             close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            set_directory(str(bundle))
    else:
        subprocess.Popen([str(python), str(script)], cwd=root / "app", env=env,
                         close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
