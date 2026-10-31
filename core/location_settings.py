"""Standalone settings card; network and configuration work run off the Qt thread."""
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QPushButton, QHBoxLayout
from core import location_preferences as preferences
from core.ip_geolocation import get_search_location


class _Signals(QObject):
    done = pyqtSignal(object, str)


class _Job(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _Signals()

    def run(self):
        try:
            result = self.operation()
            self.signals.done.emit(result, '')
        except Exception:
            self.signals.done.emit(None, 'Não foi possível ler ou salvar a localização. Tente novamente.')


class LocationSettings(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        self._jobs = []
        self.setObjectName('LocationSettings')
        self.setStyleSheet('''
            QWidget#LocationSettings { background: #000000; border: 1px solid #5b1820; border-radius: 6px; }
            QLabel { color: #dddddd; background: transparent; border: none; }
            QLineEdit, QComboBox { background: #000000; color: #eeeeee; border: 1px solid #63202a; padding: 6px; }
            QPushButton { background: #000000; color: #ff454f; border: 1px solid #a82a35; padding: 8px; }
            QPushButton:hover { border-color: #ff454f; }
            QPushButton:disabled { color: #777777; border-color: #333333; }
        ''')
        layout = QVBoxLayout(self)
        heading = QLabel('Localização das pesquisas')
        heading.setStyleSheet('color: #ff454f; font-weight: bold;')
        layout.addWidget(heading)
        self.status = QLabel('Automático por IP · aguardando consulta')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        form = QFormLayout()
        self.city = QLineEdit()
        self.city.setMaxLength(120)
        self.city.setPlaceholderText('Cidade')
        self.region = QLineEdit()
        self.region.setMaxLength(120)
        self.region.setPlaceholderText('Estado ou região (opcional)')
        self.country = QComboBox()
        self.country.addItem('Selecione o país', '')
        for code, (name, _) in sorted(preferences.countries().items(), key=lambda item: item[1][0]):
            self.country.addItem(f'{name} ({code})', code)
        self.currency = QLabel('Derivada automaticamente do país')
        form.addRow('Cidade', self.city)
        form.addRow('Estado / região', self.region)
        form.addRow('País', self.country)
        form.addRow('Moeda', self.currency)
        layout.addLayout(form)
        self.country.currentIndexChanged.connect(self._country_changed)
        buttons = QHBoxLayout()
        self.confirm = QPushButton('Confirmar localização')
        self.automatic = QPushButton('Usar automático por IP')
        self.confirm.clicked.connect(self._confirm)
        self.automatic.clicked.connect(self._automatic)
        buttons.addWidget(self.confirm)
        buttons.addWidget(self.automatic)
        layout.addLayout(buttons)
        help_label = QLabel('Edite e confirme para corrigir a região. IP é aproximado e pode variar com VPN. '
                            'Pedidos por outra região na pesquisa têm prioridade.')
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._start(get_search_location)

    def _country_changed(self):
        item = preferences.countries().get(self.country.currentData())
        self.currency.setText(item[1] if item else 'Derivada automaticamente do país')

    def _confirm(self):
        try:
            value = preferences.validate_location(self.city.text(), self.country.currentData(), self.region.text())
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        def save():
            saved = preferences.confirm_location(value['city'], value['country_code'], value['region'])
            return {**saved, 'source': 'manual'}
        self._start(save)

    def _automatic(self):
        def reset():
            preferences.reset_location()
            return get_search_location()
        self._start(reset)

    def _start(self, operation):
        self.confirm.setEnabled(False)
        self.automatic.setEnabled(False)
        self.status.setText('Atualizando localização…')
        job = _Job(operation)
        self._jobs.append(job)
        job.signals.done.connect(self._received)
        QThreadPool.globalInstance().start(job)

    @pyqtSlot(object, str)
    def _received(self, value, error):
        self._jobs.clear()
        self.confirm.setEnabled(True)
        self.automatic.setEnabled(True)
        if error:
            self.status.setText(error)
            return
        if not value:
            self.status.setText('Automático por IP · região indisponível. Você pode confirmar uma localização manual.')
            self.city.clear()
            self.region.clear()
            self.country.setCurrentIndex(0)
            return
        self.city.setText(value.get('city', ''))
        self.region.setText(value.get('region', ''))
        self.country.setCurrentIndex(max(0, self.country.findData(value.get('country_code'))))
        place = ', '.join(value[k] for k in ('city', 'region', 'country_name') if value.get(k))
        mode = 'Manual confirmada' if value.get('source') == 'manual' else 'Automático por IP · aproximado'
        self.status.setText(f'{mode}: {place}')
