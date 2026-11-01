"""Mark LVI — D20O.4, launcher de inicialização em processo separado.

Executar na raiz do projeto: python launcher.py
Requer PyQt6 e o Mark LVI completo instalado na mesma pasta.
Inicia main.py e espera sinal real de que a janela principal foi exibida.
O assistente de voz pode continuar conectando depois que o HUD aparece.
Inclui verificação e aplicação de atualizações diretamente pelo launcher.
"""
from __future__ import annotations

import math
import sys
import time
import os
import json
import subprocess
import tempfile
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient, QPolygonF, QFont, QDesktopServices
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton

RED = QColor('#ff304d')
PALE = QColor('#ff9aa9')
DIM = QColor('#82515a')


class Launcher(QWidget):
    ready = pyqtSignal()  # for integration; NOT emitted by demo sequence
    _update_status_signal = pyqtSignal(str, object)
    _check_finished_signal = pyqtSignal(object, str)
    _download_finished_signal = pyqtSignal(object, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('ULTRON — Boot Launcher')
        self.setFixedSize(540, 375)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_origin = None
        self._start = time.perf_counter()
        self._status = 'Preparando processo principal'
        self._progress = None  # None => indeterminate, not fake completion percentage
        # Display only actual reported bootstrap phases, no simulated percentages.
        self._boot_stage = "starting"
        self._boot_history = []
        self._last_boot_stage = None
        self._record_boot_stage("starting", "Iniciando processo")
        self._demo_index = -1
        self._demo_stages = [
            ('Verificando configurações · demonstração', 12),
            ('Preparando núcleo · demonstração', 32),
            ('Inicializando áudio · demonstração', 57),
            ('Preparando módulos · demonstração', 78),
            ('Interface pronta · demonstração', 100),
        ]
        self._anim = QTimer(self)
        self._anim.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim.timeout.connect(self.update)
        self._anim.start(33)
        self._demo_timer = QTimer(self)
        self._demo_timer.setInterval(750)
        self._demo_timer.timeout.connect(self._next_demo)

        self.close_btn = QPushButton('×', self)
        self.close_btn.setGeometry(496, 16, 26, 26)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet('QPushButton { background: transparent; color: #92606a; border: 0; font-size: 24px; } QPushButton:hover { color: #ff576d; }')
        self.close_btn.clicked.connect(self.close)

        self.update_btn = QPushButton('PROCURAR ATUALIZAÇÃO', self)
        self.update_btn.setGeometry(318, 18, 170, 22)
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.setStyleSheet('''
            QPushButton {
                background: #0d0407;
                border: 1px solid #4a1520;
                border-radius: 3px;
                color: #ff4d66;
                font: 9px "Consolas";
                font-weight: bold;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background: #200810;
                border-color: #ff304d;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #ff304d;
                color: #000000;
            }
            QPushButton:disabled {
                background: #080305;
                border-color: #240b10;
                color: #55333b;
            }
        ''')
        self.update_btn.clicked.connect(self._on_update_btn_clicked)

        self.action_btn = QPushButton('BUSCAR ATUALIZAÇÕES PARA REPARAR', self)
        self.action_btn.setGeometry(110, 336, 320, 26)
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setStyleSheet('''
            QPushButton {
                background: #140508;
                border: 1px solid #7c2133;
                border-radius: 4px;
                color: #ff4d66;
                font: 10px "Consolas";
                font-weight: bold;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: #280812;
                border-color: #ff304d;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #ff304d;
                color: #000000;
            }
            QPushButton:disabled {
                background: #0a0305;
                border-color: #2b0b12;
                color: #55333b;
            }
        ''')
        self.action_btn.clicked.connect(self._on_action_btn_clicked)
        self.action_btn.hide()

        self.demo_btn = QPushButton('DEMONSTRAR SEQUÊNCIA', self)
        self.demo_btn.setGeometry(173, 309, 194, 28)
        self.demo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.demo_btn.setStyleSheet('QPushButton { color: #ff7788; background: #10070a; border: 1px solid #54202a; font: 10px "Consolas"; } QPushButton:hover { background: #260b13; border-color: #ff304d; } QPushButton:disabled { color: #55333b; }')
        self.demo_btn.clicked.connect(self.start_demo)
        # Integrated build: launch only via Qt's event loop, after the splash appears.
        self.demo_btn.hide()

        # Update controller state
        self._updating = False
        self._available_release = None
        self._update_stop = threading.Event()
        self._update_status_signal.connect(self._on_update_status)
        self._check_finished_signal.connect(self._on_check_finished)
        self._download_finished_signal.connect(self._on_download_finished)

        self._child = None
        self._status_file = None
        self._hud_ready = False
        self._closing_intentionally = False
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._poll_child)
        self._poll.start()
        QTimer.singleShot(0, self._launch_main)

    def _launch_main(self):
        from core.app_paths import resource_root, child_command
        root = resource_root()
        main_file = root / "main.py"
        if not getattr(sys, "frozen", False) and not main_file.is_file():
            self.set_status("ERRO: main.py não encontrado na pasta", None)
            self._poll.stop()
            self._show_error_recovery()
            return
        # Unique file: a stale status from a previous launch cannot fake readiness.
        fd, name = tempfile.mkstemp(prefix="mark_lvi_boot_", suffix=".json")
        os.close(fd)
        self._status_file = Path(name)
        env = os.environ.copy()
        env["MARK_LVI_BOOT_STATUS"] = name
        self._record_boot_stage("imports", "Carregando módulos")
        self.set_status("Carregando módulos do Mark LVI", None)
        try:
            self._child = subprocess.Popen(child_command(),
                                           cwd=str(root), env=env)
        except Exception as exc:
            self.set_status(f"ERRO ao iniciar: {exc}", None)
            self._show_error_recovery()

    def _poll_child(self):
        if self._child is not None and self._child.poll() is not None:
            self._poll.stop()
            if not self._hud_ready:
                self.set_status(f"ERRO: processo encerrou ({self._child.returncode})", None)
                self._show_error_recovery()
            self._cleanup_status()
            return
        path = self._status_file
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        stage = data.get("stage")
        status = data.get("text", "Inicializando")
        if stage and stage != self._last_boot_stage:
            self._record_boot_stage(stage, str(status))
        if stage == "hud_shown":
            self._hud_ready = True
            self.set_status("HUD pronto", 100)
            self._poll.stop()
            self._cleanup_status()
            QTimer.singleShot(250, self.close)
        elif stage == "error":
            self.set_status("ERRO: " + str(status)[:45], None)
            self._poll.stop()
            self._show_error_recovery()
        else:
            self.set_status(status, None)

    def _show_error_recovery(self):
        if not self._updating and self._available_release is None:
            self.action_btn.setText("BUSCAR ATUALIZAÇÕES PARA REPARAR")
            self.action_btn.show()

    def _record_boot_stage(self, stage: str, status: str):
        """Store real bootstrap events in a small, capped visual history."""
        labels = {
            "starting": "Iniciando processo",
            "imports": "Carregando módulos",
            "creating_hud": "Construindo HUD",
            "hud_constructed": "Interface construída",
            "qt_starting": "Inicializando animações",
            "hud_shown": "Interface exibida",
            "error": "Falha na inicialização",
        }
        self._last_boot_stage = stage
        self._boot_stage = stage
        self._boot_history.append((stage, labels.get(stage, status[:22])))
        self._boot_history = self._boot_history[-4:]
        self.update()

    def _cleanup_status(self):
        path = self._status_file
        self._status_file = None
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def closeEvent(self, event):
        self._poll.stop()
        self._update_stop.set()
        # Never leave an invisible orphan Mark LVI if the splash is cancelled.
        if not self._hud_ready and self._child is not None and self._child.poll() is None:
            try:
                self._child.terminate()
            except OSError:
                pass
        self._cleanup_status()
        super().closeEvent(event)

    def set_status(self, text: str, progress: float | None = None):
        """External integration API. progress is 0..100 or None (unknown)."""
        self._status = str(text)
        self._progress = None if progress is None else max(0.0, min(100.0, float(progress)))
        self.update()

    def set_ready(self):
        """For actual integration ONLY; demo deliberately never triggers real readiness."""
        self.set_status('SISTEMA PRONTO', 100)
        self.ready.emit()

    def start_demo(self):
        self._demo_timer.stop()
        self._demo_index = -1
        self.demo_btn.setEnabled(False)
        self._next_demo()
        self._demo_timer.start()

    def _next_demo(self):
        self._demo_index += 1
        if self._demo_index >= len(self._demo_stages):
            self._demo_timer.stop()
            self.demo_btn.setEnabled(True)
            self.demo_btn.setText('REPETIR DEMONSTRAÇÃO')
            return
        status, percentage = self._demo_stages[self._demo_index]
        self.set_status(status, percentage)

    # ── Update management from Launcher ─────────────────────────────────────────

    def _on_update_btn_clicked(self):
        if self._available_release is not None:
            self._start_update_download(self._available_release)
        else:
            self._start_update_check()

    def _on_action_btn_clicked(self):
        if self.action_btn.text() == "ABRIR RELEASES NO GITHUB":
            try:
                from core.updates import read_release_config
                repo = read_release_config().get("github_repository", "Sinisterzs/Ultron")
            except Exception:
                repo = "Sinisterzs/Ultron"
            QDesktopServices.openUrl(QUrl(f"https://github.com/{repo}/releases"))
            return
        if self._available_release is not None:
            self._start_update_download(self._available_release)
        else:
            self._start_update_check()

    def _start_update_check(self):
        if self._updating:
            return
        self._updating = True
        self._available_release = None
        self._update_stop.clear()
        self.update_btn.setText("VERIFICANDO...")
        self.update_btn.setEnabled(False)
        self.action_btn.setText("VERIFICANDO SERVIDORES...")
        self.action_btn.setEnabled(False)
        self.action_btn.show()
        self.set_status("Consultando atualizações no GitHub...", None)

        def worker():
            try:
                from core.updates import check_release
                release = check_release(force=True)
                self._check_finished_signal.emit(release, "")
            except Exception as exc:
                self._check_finished_signal.emit(None, str(exc))

        threading.Thread(target=worker, daemon=True, name="launcher-update-check").start()

    def _on_check_finished(self, release, err: str):
        self._updating = False
        self.update_btn.setEnabled(True)
        self.action_btn.setEnabled(True)

        if err:
            self.set_status(f"Falha ao verificar: {err[:36]}", None)
            self.update_btn.setText("PROCURAR ATUALIZAÇÃO")
            self.action_btn.setText("TENTAR NOVAMENTE")
            return

        if release is None:
            self.set_status("Você já está na versão mais recente.", None)
            self.update_btn.setText("PROCURAR ATUALIZAÇÃO")
            self.action_btn.setText("ABRIR RELEASES NO GITHUB")
            return

        self._available_release = release
        self.set_status(f"Nova versão v{release.version} disponível!", 0)
        self.update_btn.setText("BAIXAR ATUALIZAÇÃO")
        self.action_btn.setText(f"BAIXAR E ATUALIZAR (v{release.version})")

    def _start_update_download(self, release):
        if self._updating:
            return
        downloadable = bool(release.installer_url and release.sha256)
        if downloadable:
            try:
                from core.update_download import installed_root
                installed_root()
            except Exception:
                downloadable = False

        if not downloadable:
            QDesktopServices.openUrl(QUrl(release.url))
            self.set_status("Página de download aberta no navegador.", None)
            self.update_btn.setText("PROCURAR ATUALIZAÇÃO")
            self.action_btn.setText("ABRIR RELEASES NO GITHUB")
            self._available_release = None
            return

        self._updating = True
        self._update_stop.clear()
        self.update_btn.setText("BAIXANDO...")
        self.update_btn.setEnabled(False)
        self.action_btn.setText("BAIXANDO INSTALADOR...")
        self.action_btn.setEnabled(False)
        self.set_status(f"Baixando v{release.version}...", 0)

        # Terminate child process if still running to release locks
        if self._child is not None and self._child.poll() is None:
            try:
                self._child.terminate()
            except OSError:
                pass

        def worker():
            try:
                from core.update_download import download_update, start_update
                def on_progress(text, current, total):
                    pct = (current * 100 / total) if total else None
                    self._update_status_signal.emit(f"Baixando: {int(pct or 0)}%", pct)

                prepared = download_update(release, on_progress, self._update_stop.is_set)
                self._update_status_signal.emit("Iniciando instalador...", 100)
                folder = start_update(prepared, on_progress, self._update_stop.is_set)
                self._download_finished_signal.emit(folder, "")
            except Exception as exc:
                from core.install_manager import redact_install_output
                self._download_finished_signal.emit(None, redact_install_output(str(exc)))

        threading.Thread(target=worker, daemon=True, name="launcher-update-download").start()

    def _on_update_status(self, text: str, progress: object):
        self.set_status(text, progress)

    def _on_download_finished(self, folder, err: str):
        self._updating = False
        self.update_btn.setEnabled(True)
        self.action_btn.setEnabled(True)

        if err:
            self.set_status(f"Erro no download: {err[:36]}", None)
            self.update_btn.setText("PROCURAR ATUALIZAÇÃO")
            self.action_btn.setText("TENTAR NOVAMENTE")
            return

        if folder is not None:
            (folder / "proceed").touch()
            self.set_status("Reiniciando para aplicar a atualização...", 100)
            self.update_btn.setText("REINICIANDO...")
            self.update_btn.setEnabled(False)
            self.action_btn.setText("APLICANDO ATUALIZAÇÃO...")
            self.action_btn.setEnabled(False)
            QTimer.singleShot(600, self.close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    @staticmethod
    def _text(p, x, y, txt, size, color, bold=False, center=False):
        p.setPen(QColor(color))
        f = QFont('Consolas', size)
        f.setBold(bold)
        p.setFont(f)
        if center:
            from PyQt6.QtGui import QFontMetrics
            x -= QFontMetrics(f).horizontalAdvance(txt) / 2
        p.drawText(QPointF(x, y), txt)

    def paintEvent(self, event):
        t = time.perf_counter() - self._start
        h = self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Outer frame and pitch-black interior; no backdrop glow outside the crystal area.
        p.setPen(QPen(QColor('#491522'), 1))
        p.setBrush(QColor('#000000'))
        p.drawRoundedRect(QRectF(1, 1, 538, h - 2), 9, 9)

        p.setPen(QPen(QColor('#7c2133'), 1.4))
        for ox, oy, sx, sy in [(15, 15, 1, 1), (525, 15, -1, 1), (15, h - 14, 1, -1), (525, h - 14, -1, -1)]:
            p.drawLine(QPointF(ox, oy), QPointF(ox + 18*sx, oy))
            p.drawLine(QPointF(ox, oy), QPointF(ox, oy + 13*sy))

        self._text(p, 27, 34, 'ULTRON', 12, '#ff445b', True)
        self._text(p, 95, 34, '//  BOOT SEQUENCE', 9, '#665159')
        p.setPen(QPen(QColor('#210c13'), 1))
        p.drawLine(28, 48, 512, 48)

        cx, cy = 270.0, 147.0
        pulse = 0.85 + .15 * math.sin(t * 1.7)
        # Soft local red light, red doesn't wash the surrounding void.
        halo = QRadialGradient(QPointF(cx, cy), 90)
        halo.setColorAt(0, QColor(255, 25, 51, int(72 * pulse)))
        halo.setColorAt(.35, QColor(185, 9, 35, int(27 * pulse)))
        halo.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QRectF(cx - 90, cy - 90, 180, 180))

        # Smooth ellipses in opposite directions; this is a lightweight visual emblem.
        p.save()
        p.translate(cx, cy)
        for width, height, angle, a in [(168, 56, t*17, 105), (163, 48, -t*22+53, 65)]:
            p.save()
            p.rotate(angle)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(235, 39, 69, a), 1.0))
            p.drawEllipse(QRectF(-width/2, -height/2, width, height))
            p.restore()

        # Faceted ruby, subtle breathing; sharp geometry is intentional.
        s = 1.0 + .035 * math.sin(t*1.8)
        top = QPointF(0, -61*s)
        left = QPointF(-34*s, -13*s)
        right = QPointF(34*s, -13*s)
        mid = QPointF(0, 4*s)
        lower_left = QPointF(-27*s, 24*s)
        lower_right = QPointF(26*s, 24*s)
        bottom = QPointF(0, 62*s)
        faces = [
            ([top, left, mid], '#a1112b'),
            ([top, mid, right], '#ff3553'),
            ([left, lower_left, mid], '#4c0817'),
            ([right, mid, lower_right], '#970c27'),
            ([mid, lower_left, bottom], '#7c0a22'),
            ([mid, bottom, lower_right], '#d21b3b'),
        ]
        p.setPen(QPen(QColor('#e83c55'), .9))
        for vertices, color in faces:
            p.setBrush(QColor(color))
            p.drawPolygon(QPolygonF(vertices))
        p.setPen(QPen(QColor(255, 161, 178, 125), 1))
        p.drawLine(top, mid)
        p.drawLine(mid, bottom)
        p.restore()

        # Status centralizado sob a barra
        self._text(p, 270, 232, 'INITIALIZING SYSTEM', 12, '#ff4b64', True, center=True)
        self._text(p, 33, 265, 'BOOTSTRAP STATUS', 8, '#72525a')
        if self._progress is not None:
            self._text(p, 495, 265, f'{int(self._progress):d}%', 9, '#ff5268', center=True)
        else:
            self._text(p, 495, 265, '...', 9, '#ff5268', center=True)
        bar = QRectF(33, 274, 474, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#2c0e17'))
        p.drawRoundedRect(bar, 2, 2)
        if self._progress is None:
            track = 88
            pos = (t * 95) % (474 + track) - track
            left_bound = max(33, 33 + pos)
            right_bound = min(507, 33 + pos + track)
            if right_bound > left_bound:
                p.fillRect(QRectF(left_bound, 274, right_bound-left_bound, 5), QColor('#ff304d'))
        elif self._progress > 0:
            p.setBrush(QColor('#ff304d'))
            p.drawRoundedRect(QRectF(33, 274, 474 * self._progress/100, 5), 2, 2)

        stage_titles = {
            'starting': 'Iniciando processo',
            'imports': 'Carregando módulos',
            'creating_hud': 'Construindo interface principal',
            'hud_constructed': 'Interface construída',
            'qt_starting': 'Preparando interface',
            'hud_shown': 'Interface pronta',
            'error': 'Falha na inicialização',
        }
        stage_details = {
            'starting': 'Preparando o processo do Mark LVI',
            'imports': 'Importando módulos e dependências',
            'creating_hud': 'Criando HUD e componentes visuais',
            'hud_constructed': 'Aguardando a primeira exibição do HUD',
            'qt_starting': 'Inicializando animações e event loop',
            'hud_shown': 'Inicialização da interface concluída',
            'error': 'Falha ao iniciar. Busque atualizações para reparar.',
        }
        stage = self._boot_stage
        is_error = stage == 'error' or self._status.startswith('ERRO:')
        title = self._status if is_error else stage_titles.get(stage, self._status)
        detail = stage_details.get(stage, self._status)
        if not is_error and self._status and self._status not in (title, 'HUD pronto'):
            detail = self._status
        self._text(p, 270, 302, title[:52], 10,
                   '#ff657a' if not is_error else '#ff334e', True, center=True)
        if detail != title:
            self._text(p, 270, 320, detail[:60], 8, '#8c6670', center=True)
        p.end()


def main():
    app = QApplication(sys.argv)
    from core.app_icon import apply_app_icon
    apply_app_icon(app)
    app.setQuitOnLastWindowClosed(True)
    window = Launcher()
    window.show()
    screen = window.screen()
    if screen:
        rect = screen.availableGeometry()
        window.move(rect.center().x()-window.width()//2, rect.center().y()-window.height()//2)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
