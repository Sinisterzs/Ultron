"""Single-file online installer and installed launcher shim (Windows x64)."""
from __future__ import annotations

import json
import os
import shutil
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


def main():
    if "--apply-update" in sys.argv:
        from ui_update_install import run_update
        return run_update(Path(sys.argv[sys.argv.index("--apply-update") + 1]), launch_installed)
    if "--smoke-test" in sys.argv:
        return smoke_test(Path(sys.argv[sys.argv.index("--smoke-test") + 1]))
    from core.update_apply import recover_interrupted
    recover_interrupted()
    if getattr(sys, "frozen", False) and Path(sys.executable).name.lower() == "ultron.exe":
        home = Path(sys.executable).parent
        if (home / "install_state.json").is_file():
            launch_installed(home)
            return 0
    from PyQt6.QtWidgets import QApplication
    from ui_setup import SetupOverlay
    from core import install_manager
    from core.config_store import update_config, save_config
    from core.app_paths import data_root

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from core.app_icon import apply_app_icon
    apply_app_icon(app)
    installed = {"root": None, "saved": False}

    def prepare(emit, cancel):
        if not getattr(sys, "frozen", False):
            raise RuntimeError("Execute o Setup compilado. Este modo não instala pelo código-fonte.")
        root = install_manager.install(emit, cancel, browser=window.browser_requested)
        emit("Preparando o atalho do aplicativo", 0, 0)
        # Different filename lets a downloaded Setup update the installed launcher.
        if Path(sys.executable).resolve() != (root / "ULTRON.exe").resolve():
            shutil.copy2(sys.executable, root / "ULTRON.exe")
        programs = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"
        programs.mkdir(parents=True, exist_ok=True)
        escaped = str(root / "ULTRON.exe").replace("'", "''")
        shortcut = str(programs / "ULTRON.lnk").replace("'", "''")
        icon = str(root / "app/config/jarvis.ico").replace("'", "''")
        command = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('" + shortcut + "');"
                   "$s.TargetPath='" + escaped + "';$s.IconLocation='" + icon + ",0';$s.Save()")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                       check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        installed["root"] = root

    window = SetupOverlay(preparer=prepare, preview="--preview-setup" in sys.argv)
    window.resize(960, 700)
    window.setWindowTitle("ULTRON — Instalação")

    def complete(key, os_name):
        root = installed["root"]
        if installed["saved"]:
            try:
                launch_installed(root)
                window.close()
            except Exception:
                window.show_error("Não foi possível abrir o aplicativo. Execute o Setup novamente.")
            return
        try:
            current = dict(window.settings)
            update_config(current)
            save_config({"version": current.get("onboarding_version", 1),
                         "app": "app/ultron_entry.py"}, root / "install_state.json")
            installed["saved"] = True
            window.progress_label.setText("Instalação concluída. Suas credenciais foram protegidas.")
            window.next.setText("Abrir ULTRON  →"); window.next.setEnabled(True)
            window.back.hide()
        except Exception:
            window.show_error("Não foi possível finalizar a instalação com segurança. Tente novamente.")

    window.done.connect(complete)
    window.show()
    return app.exec()


def smoke_test(output):
    """Headless executable validation: no installation, network, voice or credentials."""
    import hashlib
    output.mkdir(parents=True, exist_ok=True)
    (output / "stage.txt").write_text("Importing Qt", encoding="utf-8")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFontDatabase, QFont
    from core.app_paths import resource_root, config_path
    from ui_setup import SetupOverlay
    app = QApplication([])
    (output / "stage.txt").write_text("Qt application created", encoding="utf-8")
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ["segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"]:
        if (fonts / name).is_file():
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Segoe UI", 10)); app.setStyle("Fusion")
    before = config_path().exists()
    window = SetupOverlay(preview=True)
    (output / "stage.txt").write_text("Wizard created", encoding="utf-8")
    window.resize(960, 700); window.show(); app.processEvents()
    if not window.grab().save(str(output / "setup.png")):
        raise RuntimeError("Cannot save setup preview")
    payload = resource_root() / "payload"
    manifest = json.loads((payload / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if hashlib.sha256((payload / "app" / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Payload integrity failure")
    # Exercise the update transaction in an isolated fixture inside smoke output.
    # Never point this check at the real installed application or credentials.
    from core import update_apply
    from unittest.mock import patch
    fixture = output / "update-fixture/ULTRON"
    fixture.mkdir(parents=True)
    (fixture / "install_state.json").write_text('{"version":1}', encoding="utf-8")
    (fixture / "old.txt").write_text("old fixture", encoding="utf-8")
    for name in ("runtime/pythonw.exe", "app/ultron_entry.py", "ULTRON.exe"):
        previous = fixture / name
        previous.parent.mkdir(parents=True, exist_ok=True)
        previous.write_text("old fixture component", encoding="utf-8")
    def fixture_prepare(emit, cancel, *, target):
        for name in ("runtime/pythonw.exe", "app/ultron_entry.py"):
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("new fixture", encoding="utf-8")
    with patch.object(update_apply, "installation_root", return_value=fixture):
        backup = update_apply.stage_and_swap(fixture, lambda *args: None,
                                             prepare=fixture_prepare)
    assert (backup / "app/ultron_entry.py").is_file()
    assert (fixture / "old.txt").is_file()
    assert (fixture / "app/ultron_entry.py").is_file()
    from ui_update_install import build_update_window
    updater, status, bar, cancel, stop = build_update_window()
    status.setText("Preparando a atualização em uma pasta separada")
    updater.show(); app.processEvents()
    assert updater.grab().save(str(output / "updater.png"))
    updater.running = False; updater.close()
    assert config_path().exists() == before
    (output / "report.json").write_text(json.dumps({"frozen": bool(getattr(sys, "frozen", False)),
        "payload_files_verified": len(manifest["files"]), "configuration_created": False,
        "network_used": False, "assistant_started": False,
        "update_fixture_swap_verified": True}, indent=2), encoding="utf-8")
    window.close()
    return 0



if __name__ == "__main__":
    try:
        result = main()
    except Exception:
        if "--smoke-test" in sys.argv:
            import traceback
            path = Path(sys.argv[sys.argv.index("--smoke-test") + 1])
            path.mkdir(parents=True, exist_ok=True)
            (path / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise SystemExit(1)
        raise
    raise SystemExit(result)
