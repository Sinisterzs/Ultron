"""Painel compacto CORE TELEMETRY ancorado ao topo da Home (sem timers próprios)."""
from PyQt6.QtCore import QEvent, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget


def format_network_rate(net_mbps) -> str:
    """Formata taxa de rede em MB/s do _SysMetrics para KB/s ou MB/s."""
    try:
        val = max(0.0, float(net_mbps))
    except (TypeError, ValueError):
        return ""
    if val < 1.0:
        return f"{val * 1024.0:.0f} KB/s"
    return f"{val:.1f} MB/s"


def derive_status(state, fps_reading, fps_target, net_mbps=None):
    """Mapeia estado da sessão, taxa de rede opcional e FPS para CORE TELEMETRY.

    Mantém compatibilidade com chamadas de 3 argumentos; quando `net_mbps` é
    fornecido pela telemetria local, combina estado da sessão + taxa real.
    """
    state = (state or "").upper()
    if state in ("", "INITIALISING", "INITIALIZING"):
        system, conn = "STARTING", "CONNECTING"
    elif state == "SLEEPING":
        system, conn = "ONLINE", "STANDBY"
    elif state == "MUTED":
        system, conn = "ONLINE", "MUTED"
    else:
        system, conn = "ONLINE", "STABLE"
    if net_mbps is not None:
        rate = format_network_rate(net_mbps)
        if rate:
            conn = f"{conn} {rate}"
    render = f"{int(round(fps_reading))} FPS" if fps_reading else "-- FPS"
    return system, conn, render


class CoreStatusPanel(QWidget):
    """Moldura CORE TELEMETRY transparente a mouse; repinta só quando muda."""

    PANEL_H = 50
    PANEL_MAX_W = 312
    PANEL_MIN_W = 228

    def __init__(self, anchor, accent=lambda: "#ff2034", parent=None, net_provider=None):
        super().__init__(parent or anchor)
        self._anchor = anchor
        self._accent = accent
        self._net_provider = net_provider
        self._values = ("STARTING", "CONNECTING", "-- FPS")
        self._top_offset = 4
        self._hud = None
        self._hud_page = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        node = anchor
        while node is not None:
            node.installEventFilter(self)
            if node is self.parentWidget():
                break
            node = node.parentWidget()
        self.reposition()

    def set_net_provider(self, provider):
        self._net_provider = provider

    def bind_hud_clock(self, hud):
        """Lê o HUD no quadro compartilhado; repinta apenas se o texto mudar."""
        if self._hud is hud:
            return
        if self._hud is not None:
            self._hud.pacedFrame.disconnect(self._on_frame)
        self._hud = hud
        hud.pacedFrame.connect(self._on_frame)
        self._on_frame(0.0)

    def _on_frame(self, _now):
        hud = self._hud
        net_val = None
        if callable(self._net_provider):
            try:
                net_val = self._net_provider()
            except Exception:
                net_val = None
        values = derive_status(hud.state, hud._fps_reading, hud._fps_target, net_val)
        self.set_values(*values)

    def set_values(self, system, connection, render):
        values = (system, connection, render)
        if values != self._values:
            self._values = values
            self.update()

    def summary_text(self) -> str:
        return f"{self._values[0]}  •  {self._values[1]}  •  {self._values[2]}"

    def refresh_theme(self):
        self.update()

    def _apply_style(self):
        self.update()

    def on_page_changed(self, index):
        self._hud_page = index == 0
        self.setVisible(self._hud_page)
        if self._hud_page:
            self.reposition()

    def reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        w = self._anchor.width()
        avail = parent.width() - 40 if parent is not self._anchor else w - 16
        width = max(1, min(self.PANEL_MAX_W, max(self.PANEL_MIN_W, min(avail, max(w, self.PANEL_MIN_W)))))
        width = min(width, max(1, parent.width() - 16))
        height = self.PANEL_H
        if parent is not self._anchor and self._anchor.width() > 0:
            origin = parent.mapFromGlobal(self._anchor.mapToGlobal(self._anchor.rect().topLeft()))
            cx = origin.x() + w // 2
            y = self._top_offset
        else:
            cx = parent.width() // 2
            y = self._top_offset
        x = max(8, min(parent.width() - width - 8, cx - width // 2))
        self.setGeometry(max(0, x), max(0, y), width, height)
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is not self and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show,
                QEvent.Type.LayoutRequest):
            self.reposition()
        return False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        w, h = float(self.width()), float(self.height())
        rect = QRectF(1.0, 1.0, max(1.0, w - 2.0), max(1.0, h - 2.0))

        red = QColor(self._accent())
        border_col = QColor(red)
        border_col.setAlpha(155)

        p.setPen(QPen(border_col, 1.15))
        p.setBrush(QColor(0, 0, 0, 255))
        p.drawRoundedRect(rect, 6.5, 6.5)

        title_font = QFont("Consolas")
        title_font.setPixelSize(11)
        title_font.setBold(True)
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
        p.setFont(title_font)
        p.setPen(red)
        p.drawText(QRectF(8.0, 6.0, w - 16.0, 18.0), Qt.AlignmentFlag.AlignCenter, "CORE TELEMETRY")

        sub_font = QFont("Consolas")
        sub_font.setPixelSize(10)
        sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.7)
        p.setFont(sub_font)
        p.setPen(QColor("#b8b8c4"))
        summary = f"{self._values[0]}  •  {self._values[1]}  •  {self._values[2]}"
        p.drawText(QRectF(8.0, 25.0, w - 16.0, 18.0), Qt.AlignmentFlag.AlignCenter, summary)
        p.end()
