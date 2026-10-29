"""
HoloOrb — esfera holografica de "trilhas de circuito" para o HUD do Mark LVI.

Mesma interface do HoloEye / HoloAvatar:
    SPAN, step(dt, amp, speaking, muted, state, **kw), paint(p, cx, cy, r, primary, accent, bg),
    glance(dx, dy, hold)

Camadas (como na imagem de referencia):
  1. CASCA   - centenas de trilhas curtas que andam em passos retos/diagonais (placa de circuito),
               com uma "cabeca" que avanca e uma cauda que apaga
  2. ARCOS   - aros finos, incompletos, em varios raios, girando em eixos diferentes
  3. MIOLO   - aneis hexagonais irregulares e apertados (favo de mel) com um buraco escuro no centro
  4. ANEL    - faixa equatorial larga e inclinada, feita de dezenas de linhas quase coladas
  5. FEIXE   - 3 fios finos e muito brilhantes cruzando o miolo na diagonal

So numpy + QPainter (sem OpenGL, sem dependencia nova). O Qt so e importado dentro de paint(),
entao a geometria pode ser testada sem interface.

Ajustes rapidos: constantes logo abaixo.
"""
from __future__ import annotations

import math
import time

import numpy as np

# ── Ajustes ─────────────────────────────────────────────────────────────────
SPAN = 1.80            # mesmo valor do HoloEye (escala da faixa do HUD)
ORB_SCALE = 1.0        # tamanho da esfera em relacao ao "r" do HUD (aumente/diminua se precisar)
QUALITY = 0.8          # 0.5 = metade das linhas (mais leve) ... 1.5 = mais denso
ANTIALIAS = True       # False = bem mais leve, linhas um pouco serrilhadas
GLOW = True            # False = sem o brilho extra (menos uma passada de desenho)
DRAW_BACK = True       # False = nao desenha o lado de tras da esfera (bem mais leve)
NUM_TRACES = int(190 * QUALITY)     # trilhas da casca
MAX_LEN = 96                         # pontos por trilha
STEP = 0.012                         # tamanho de cada passo na superficie (radianos)
REROLL_PER_SEC = 0.06                # fracao de trilhas refeitas por segundo
NUM_ARCS = 13
CORE_RINGS = 36
CORE_RADIUS = 0.50
BAND_LINES = int(22 * QUALITY)
BAND_POINTS = 96
BAND_TILT_DEG = 8.0                  # abertura do anel (menor = mais fino)
BAND_ROLL_DEG = -8.0                 # inclinacao do anel na tela
SPHERE_TILT_DEG = 16.0
BEAM_ANGLE_DEG = -57.0               # direcao do feixe na tela (negativo = desce para a direita)
ALPHA = (60, 135, 225)               # opacidade das 3 faixas de brilho
LINE_WIDTH = 0.0042                  # espessura da linha em relacao ao raio


def _rate(dt: float, tau: float) -> float:
    return 1.0 - math.exp(-dt / max(tau, 1e-6))


def _rgb(c) -> tuple[int, int, int]:
    try:
        return int(c.red()), int(c.green()), int(c.blue())
    except Exception:
        try:
            return int(c[0]), int(c[1]), int(c[2])
        except Exception:
            return 255, 150, 60


def _mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def _rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def _rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


class HoloOrb:
    SPAN = SPAN

    def __init__(self) -> None:
        self._rng = np.random.default_rng()
        rng = self._rng

        # estado animado
        self._t = 0.0
        self._yaw = rng.uniform(0, 6.28)
        self._amp = 0.0
        self._sf = 0.55          # fator de velocidade (suavizado)
        self._en = 0.65          # energia/brilho (suavizado)
        self._reroll_acc = 0.0
        self._gx = self._gy = 0.0
        self._gxs = self._gys = 0.0
        self._glance_until = 0.0

        # CASCA: trilhas
        T = NUM_TRACES
        self._pts = np.zeros((T, MAX_LEN, 3), dtype=np.float64)
        self._len = np.zeros(T, dtype=np.int64)
        for i in range(T):
            self._pts[i], self._len[i] = self._new_trace()
        self._head = rng.uniform(0, MAX_LEN, T)
        self._win = rng.uniform(0.35, 0.6, T) * self._len
        self._spd = rng.uniform(14.0, 34.0, T)
        self._idx = np.arange(MAX_LEN)[None, :]

        # ARCOS
        A = NUM_ARCS
        self._arc_r = rng.uniform(0.84, 1.0, A)
        self._arc_span = rng.uniform(1.6, 5.4, A)
        self._arc_phi0 = rng.uniform(0, 6.28, A)
        self._arc_spin = rng.uniform(-0.25, 0.25, A)
        self._arc_Q = []
        for _ in range(A):
            q, _r = np.linalg.qr(rng.normal(size=(3, 3)))
            if np.linalg.det(q) < 0:
                q[:, 0] *= -1
            self._arc_Q.append(q)
        self._arc_Q = np.array(self._arc_Q)
        n_arc = 90
        self._arc_u = np.linspace(0, 1, n_arc)
        self._arc_noise = rng.normal(0, 0.004, (A, n_arc))
        self._arc_ok = np.ones((A, n_arc - 1), dtype=bool)
        for a in range(A):
            for _ in range(rng.integers(1, 3)):
                g0 = rng.uniform(0, 0.9)
                gw = rng.uniform(0.03, 0.12)
                lo, hi = int(g0 * n_arc), int((g0 + gw) * n_arc)
                self._arc_ok[a, lo:hi] = False

        # MIOLO: aneis hexagonais irregulares
        K = CORE_RINGS
        sub = 5
        self._core = np.zeros((K, 6 * sub + 1, 2))
        for k in range(K):
            rho = 0.05 + k * (CORE_RADIUS - 0.05) / (K - 1)
            th0 = rng.uniform(0, 6.28)
            ang = th0 + np.arange(6) * (math.pi / 3) + rng.normal(0, 0.10, 6)
            rad = rho * (1 + rng.normal(0, 0.05, 6))
            v = np.stack([rad * np.cos(ang), rad * np.sin(ang)], axis=1)
            v = np.vstack([v, v[:1]])
            pts = []
            for e in range(6):
                for s in range(sub):
                    f = s / sub
                    pts.append(v[e] * (1 - f) + v[e + 1] * f)
            pts.append(v[6])
            arr = np.array(pts) + rng.normal(0, 0.0035, (6 * sub + 1, 2))
            arr += rng.normal(0, 0.006, 2)
            self._core[k] = arr
        self._core_w = 0.10 + 0.012 * np.arange(K) * rng.uniform(0.6, 1.4, K)
        self._core_dir = rng.choice([-1.0, 1.0], K)
        # pequenos hexagonos soltos (textura de favo)
        H = int(90 * QUALITY)
        hc_r = rng.uniform(0.05, CORE_RADIUS - 0.03, H)
        hc_a = rng.uniform(0, 6.28, H)
        hs = rng.uniform(0.028, 0.05, H)
        ha = rng.uniform(0, 1.05, H)
        hv = np.arange(7) * (math.pi / 3)
        self._hex = np.zeros((H, 7, 2))
        for i in range(H):
            cx_, cy_ = hc_r[i] * math.cos(hc_a[i]), hc_r[i] * math.sin(hc_a[i])
            self._hex[i, :, 0] = cx_ + hs[i] * np.cos(hv + ha[i])
            self._hex[i, :, 1] = cy_ + hs[i] * np.sin(hv + ha[i])

        # ANEL equatorial
        J = BAND_LINES
        self._band_rho = np.linspace(0.97, 1.13, J) + rng.normal(0, 0.004, J)
        self._band_u = np.linspace(0, 1, BAND_POINTS)
        self._band_noise = rng.normal(0, 0.005, (J, BAND_POINTS))
        self._band_spin = rng.uniform(0.04, 0.2, J) * rng.choice([-1, 1], J)
        self._band_ok = np.ones((J, BAND_POINTS - 1), dtype=bool)
        for j in range(J):
            for _ in range(rng.integers(2, 5)):
                g0 = rng.uniform(0, 0.95)
                gw = rng.uniform(0.02, 0.10)
                lo, hi = int(g0 * BAND_POINTS), int((g0 + gw) * BAND_POINTS)
                self._band_ok[j, lo:hi] = False

        # FEIXE
        self._beam_phase = rng.uniform(0, 6.28)

    # ── geracao de trilhas ──────────────────────────────────────────────
    def _new_trace(self):
        rng = self._rng
        L = int(rng.integers(30, MAX_LEN))
        lat = math.asin(rng.uniform(-0.98, 0.98))
        lon = rng.uniform(0, 2 * math.pi)
        base = int(rng.integers(0, 8))
        # horizontais/verticais sao mais comuns
        if rng.random() < 0.55:
            base = int(rng.choice([0, 2, 4, 6]))
        jog = 0
        out = np.zeros((MAX_LEN, 3))
        for i in range(L):
            if rng.random() < 0.50:
                jog = int(rng.choice([-1, 0, 1]))
            if rng.random() < 0.05:
                base = int(rng.integers(0, 8))
            h = (base + jog) * (math.pi / 4)
            c = max(0.22, math.cos(lat))
            lon += STEP * math.cos(h) / c
            lat += STEP * math.sin(h)
            lat = max(-1.45, min(1.45, lat))
            out[i] = (math.cos(lat) * math.sin(lon), math.sin(lat), math.cos(lat) * math.cos(lon))
        out[L:] = out[L - 1]
        return out, L

    # ── interface ───────────────────────────────────────────────────────
    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        self._gx = max(-1.0, min(1.0, float(dx)))
        self._gy = max(-1.0, min(1.0, float(dy)))
        self._glance_until = time.monotonic() + float(hold)

    def step(self, dt, amp, speaking=False, muted=False, state="", **kw) -> None:
        dt = max(0.0, min(float(dt or 0.0), 0.1))
        st = str(state or "").upper()
        a = float(amp or 0.0) if speaking else 0.0
        a = max(0.0, min(1.0, a))
        self._amp += (a - self._amp) * _rate(dt, 0.06)

        if muted:
            sf, en = 0.10, 0.18
        elif st == "SLEEPING":
            sf, en = 0.18, 0.35
        elif st in ("THINKING", "PROCESSING"):
            sf, en = 2.6, 1.0
        elif speaking:
            sf, en = 1.0 + 0.8 * self._amp, 0.85 + 0.55 * self._amp
        elif st == "LISTENING":
            sf, en = 0.9, 0.85
        else:
            sf, en = 0.55, 0.65
        self._sf += (sf - self._sf) * _rate(dt, 0.4)
        self._en += (en - self._en) * _rate(dt, 0.25)

        self._t += dt * self._sf
        self._yaw += 0.20 * dt * self._sf

        # olhar
        if time.monotonic() > self._glance_until:
            self._gx = self._gy = 0.0
        self._gxs += (self._gx - self._gxs) * _rate(dt, 0.3)
        self._gys += (self._gy - self._gys) * _rate(dt, 0.3)

        # trilhas: a cabeca avanca; algumas sao refeitas
        self._head += self._spd * dt * self._sf
        self._head %= np.maximum(self._len, 1)
        self._reroll_acc += REROLL_PER_SEC * NUM_TRACES * dt * (0.5 + 0.5 * self._sf)
        n = int(self._reroll_acc)
        if n > 0:
            self._reroll_acc -= n
            for t in self._rng.integers(0, NUM_TRACES, n):
                self._pts[t], self._len[t] = self._new_trace()
                self._win[t] = self._rng.uniform(0.35, 0.6) * self._len[t]

    # ── geometria (sem Qt) ──────────────────────────────────────────────
    def _segments(self, cx: float, cy: float, R: float):
        """Devolve ([lote0, lote1, lote2], feixe): cada lote e um array (n,4) de x1,y1,x2,y2."""
        b = [[], [], []]
        breath = 1.0 + 0.03 * self._amp

        def xy(P):
            return np.stack([cx + P[..., 0] * R * breath, cy - P[..., 1] * R * breath], axis=-1)

        sphere = _rot_x(math.radians(SPHERE_TILT_DEG) + 0.25 * self._gys) @ _rot_y(self._yaw + 0.3 * self._gxs)

        # 1) CASCA
        P = self._pts @ sphere.T                      # (T, M, 3)
        S = xy(P)
        age = (self._head[:, None] - self._idx) % np.maximum(self._len, 1)[:, None]
        vis = (age < self._win[:, None]) & (self._idx < self._len[:, None])
        ok = vis[:, :-1] & vis[:, 1:]
        frac = age[:, 1:] / np.maximum(self._win[:, None], 1.0)
        zmid = 0.5 * (P[:, :-1, 2] + P[:, 1:, 2])
        front = zmid > 0
        seg = np.concatenate([S[:, :-1], S[:, 1:]], axis=-1)       # (T, M-1, 4)
        lvl = np.where(front, np.where(frac < 0.15, 2, np.where(frac < 0.6, 1, 0)), 0)
        if not DRAW_BACK:
            ok = ok & front
        for k in range(3):
            m = ok & (lvl == k)
            if m.any():
                b[k].append(seg[m])

        # 2) ARCOS
        phi = self._arc_phi0[:, None] + self._arc_spin[:, None] * self._t * 3.0 \
            + self._arc_span[:, None] * self._arc_u[None, :]
        rr = self._arc_r[:, None] + self._arc_noise
        arc = np.stack([rr * np.cos(phi), rr * np.sin(phi), np.zeros_like(phi)], axis=-1)   # (A, n, 3)
        arc = np.einsum("aij,anj->ani", self._arc_Q, arc) @ sphere.T
        Sa = xy(arc)
        sega = np.concatenate([Sa[:, :-1], Sa[:, 1:]], axis=-1)
        fa = (0.5 * (arc[:, :-1, 2] + arc[:, 1:, 2])) > 0
        for k, m in ((1, self._arc_ok & fa), (0, self._arc_ok & ~fa if DRAW_BACK else self._arc_ok & False)):
            if m.any():
                b[k].append(sega[m])

        # 3) MIOLO (gira no proprio plano, aneis em velocidades diferentes)
        ang = self._t * self._core_w * self._core_dir * 2.2
        ca, sa_ = np.cos(ang)[:, None], np.sin(ang)[:, None]
        cx_, cy_ = self._core[..., 0], self._core[..., 1]
        pr = np.stack([cx_ * ca - cy_ * sa_, cx_ * sa_ + cy_ * ca], axis=-1)
        core3 = np.concatenate([pr, np.zeros(pr.shape[:-1] + (1,))], axis=-1) @ _rot_x(math.radians(10)).T
        scale = 1.0 + 0.04 * math.sin(self._t * 1.3) + 0.08 * self._amp
        Sc = xy(core3 * scale)
        segc = np.concatenate([Sc[:, :-1], Sc[:, 1:]], axis=-1)
        K = segc.shape[0]
        b[2].append(segc[:8].reshape(-1, 4))
        b[1].append(segc[8:].reshape(-1, 4))
        hx = self._hex
        ah = self._t * 0.18
        hxr = np.stack([hx[..., 0] * math.cos(ah) - hx[..., 1] * math.sin(ah),
                        hx[..., 0] * math.sin(ah) + hx[..., 1] * math.cos(ah)], axis=-1)
        Sh = xy(np.concatenate([hxr, np.zeros(hxr.shape[:-1] + (1,))], axis=-1) * scale)
        b[0].append(np.concatenate([Sh[:, :-1], Sh[:, 1:]], axis=-1).reshape(-1, 4))

        # 4) ANEL equatorial (fica quase de lado; so gira o pontilhado)
        th = 2 * math.pi * self._band_u[None, :] + self._band_spin[:, None] * self._t * 2.0
        rho = self._band_rho[:, None] + self._band_noise
        ring = np.stack([rho * np.cos(th), np.zeros_like(th), rho * np.sin(th)], axis=-1)   # plano xz
        Rb = _rot_z(math.radians(BAND_ROLL_DEG)) @ _rot_x(math.radians(BAND_TILT_DEG + 2 * self._gys))
        ring = ring @ Rb.T
        Sr = xy(ring)
        segr = np.concatenate([Sr[:, :-1], Sr[:, 1:]], axis=-1)
        fr = (0.5 * (ring[:, :-1, 2] + ring[:, 1:, 2])) > 0
        bright = (np.arange(ring.shape[0]) % 7 == 3)[:, None]
        m2 = self._band_ok & fr & bright
        m1 = self._band_ok & fr & ~bright
        m0 = self._band_ok & ~fr if DRAW_BACK else self._band_ok & False
        for k, m in ((2, m2), (1, m1), (0, m0)):
            if m.any():
                b[k].append(segr[m])

        # 5) FEIXE (3 fios finos, abrindo levemente para a ponta)
        ang = math.radians(BEAM_ANGLE_DEG) + 0.22 * math.sin(self._t * 0.45 + self._beam_phase)
        d = np.array([math.cos(ang), math.sin(ang)])
        nrm = np.array([-d[1], d[0]])
        beam = []
        for off0, off1 in ((0.0, 0.0), (0.004, 0.016), (-0.004, -0.016)):
            p0 = d * -0.50 + nrm * off0
            p1 = d * 0.66 + nrm * off1
            beam.append([cx + p0[0] * R, cy - p0[1] * R, cx + p1[0] * R, cy - p1[1] * R])
        beam = np.array(beam)

        out = [np.concatenate(x, axis=0) if x else np.zeros((0, 4)) for x in b]
        return out, beam

    # ── desenho (Qt) ────────────────────────────────────────────────────
    def paint(self, p, cx, cy, r, primary, accent, bg=None) -> None:
        from PyQt6.QtCore import QLineF, Qt
        from PyQt6.QtGui import QColor, QPainter, QPen

        R = float(r) * ORB_SCALE
        if R < 8:
            return
        base = _rgb(primary)
        hot = _mix(base, (255, 255, 255), 0.5)
        batches, beam = self._segments(float(cx), float(cy), R)
        en = max(0.0, min(1.4, self._en))
        w = max(0.9, R * LINE_WIDTH)

        p.save()
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, ANTIALIAS)

            def draw(arr, rgb, alpha, width):
                if len(arr) == 0:
                    return
                pen = QPen(QColor(rgb[0], rgb[1], rgb[2], int(max(0, min(255, alpha)))))
                pen.setWidthF(width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLines([QLineF(a, b_, c, d) for a, b_, c, d in arr.tolist()])

            draw(batches[0], base, ALPHA[0] * en, w)
            draw(batches[1], base, ALPHA[1] * en, w)
            draw(batches[2], hot, ALPHA[2] * en, w)
            # brilho: o lote mais forte e o feixe de novo, mais largo e bem transparente
            if GLOW:
                draw(batches[2], hot, 34 * en, w * 3.6)
                draw(beam, hot, 40 * en, w * 5.0)
            draw(beam, (255, 255, 255), 225 * en, w * 1.15)
        finally:
            p.restore()