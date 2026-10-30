"""Update trust, staging, rollback, parent wait and Qt behavior regressions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from core import updates, update_apply as apply, update_download as download


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"ULTRON_DATA_DIR": str(self.base/"data")})
        self.env.start()
        self.root = self.base/"Programs/ULTRON"
        self.root.mkdir(parents=True)
        (self.root/"install_state.json").write_text('{"version":1}')
        (self.root/"old.txt").write_text("old install")
        for name in ("runtime/pythonw.exe", "app/ultron_entry.py", "ULTRON.exe"):
            item=self.root/name;item.parent.mkdir(parents=True,exist_ok=True);item.write_text("old component")
        self.setup = self.base/"download.exe"; self.setup.write_bytes(b"setup fixture")

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def prepare(self, emit, cancel, *, target):
        self.assertTrue((self.root/"old.txt").is_file())
        for name in ("runtime/pythonw.exe", "app/ultron_entry.py"):
            p=target/name; p.parent.mkdir(parents=True,exist_ok=True);p.write_text("new")

    def swap(self, prepare=None):
        with patch.object(apply, "installation_root", return_value=self.root):
            return apply.stage_and_swap(self.root, lambda *args:None,
                prepare=prepare or self.prepare, setup=self.setup)

    def test_staging_preserves_user_data_and_old_install(self):
        personal=self.base/"data/config/api_keys.json"
        personal.parent.mkdir(parents=True);personal.write_bytes(b"protected fixture")
        backup=self.swap()
        self.assertEqual((self.root/"old.txt").read_text(),"old install")
        self.assertEqual((backup/"app/ultron_entry.py").read_text(),"old component")
        self.assertEqual((self.root/"app/ultron_entry.py").read_text(),"new")
        self.assertEqual(personal.read_bytes(),b"protected fixture")
        self.assertEqual((self.root/"install_state.json").read_text(),'{"version":1}')
        self.assertFalse((self.base/"data/updates/pending.json").exists())

    def test_prepare_failure_never_replaces_current_install(self):
        def fail(*args, **kwargs):raise RuntimeError("network fixture failed")
        with self.assertRaises(RuntimeError):
            self.swap(fail)
        self.assertEqual((self.root/"old.txt").read_text(),"old install")
        self.assertFalse(list(self.root.parent.glob(".ULTRON-backup-*")))

    def test_promotion_failure_restores_original(self):
        rename=Path.rename
        def fail_stage(path, target):
            if path.parent.name.startswith(".ULTRON-stage-") and path.name == "runtime":
                raise OSError("locked fixture")
            return rename(path,target)
        with patch.object(Path,"rename",fail_stage), self.assertRaises(OSError):
            self.swap()
        self.assertEqual((self.root/"old.txt").read_text(),"old install")
        self.assertTrue((self.root/"install_state.json").exists())

    def test_cancel_before_swap_keeps_current_install(self):
        def cancel_prepare(emit,cancel,*,target):
            self.prepare(emit,cancel,target=target)
            stop.set()
        stop=threading.Event()
        with patch.object(apply,"installation_root",return_value=self.root):
            with self.assertRaises(Exception):
                apply.stage_and_swap(self.root,lambda *a:None,stop.is_set,
                                     prepare=cancel_prepare,setup=self.setup)
        self.assertTrue((self.root/"old.txt").is_file())

    def test_interrupted_first_rename_is_recovered(self):
        backup=self.root.parent/".ULTRON-backup-fixture"
        self.root.rename(backup)
        stage=self.root.parent/".ULTRON-stage-fixture"
        journal=self.base/"data/updates/pending.json"
        journal.parent.mkdir(parents=True)
        journal.write_text(json.dumps({"root":str(self.root),"backup":str(backup),"stage":str(stage)}))
        with patch.object(apply,"installation_root",return_value=self.root):
            apply.recover_interrupted()
        self.assertTrue((self.root/"old.txt").exists())
        self.assertFalse(journal.exists())

    def test_download_requires_exact_github_asset_and_digest(self):
        url="https://github.com/owner/repo/releases/download/v2.0.0/ULTRON-Setup.exe"
        asset={"name":"ULTRON-Setup.exe","browser_download_url":url,"digest":"sha256:"+"a"*64,"size":100}
        payload={"tag_name":"v2.0.0","assets":[asset]}
        release=updates.parse_release(payload,"owner/repo","1.0.0")
        self.assertEqual(release.sha256,"a"*64)
        asset["browser_download_url"]="https://example.invalid/malware.exe"
        self.assertEqual(updates.parse_release(payload,"owner/repo","1.0.0").installer_url,"")
        asset["browser_download_url"]=url;asset["digest"]=""
        self.assertEqual(updates.parse_release(payload,"owner/repo","1.0.0").installer_url,"")

    def test_tampered_download_never_executes(self):
        release=updates.Release("2.0.0","https://github.com/owner/repo","https://github.com/owner/repo/releases/download/v2.0.0/ULTRON-Setup.exe","0"*64)
        with patch.object(download,"installed_root",return_value=self.root), \
             patch.object(download,"download_verified",return_value=self.setup), \
             patch.object(download.subprocess,"Popen") as process:
            with self.assertRaises(ValueError):
                download.download_and_handoff(release,lambda *a:None)
            process.assert_not_called()
        self.assertTrue((self.root/"old.txt").exists())

    def test_verified_helper_ready_returns_before_app_is_closed(self):
        digest=hashlib.sha256(self.setup.read_bytes()).hexdigest()
        release=updates.Release("2.0.0","https://github.com/owner/repo","https://github.com/owner/repo/releases/download/v2.0.0/ULTRON-Setup.exe",digest)
        from unittest.mock import MagicMock
        def spawn(command, **kwargs):
            request=Path(command[2])
            self.assertEqual(json.loads(request.read_text())["parent_pid"],os.getpid())
            (request.parent/"ready").touch()
            child=MagicMock();child.poll.return_value=None
            return child
        with patch.object(download,"installed_root",return_value=self.root), \
             patch.object(download,"download_verified",return_value=self.setup), \
             patch.object(download.subprocess,"Popen",side_effect=spawn):
            folder=download.download_and_handoff(release,lambda *args:None)
        self.assertTrue((folder/"ready").exists())
        self.assertFalse((folder/"proceed").exists())
        self.assertTrue((self.root/"old.txt").is_file())

    def test_download_completion_never_launches_helper(self):
        digest=hashlib.sha256(self.setup.read_bytes()).hexdigest()
        release=updates.Release("2.0.0","https://github.com/owner/repo","https://github.com/owner/repo/releases/download/v2.0.0/ULTRON-Setup.exe",digest)
        with patch.object(download,"installed_root",return_value=self.root), \
             patch.object(download,"download_verified",return_value=self.setup), \
             patch.object(download.subprocess,"Popen") as spawn:
            prepared=download.download_update(release,lambda *a:None)
            spawn.assert_not_called()
            self.assertEqual(prepared.path,self.setup)
            self.assertFalse(list((self.base/"data/updates").glob("*/request.json")))

    def test_delayed_restart_rechecks_download_hash(self):
        release=updates.Release("2.0.0","https://github.com/owner/repo","fixture","0"*64)
        prepared=download.DownloadedUpdate(release,self.base,self.root,self.setup)
        with patch.object(download,"installed_root",return_value=self.root), \
             patch.object(download.subprocess,"Popen") as spawn:
            with self.assertRaises(ValueError):download.start_update(prepared,lambda *a:None)
            spawn.assert_not_called()

    @unittest.skipUnless(os.name=="nt","Windows directory handle")
    def test_container_can_stay_open_during_component_promotion(self):
        import time
        ready=self.base/"child-ready"
        child=subprocess.Popen([sys.executable,"-c","import pathlib,sys,time;pathlib.Path(sys.argv[1]).touch();time.sleep(10)",str(ready)],cwd=self.root,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline=time.monotonic()+5
            while not ready.exists() and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(ready.exists())
            backup=self.swap()
            self.assertIsNone(child.poll())
            self.assertEqual((self.root/"app/ultron_entry.py").read_text(),"new")
            self.assertEqual((backup/"app/ultron_entry.py").read_text(),"old component")
        finally:
            child.terminate();child.wait(timeout=5)

    def test_recovery_restores_partially_promoted_components(self):
        backup=self.root.parent/".ULTRON-backup-fixture";backup.mkdir()
        stage=self.root.parent/".ULTRON-stage-fixture";stage.mkdir()
        (self.root/"app").rename(backup/"app")
        (self.root/"app").mkdir();(self.root/"app/ultron_entry.py").write_text("new")
        journal=self.base/"data/updates/pending.json";journal.parent.mkdir(parents=True)
        journal.write_text(json.dumps({"schema":2,"root":str(self.root),"backup":str(backup),"stage":str(stage)}))
        with patch.object(apply,"installation_root",return_value=self.root):apply.recover_interrupted()
        self.assertEqual((self.root/"app/ultron_entry.py").read_text(),"old component")
        self.assertEqual((stage/"app/ultron_entry.py").read_text(),"new")

    def test_failure_at_each_component_move_restores_old_files(self):
        rename=Path.rename
        for name in apply.COMPONENTS:
            for phase in ("backup", "promote"):
                with self.subTest(component=name, phase=phase):
                    def fail_once(path,target):
                        is_target=(path==self.root/name if phase=="backup" else path.parent.name.startswith(".ULTRON-stage-") and path.name==name)
                        if is_target and not failed[0]:
                            failed[0]=True
                            raise OSError("injected move failure")
                        return rename(path,target)
                    failed=[False]
                    with patch.object(Path,"rename",fail_once),self.assertRaises(OSError):self.swap()
                    for relative in ("app/ultron_entry.py","runtime/pythonw.exe","ULTRON.exe"):
                        self.assertEqual((self.root/relative).read_text(),"old component")

    def test_request_must_be_in_dedicated_update_folder(self):
        path=self.base/"request.json";path.write_text("{}")
        with self.assertRaises(ValueError):apply.validate_request(path)

    @unittest.skipUnless(os.name=="nt","Windows process handle")
    def test_real_parent_process_wait_uses_handle_without_killing(self):
        request=self.base/"request.json";request.touch()
        process=subprocess.Popen([sys.executable,"-c","import time;time.sleep(0.7)"],
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            apply.wait_for_app(request,process.pid,lambda *a:None,timeout=5)
            process.wait(timeout=2)
            self.assertEqual(process.returncode,0)
            self.assertTrue((self.base/"ready").exists())
        finally:
            if process.poll() is None:process.kill();process.wait()

    def test_missing_shutdown_confirmation_prevents_apply(self):
        request=self.base/"request.json";request.touch()
        with patch.object(apply,"validate_request",return_value=(request,{"parent_pid":1,"root":str(self.root)})), \
             patch.object(apply,"wait_for_app"), patch.object(apply,"stage_and_swap") as swap:
            with self.assertRaises(RuntimeError):apply.apply_request(request,lambda *a:None)
            swap.assert_not_called()


class UpdateQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"]="offscreen"
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_toast_never_downloads_without_click(self):
        from ui_updates import UpdateToast
        from PyQt6.QtCore import Qt
        release=updates.Release("2.0.0","https://github.com/owner/repo","https://github.com/owner/repo/releases/download/v2.0.0/ULTRON-Setup.exe","a"*64)
        with patch.object(download,"installed_root",return_value=Path("fixture")), \
             patch.object(download,"download_and_handoff") as fetch:
            toast=UpdateToast(release)
            events=[];toast.updateRequested.connect(events.append)
            toast.show();self.app.processEvents()
            self.assertEqual(events,[])
            self.assertTrue(toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
            toast.action.click();self.app.processEvents()
            self.assertEqual(events,[release])
            fetch.assert_not_called()
            toast.close()

    def test_ready_prompt_only_restarts_after_separate_click(self):
        from ui_updates import UpdateToast
        release=updates.Release("2.0.0","https://github.com/owner/repo","fixture","a"*64)
        with patch.object(download,"installed_root",return_value=Path("fixture")):
            toast=UpdateToast(release);events=[]
            toast.restartRequested.connect(lambda:events.append("restart"))
            toast.show_ready();toast.show();self.app.processEvents()
            self.assertEqual(events,[])
            self.assertEqual(toast.action.text(),"Reiniciar agora")
            toast.later.click();self.app.processEvents()
            self.assertEqual(events,[])
            self.assertFalse(toast.isVisible())
            toast.show();toast.action.click();self.app.processEvents()
            self.assertEqual(events,["restart"])
            toast.close()

    def test_controller_waits_for_restart_choice_and_helper_readiness(self):
        from PyQt6.QtWidgets import QMainWindow,QWidget
        from ui_updates import UpdateController
        window=QMainWindow();window.setCentralWidget(QWidget());window._ready=True
        release=updates.Release("2.0.0","https://github.com/owner/repo","fixture","a"*64)
        with tempfile.TemporaryDirectory() as folder, patch.object(download,"installed_root",return_value=Path(folder)), \
             patch("ui_updates.threading.Thread"):
            window.show();controller=UpdateController(window);controller._show(release)
            with patch.object(window,"close") as close:
                controller.toast.action.click()
                prepared=download.DownloadedUpdate(release,Path(folder),Path(folder),Path(folder)/"setup.exe")
                controller._download_ready(prepared)
                close.assert_not_called()
                self.assertIn("Quer reiniciar",controller.toast.status.text())
                controller.toast.later.click()
                close.assert_not_called()
                self.assertFalse(controller.toast.isVisible())
                controller.pending_button.click()
                self.assertTrue(controller.toast.isVisible())
                controller.toast.action.click()
                close.assert_not_called()
                controller.download_worker.ready.emit(Path(folder))
                close.assert_called_once()
                self.assertTrue((Path(folder)/"proceed").exists())
            window.close();window.deleteLater();self.app.processEvents()

    def test_checks_repeat_and_never_overlap(self):
        from PyQt6.QtWidgets import QMainWindow,QWidget
        from ui_updates import UpdateController,ReleaseWorker
        window=QMainWindow();window.setCentralWidget(QWidget());window._ready=True
        controller=UpdateController(window)
        with patch.object(ReleaseWorker,"start") as start:
            controller.start()
            self.assertTrue(controller.timer.isActive())
            self.assertEqual(controller.timer.interval(),300000)
            controller._check();controller._check()
            self.assertEqual(start.call_count,1)
            controller._check_finished()
            controller._check()
            self.assertEqual(start.call_count,2)
        controller.timer.stop();window.close();window.deleteLater()
