"""Painel compacto CORE STATUS ancorado ao topo do HUD (sem timers próprios)."""
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

_REF_W, _REF_H = 748.0, 202.0   # proporção da arte de referência


def derive_status(state, fps_reading, fps_target):
    """Mapeia o estado da UI para os três campos. Não mede rede/serviços.

    CONNECTION é inferido do estado publicado pela sessão (a UI não recebe um
    sinal explícito de conexão); por isso nunca afirma mais que isso.
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
    render = f"{int(round(fps_reading))} FPS" if fps_reading else "-- FPS"
    return system, conn, render


class CoreStatusPanel(QWidget):
    """Overlay transparente a mouse; repinta só quando algum valor muda."""

    def __init__(self, anchor, accent=lambda: "#ff2034", parent=None):
        super().__init__(parent or anchor)
        self._anchor = anchor
        self._accent = accent
        self._values = ("STARTING", "CONNECTING", "-- FPS")
        self._hud = None
        self._hud_page = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        # O Qt só emite Move/Resize para o próprio widget: quando um ancestral
        # (splitter, layout da página) se move ou redimensiona, a âncora não é
        # notificada. Observa toda a cadeia até o pai do overlay.
        node = anchor
        while node is not None:
            node.installEventFilter(self)
            if node is self.parentWidget():
                break
            node = node.parentWidget()
        self.reposition()

    def bind_hud_clock(self, hud):
        """Lê o HUD no quadro compartilhado; atualiza apenas se o texto mudar."""
        if self._hud is hud:
            return
        if self._hud is not None:
            self._hud.pacedFrame.disconnect(self._on_frame)
        self._hud = hud
        hud.pacedFrame.connect(self._on_frame)
        self._on_frame(0.0)

    def _on_frame(self, _now):
        hud = self._hud
        values = derive_status(hud.state, hud._fps_reading, hud._fps_target)
        self.set_values(*values)

    def set_values(self, system, connection, render):
        values = (system, connection, render)
        if values != self._values:
            self._values = values
            self.update()

    def on_page_changed(self, index):
        self._hud_page = index == 0
        self.setVisible(self._hud_page)
        if self._hud_page:
            self.reposition()

    def reposition(self):
        w = self._anchor.width()
        parent = self.parentWidget()
        avail = max(w + 36, min(336, parent.width() - 40)) if parent is not self._anchor else w - 16
        width = max(1, min(340, avail))
        height = max(1, int(width * _REF_H / _REF_W))
        origin = parent.mapFromGlobal(self._anchor.mapToGlobal(self._anchor.rect().topLeft()))
        cx = origin.x() + w // 2
        x = cx - width // 2
        self.setGeometry(max(0, x), origin.y() + 4, width, height)
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is not self and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show,
                QEvent.Type.LayoutRequest):
            self.reposition()
        return False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / _REF_W, self.height() / _REF_H)
        red = QColor(self._accent())
        dim = QColor(red)
        dim.setAlpha(70)

        # Moldura chanfrada simétrica: centro (l + r) / 2 == _REF_W / 2 == 374.
        l, r, t, b, c = 28.0, 720.0, 27.0, 185.0, 25.0
        bright = QPen(red, 3.0)
        faint = QPen(dim, 2.0)
        p.setPen(bright)
        p.drawPolyline(QPolygonF([
            QPointF(l, 77), QPointF(l, t + c), QPointF(l + c, t), QPointF(210, t)]))
        p.drawPolyline(QPolygonF([
            QPointF(538, t), QPointF(r - c, t), QPointF(r, t + c), QPointF(r, 77)]))
        p.drawPolyline(QPolygonF([
            QPointF(l, 135), QPointF(l, b - c), QPointF(l + c, b), QPointF(195, b)]))
        p.drawPolyline(QPolygonF([
            QPointF(553, b), QPointF(r - c, b), QPointF(r, b - c), QPointF(r, 135)]))
        p.setPen(faint)
        p.drawLine(QPointF(210, t), QPointF(285, t))
        p.drawLine(QPointF(463, t), QPointF(538, t))
        p.drawLine(QPointF(195, b), QPointF(553, b))
        p.drawLine(QPointF(l, 77), QPointF(l, 135))
        p.drawLine(QPointF(r, 77), QPointF(r, 135))

        title = QFont("Consolas", 1)
        title.setPixelSize(20)
        title.setBold(True)
        title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
        p.setFont(title)
        p.setPen(red)
        p.drawText(QRectF(210, 8, 328, 40), Qt.AlignmentFlag.AlignCenter, "CORE STATUS")

        labels = ("SYSTEM", "CONNECTION", "RENDER")
        label_font = QFont("Consolas", 1)
        label_font.setPixelSize(17)
        value_font = QFont("Consolas", 1)
        value_font.setPixelSize(24)
        value_font.setBold(True)
        col_w = (r - l) / 3.0
        for i, (label, value) in enumerate(zip(labels, self._values)):
            cell = QRectF(l + i * col_w, 0, col_w, _REF_H)
            p.setFont(label_font)
            p.setPen(QColor("#9a9aa3"))
            p.drawText(QRectF(cell.left(), 76, col_w, 34), Qt.AlignmentFlag.AlignCenter, label)
            p.setFont(value_font)
            p.setPen(red)
            p.drawText(QRectF(cell.left(), 108, col_w, 40), Qt.AlignmentFlag.AlignCenter, value)
            if i:
                p.setPen(QPen(dim, 2.0))
                p.drawLine(QPointF(cell.left(), 72), QPointF(cell.left(), 155))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(red)
        p.drawEllipse(QPointF(_REF_W / 2.0, 193), 3.5, 3.5)
        p.end()
