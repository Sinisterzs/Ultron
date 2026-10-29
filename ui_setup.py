"""First-run wizard. Importing this module never starts the assistant or saves data."""
from __future__ import annotations

import platform
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QUrl
from PyQt6.QtGui import QPainter, QColor, QPen, QRadialGradient, QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QFrame, QCheckBox, QScrollArea, QProgressBar,
)


class UltronRail(QFrame):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QRadialGradient(100, 40, 150)
        glow.setColorAt(0, QColor(255, 32, 52, 35)); glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), glow)
        painter.setPen(QPen(QColor("#481019"), 1))
        painter.drawLine(self.width() - 1, 70, self.width() - 1, self.height() - 70)
        painter.setPen(QPen(QColor("#ff2034"), 2))
        painter.drawLine(self.width() - 1, 105, self.width() - 1, 165)
        painter.drawLine(24, self.height() - 95, 65, self.height() - 95)
        painter.end()


class PreparationWorker(QThread):
    progress = pyqtSignal(str, int, int)
    result = pyqtSignal(bool, str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task

    def run(self):
        try:
            self.task(self.progress.emit, self.isInterruptionRequested)
            self.result.emit(True, "")
        except Exception as exc:
            self.result.emit(False, str(exc)[:250])


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None, *, preparer=None, preview=False):
        super().__init__(parent)
        self.setObjectName("SetupWizard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._sel_os = {"Windows": "windows", "Darwin": "mac"}.get(platform.system(), "linux")
        self._index = 0
        self.settings = {}
        self._preparer = preparer
        self._preview = preview
        self._worker = None
        self._preparing = False
        self._prepared = False
        self.browser_requested = False
        self.setStyleSheet("""
            QWidget#SetupWizard { background:#000000; border:1px solid #2c0d14; border-radius:16px; }
            QWidget { color:#eeeeee; font-family:'Segoe UI'; font-size:13px; }
            QFrame#Rail { background:#030303; border:0; border-radius:12px; }
            QLabel { background:transparent; border:0; }
            QLabel#Eyebrow { color:#ff2034; font-size:11px; font-weight:700; letter-spacing:2px; }
            QLabel#Heading { font-size:30px; font-weight:700; }
            QLabel#Body { color:#999999; font-size:14px; }
            QFrame#Card { background:#050505; border:1px solid #2c0d14; border-radius:10px; }
            QLineEdit { background:#000000; color:#fff; border:1px solid #401019;
                        border-radius:7px; padding:11px; font-size:14px; }
            QLineEdit:focus { border:1px solid #ff2034; }
            QPushButton { border:1px solid #351017; border-radius:7px; padding:11px 18px; background:#080808; }
            QPushButton:hover { background:#180407; }
            QPushButton#Primary { background:#e51f35; border:1px solid #e51f35; color:white; font-weight:700; }
            QPushButton#Primary:hover { background:#ff2034; }
            QPushButton:disabled { color:#555555; background:#050505; border-color:#22090d; }
            QCheckBox { color:#bbbbbb; spacing:9px; }
            QScrollArea { background:transparent; border:0; }
            QWidget#WizardPage { background:#000000; }
            QProgressBar { border:0; background:#21070c; border-radius:2px; }
            QProgressBar::chunk { background:#ff2034; border-radius:2px; }
            QScrollBar:vertical { background:#000000; width:5px; margin:0; }
            QScrollBar::handle:vertical { background:#50111c; min-height:24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:#000000; }
        """)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)
        rail = UltronRail(); rail.setObjectName("Rail"); rail.setFixedWidth(205)
        side = QVBoxLayout(rail); side.setContentsMargins(24, 30, 20, 24)
        brand = QLabel("◈  ULTRON"); brand.setStyleSheet("font-size:22px;font-weight:700;color:#ff2034")
        side.addWidget(brand)
        subtitle = QLabel("SEU ASSISTENTE.\nDO SEU JEITO.")
        subtitle.setStyleSheet("color:#777777;font-size:10px;letter-spacing:2px;line-height:160%")
        side.addWidget(subtitle); side.addSpacing(44)
        self.steps = []
        for i, title in enumerate(["Boas-vindas", "Inteligência", "Integrações", "Concluir"]):
            label = QLabel(f"{i + 1:02}   {title}"); side.addWidget(label); side.addSpacing(18)
            self.steps.append(label)
        side.addStretch()
        foot = QLabel("CONFIGURAÇÃO LOCAL\nSuas chaves ficam neste PC.")
        foot.setWordWrap(True); foot.setStyleSheet("color:#777777;font-size:11px")
        side.addWidget(foot); outer.addWidget(rail)

        main = QVBoxLayout(); main.setContentsMargins(34, 24, 26, 20); main.setSpacing(12)
        top = QLabel("PRIMEIRA INICIALIZAÇÃO"); top.setObjectName("Eyebrow"); main.addWidget(top)
        self.pages = QStackedWidget(); main.addWidget(self.pages, 1)
        self._welcome(); self._intelligence(); self._integrations(); self._review()
        self._preparation_page_index = self.pages.count()
        prep = self._page("Preparando seu ULTRON.",
                          "Baixando e instalando os componentes necessários. "
                          "Sua configuração será salva somente depois desta etapa.")
        self._card(prep, "UM AMBIENTE SÓ DO ULTRON", "As bibliotecas ficam no ambiente privado do aplicativo. "
                   "O Python de outros projetos não é alterado.")
        prep.addStretch()
        self.progress_box = QWidget()
        progress_layout = QVBoxLayout(self.progress_box); progress_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_label = QLabel("Preparando os componentes…")
        self.progress_label.setWordWrap(True); progress_layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5); progress_layout.addWidget(self.progress_bar)
        self.cancel = QPushButton("Cancelar preparação")
        self.cancel.clicked.connect(self._cancel_preparation); progress_layout.addWidget(self.cancel)
        self.log_button = QPushButton("Abrir registro de instalação")
        self.log_button.clicked.connect(self._open_install_log)
        progress_layout.addWidget(self.log_button); self.log_button.hide()
        main.addWidget(self.progress_box); self.progress_box.hide()
        self.error = QLabel(); self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#ff2034;font-size:12px"); main.addWidget(self.error)
        nav = QHBoxLayout()
        self.back = QPushButton("Voltar"); self.back.clicked.connect(self._previous)
        nav.addWidget(self.back); nav.addStretch()
        self.counter = QLabel(); self.counter.setStyleSheet("color:#666666;font-size:11px")
        nav.addWidget(self.counter); nav.addSpacing(12)
        self.next = QPushButton("Começar  →"); self.next.setObjectName("Primary")
        self.next.clicked.connect(self._advance); nav.addWidget(self.next)
        main.addLayout(nav); outer.addLayout(main, 1)
        self._display()

    def _page(self, heading, description):
        body = QWidget(); body.setObjectName("WizardPage")
        layout = QVBoxLayout(body); layout.setContentsMargins(0, 14, 0, 12)
        layout.setSpacing(18)
        title = QLabel(heading); title.setObjectName("Heading"); title.setWordWrap(True)
        layout.addWidget(title)
        text = QLabel(description); text.setObjectName("Body"); text.setWordWrap(True)
        layout.addWidget(text)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(body)
        self.pages.addWidget(scroll)
        return layout

    @staticmethod
    def _card(layout, title, description):
        card = QFrame(); card.setObjectName("Card")
        box = QVBoxLayout(card); box.setContentsMargins(18, 16, 18, 16)
        t = QLabel(title); t.setStyleSheet("font-size:15px;font-weight:600"); box.addWidget(t)
        d = QLabel(description); d.setObjectName("Body"); d.setWordWrap(True); box.addWidget(d)
        layout.addWidget(card)

    def _welcome(self):
        box = self._page("Tudo pronto para\ncomeçar algo seu.",
                         "Vamos preparar o ULTRON em poucos passos. Você escolhe as conexões; "
                         "o assistente de voz só começa depois de concluir.")
        self._card(box, "01   Conecte sua inteligência", "Informe a sua chave do Gemini para usar a conversa por voz.")
        self._card(box, "02   Adicione o que faz sentido", "Spotify é opcional. Você pode configurar outras integrações depois.")
        self._card(box, "03   Seus dados, no seu perfil", "Credenciais protegidas pelo sistema e preferências fora da pasta instalada.")
        box.addStretch()

    def _intelligence(self):
        box = self._page("A voz começa aqui.", "Nesta primeira versão, a configuração inicial usa Gemini Live. "
                         "Os outros engines continuam disponíveis nas configurações do aplicativo.")
        box.addWidget(QLabel("CHAVE DA API GEMINI"))
        self._key_input = QLineEdit(); self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Cole a sua chave aqui")
        box.addWidget(self._key_input)
        show = QCheckBox("Mostrar chave")
        show.toggled.connect(lambda checked: self._key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        box.addWidget(show)
        link = QLabel('<a href="https://aistudio.google.com/apikey" style="color:#ff2034">Obter minha chave no Google AI Studio ↗</a>')
        link.setOpenExternalLinks(True); box.addWidget(link)
        box.addWidget(QLabel("COMO VOCÊ GOSTARIA DE SER CHAMADO?"))
        self.user_name = QLineEdit(); self.user_name.setPlaceholderText("Seu nome (opcional)")
        box.addWidget(self.user_name)
        note = QLabel("A chave será salva somente ao concluir. Esta tela ainda não valida a chave pela rede.")
        note.setObjectName("Body"); note.setWordWrap(True); box.addWidget(note); box.addStretch()

    def _integrations(self):
        box = self._page("Sua música pode vir junto.", "A conexão com Spotify é opcional. "
                         "Você autoriza o acesso no navegador na primeira utilização.")
        box.addWidget(QLabel("SPOTIFY CLIENT ID"))
        self.spotify_id = QLineEdit(); self.spotify_id.setPlaceholderText("Client ID do seu aplicativo Spotify (opcional)")
        box.addWidget(self.spotify_id)
        self._card(box, "Login com autorização do Spotify", "O fluxo PKCE não pede Client Secret. "
                   "O aplicativo deve estar cadastrado no Spotify Developer Dashboard; "
                   "o acesso depende das regras e do plano da sua conta.")
        self._card(box, "Endereço de retorno", "Cadastre http://127.0.0.1:8888/callback no aplicativo Spotify. "
                   "O mesmo endereço será usado na autorização.")
        box.addStretch()

    def _review(self):
        box = self._page("Seu ULTRON está quase pronto.", "Ao concluir, os componentes serão preparados antes de salvar suas chaves.")
        self.summary = QLabel(); self.summary.setObjectName("Body"); self.summary.setWordWrap(True)
        box.addWidget(self.summary)
        self._card(box, "Depois de abrir", "Escolha microfone e saída nas configurações de áudio. "
                   "Outras integrações podem ser adicionadas quando você precisar.")
        self._card(box, "Proteção local", "No Windows, as credenciais são protegidas para sua conta "
                   "com DPAPI. Não use o arquivo de configuração como backup portátil das chaves.")
        self.browser = QCheckBox("Preparar automação web (baixar navegador)")
        self.browser.setChecked(False)
        self.browser.setEnabled(self._preparer is not None or self._preview)
        box.addWidget(self.browser)
        box.addStretch()

    def show_error(self, message):
        self.error.setText(message)
        if not self._preparing:
            self.next.setEnabled(True)

    def _previous(self):
        self._index = max(0, self._index - 1); self._display()

    def _advance(self):
        if self._preparing:
            return
        if self._index == 1 and len(self._key_input.text().strip()) < 16:
            self.show_error("Informe uma chave Gemini. Ela ainda não foi validada online.")
            return
        if self._index < 3:
            self._index += 1; self._display(); return
        if not self._prepared:
            self._begin_preparation()
            return
        self._submit()

    def _submit(self):
        self.settings = {"gemini_api_key": self._key_input.text().strip(), "os_system": self._sel_os,
                         "user_name": self.user_name.text().strip(), "onboarding_version": 1}
        client_id = self.spotify_id.text().strip()
        if client_id:
            self.settings["plugin_config"] = {"spotify": {"client_id": client_id,
                "redirect_uri": "http://127.0.0.1:8888/callback"}}
        self.next.setEnabled(False)
        self.done.emit(self.settings["gemini_api_key"], self._sel_os)

    def _open_install_log(self):
        from core.app_paths import data_root
        path = data_root() / "logs/setup-install.log"
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _begin_preparation(self):
        if self._preview:
            self.show_error("Prévia visual: nenhum download, instalação ou salvamento será feito.")
            return
        from core.install_manager import check_local_environment
        self._preparing = True
        self.log_button.hide()
        self.pages.setCurrentIndex(self._preparation_page_index)
        self.browser_requested = self.browser.isChecked()
        self.back.setEnabled(False); self.next.setEnabled(False)
        self.next.setText("Preparando…")
        self.progress_box.show(); self.cancel.show(); self.progress_bar.setRange(0, 0)
        task = self._preparer or check_local_environment
        self._worker = PreparationWorker(task, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._preparation_result)
        self._worker.start()

    def _on_progress(self, label, received, total):
        self.progress_label.setText(label)
        if total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(min(100, round(received * 100 / total)))
        else:
            self.progress_bar.setRange(0, 0)

    def _preparation_result(self, success, message):
        self._preparing = False
        self.back.setEnabled(True); self.next.setEnabled(True)
        self.cancel.hide()
        if success:
            self._prepared = True
            self._on_progress("Componentes prontos. Salvando sua configuração…", 1, 1)
            self._submit()
        else:
            self.show_error(message or "Não foi possível preparar o ambiente.")
            self.next.setText("Tentar novamente  →")
            self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0)
            from core.app_paths import data_root
            self.log_button.setVisible((data_root() / "logs/setup-install.log").is_file())

    def _cancel_preparation(self):
        if self._worker:
            self._worker.requestInterruption()
            self.progress_label.setText("Cancelando a etapa atual…")

    def closeEvent(self, event):
        if self._preparing:
            self._cancel_preparation()
            event.ignore()
        else:
            super().closeEvent(event)

    def _display(self):
        self.pages.setCurrentIndex(self._index); self.error.clear()
        self.back.setVisible(self._index > 0)
        self.counter.setText(f"{self._index + 1} / 4")
        self.next.setText("Preparar e concluir  →" if self._index == 3 else
                          "Começar  →" if self._index == 0 else "Continuar  →")
        for i, label in enumerate(self.steps):
            label.setStyleSheet("font-size:13px;" + ("color:#ff2034;font-weight:700" if i == self._index else "color:#777777"))
        if self._index == 3:
            self.summary.setText("Gemini: chave informada, sem validação online.\n"
                + ("Spotify: será autorizado no navegador.\n" if self.spotify_id.text().strip() else "Spotify: configurar depois.\n")
                + "Primeiro preparamos o ambiente. Depois salvamos sua configuração.")
