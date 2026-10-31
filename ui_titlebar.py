"""Opaque minimalist VOID OS window chrome; movement remains managed by the OS."""

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QWidget


class WindowButton(QWidget):
    """Discrete window control painted independently of application QSS."""

    clicked = pyqtSignal()

    def __init__(self, name, icon, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 34)
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
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        if self._hovered:
            background = QColor("#7a101d" if self._icon == "close" else "#120609")
            if self._pressed:
                background = background.darker(125)
            painter.fillRect(self.rect(), background)
        stroke = QColor("#ffffff" if self._hovered else "#5c5c68")
        painter.setPen(QPen(stroke, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        if self._icon == "minimize":
            painter.drawLine(QPointF(cx - 4.5, cy + 0.5), QPointF(cx + 4.5, cy + 0.5))
        elif self._icon == "maximize":
            painter.drawRoundedRect(QRectF(cx - 4.5, cy - 4.5, 9.0, 9.0), 1.0, 1.0)
        elif self._icon == "restore":
            painter.drawRoundedRect(QRectF(cx - 2.5, cy - 5.0, 7.5, 7.5), 1.0, 1.0)
            fill = QColor("#000000")
            if self._hovered:
                fill = QColor("#120609")
                if self._pressed:
                    fill = fill.darker(125)
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(cx - 5.0, cy - 2.5, 7.5, 7.5), 1.0, 1.0)
        elif self._icon == "close":
            painter.drawLine(QPointF(cx - 4.2, cy - 4.2), QPointF(cx + 4.2, cy + 4.2))
            painter.drawLine(QPointF(cx + 4.2, cy - 4.2), QPointF(cx - 4.2, cy + 4.2))
        painter.end()


class TitleBar(QWidget):
    """Minimalist pure-black top chrome with symmetric crimson corner lines."""

    BAR_HEIGHT = 34

    def __init__(self, parent, title, clock, date):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setStyleSheet("background: #000000; border: none;")
        # Keep legacy labels alive and hidden so MainWindow updates stay valid.
        for label in (title, clock, date):
            label.setParent(self)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        painter.fillRect(self.rect(), QColor("#000000"))

        # D20 VOID OS — symmetric thin crimson accent lines at top corners.
        seg = min(136.0, max(54.0, w * 0.14))
        y = 20.5
        left_x0 = 26.0
        left_x1 = left_x0 + seg
        controls_w = 36.0 * 3.0 + 18.0
        right_x1 = max(left_x1 + 32.0, w - controls_w)
        right_x0 = max(left_x1 + 24.0, right_x1 - seg)

        line_pen = QPen(QColor(210, 26, 48, 175), 1.2)
        tip_pen = QPen(QColor(255, 36, 58, 235), 1.4)
        painter.setPen(line_pen)
        painter.drawLine(QPointF(left_x0, y), QPointF(left_x1, y))
        if right_x1 - right_x0 >= 24.0:
            painter.drawLine(QPointF(right_x0, y), QPointF(right_x1, y))

        painter.setPen(tip_pen)
        painter.drawLine(QPointF(left_x0, y), QPointF(left_x0 + min(22.0, seg * 0.25), y))
        if right_x1 - right_x0 >= 24.0:
            painter.drawLine(QPointF(right_x1 - min(22.0, seg * 0.25), y), QPointF(right_x1, y))
        painter.end()
