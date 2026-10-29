"""Opaque custom window chrome; movement remains managed by the OS."""

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget



class WindowButton(QWidget):
    """Window control painted independently of application button styles."""

    clicked = pyqtSignal()

    def __init__(self, name, icon, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 40)
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self._icon = icon
        self._hovered = False
        self._pressed = False

    def set_icon(self, icon):
        self._icon = icon
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            activate = self._pressed and self.rect().contains(event.position().toPoint())
            self._pressed = False
            self.update()
            if activate:
                self.clicked.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.TextAntialiasing)
        if self._hovered:
            background = QColor("#961220" if self._icon == "close" else "#1a1a20")
            if self._pressed:
                background = background.darker(125)
            painter.fillRect(self.rect(), background)
        painter.setPen(QPen(QColor("#ffffff" if self._hovered else "#767684"), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._icon == "minimize":
            painter.drawLine(QPointF(18, 20), QPointF(28, 20))
        elif self._icon == "maximize":
            painter.drawRoundedRect(QRectF(18, 15, 10, 10), 1.5, 1.5)
        elif self._icon == "restore":
            painter.drawRoundedRect(QRectF(20, 14, 9, 9), 1.3, 1.3)
            background = QColor("#09090c")
            if self._hovered:
                background = QColor("#1a1a20")
                if self._pressed:
                    background = background.darker(125)
            painter.setBrush(background)
            painter.drawRoundedRect(QRectF(17, 17, 9, 9), 1.3, 1.3)
        elif self._icon == "close":
            painter.drawLine(QPointF(18, 15), QPointF(28, 25))
            painter.drawLine(QPointF(28, 15), QPointF(18, 25))


class TitleBar(QWidget):
    def __init__(self, parent, title, clock, date):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet(f"background: #000000; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(10)
        layout.addSpacing(30)  # Reserved for Ultron angular monogram.
        title.setText("ULTRON")
        title_font = QFont("Segoe UI Semibold")
        title_font.setPointSizeF(10.5)
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        title_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        title.setFont(title_font)
        layout.addWidget(title)
        layout.addStretch(1)  # Reserved for the command palette.
        dates = QVBoxLayout()
        dates.setContentsMargins(0, 0, 0, 0)
        dates.setSpacing(0)
        clock_font = QFont("Consolas", 11, QFont.Weight.Bold)
        clock_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        clock.setFont(clock_font)  # Preserve the existing theme accent stylesheet.
        date_font = QFont("Segoe UI")
        date_font.setPointSizeF(7.5)
        date_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        date.setFont(date_font)
        date.setStyleSheet("color: #767684; background: transparent; border: none;")
        for label in (clock, date):
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dates.addWidget(clock)
        dates.addWidget(date)
        layout.addLayout(dates)
        layout.addSpacing(4)  # Together with layout spacing: 14 px before controls.
        buttons = QHBoxLayout()
        buttons.setSpacing(0)
        self.minimize_button = self._button("Minimizar", "minimize")
        self.maximize_button = self._button("Maximizar", "maximize")
        self.close_button = self._button("Fechar", "close")
        self.close_button.setObjectName("windowClose")
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.minimize_button.clicked.connect(parent.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(parent.close)
        for label in (title, clock, date):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _button(self, name, icon):
        return WindowButton(name, icon, self)

    def sync_state(self):
        maximized = self.window().isMaximized()
        self.maximize_button.set_icon("restore" if maximized else "maximize")
        name = "Restaurar" if maximized else "Maximizar"
        self.maximize_button.setToolTip(name)
        self.maximize_button.setAccessibleName(name)
        self.setVisible(not self.window().isFullScreen())

    def toggle_maximized(self):
        window = self.window()
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()
        self.sync_state()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window.isMaximized():
                position = event.globalPosition().toPoint()
                fraction = event.position().x() / max(1, self.width())
                offset_y = int(event.position().y())
                window.showNormal()
                window.move(position - QPoint(int(window.width() * fraction), offset_y))
            handle = window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), QColor("#000000"))
        # D21C — seamless top chrome: no horizontal divider line.
        # Ultron monogram: angular U, deliberately not the old hexagon.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#f02e4a"), 1.65))
        crest = QPainterPath()
        crest.moveTo(17.5, 10.5)
        crest.lineTo(17.5, 24.0)
        crest.lineTo(27.0, 30.5)
        crest.lineTo(36.5, 24.0)
        crest.lineTo(36.5, 10.5)
        painter.drawPath(crest)
        painter.setPen(QPen(QColor("#ff566c"), 1.2))
        inner = QPainterPath()
        inner.moveTo(22.0, 13.0)
        inner.lineTo(22.0, 22.0)
        inner.lineTo(27.0, 25.5)
        inner.lineTo(32.0, 22.0)
        inner.lineTo(32.0, 13.0)
        painter.drawPath(inner)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff304e"))
        painter.drawEllipse(QPointF(27.0, 9.8), 1.5, 1.5)
