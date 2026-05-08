"""Desktop pet for macOS — frameless, transparent, always-on-top window.

상태 (state):
    WANDER   기본. 화면 하단을 어슬렁
    EXCITED  CPU > 70%. 빠르게 + 크게 흔들림
    SLEEPING 낮은 CPU 가 일정 시간 지속될 때. 멈춰서 ZZZ

Sprite:
    한 widget 안에 3마리(요키/진돗개/비숑) 를 같이 그린다.
    각자 독립된 bob phase 로 갤럽 모션처럼 보이게.
"""
from __future__ import annotations

import math
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
    QTransform,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
    QWidget,
)

from monitor import (
    CoreLayout,
    HwMonitor,
    HwSnapshot,
    MacmonReader,
    ProcEntry,
    ProcessTracker,
    TempSnapshot,
    detect_core_layout,
)

if sys.platform == "darwin":
    try:
        import objc
        from AppKit import (
            NSApp,
            NSApplicationActivationPolicyAccessory,
            NSStatusWindowLevel,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorIgnoresCycle,
            NSWindowCollectionBehaviorStationary,
        )
        _MAC_NATIVE = True
    except ImportError:
        _MAC_NATIVE = False
else:
    _MAC_NATIVE = False


def _configure_mac_window(widget: QWidget) -> None:
    """Make the underlying NSWindow stay visible across spaces and apps."""
    if not _MAC_NATIVE:
        return
    view_ptr = int(widget.winId())
    ns_view = objc.objc_object(c_void_p=view_ptr)
    ns_window = ns_view.window()
    if ns_window is None:
        return
    ns_window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorStationary
        | NSWindowCollectionBehaviorIgnoresCycle
    )
    ns_window.setLevel_(NSStatusWindowLevel)
    ns_window.setHidesOnDeactivate_(False)


def _hide_dock_icon() -> None:
    if not _MAC_NATIVE:
        return
    NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)


ASSET_DIR = Path(__file__).parent / "assets"

PET_HEIGHT = 150          # 가운데 leader 의 기준 높이
WIDGET_PAD = 30
TICK_MS = 16
HW_SAMPLE_MS = 1500

CPU_EXCITED = 70.0
CPU_SLEEP = 10.0
SLEEP_AFTER_SEC = 90.0
HOT_TEMP_C = 80.0          # CPU temp at which the pet "feels hot"

WANDER_SPEED_PX_S = 55.0
EXCITED_SPEED_PX_S = 220.0

# 한 widget 안 3마리 배치 (좌→우).
# scale: 자기 키 = PET_HEIGHT * scale
# phase_offset: bob phase 라디안 오프셋 → 갤럽 stagger
# bob_scale: 점프 크기 보정 (작은 강아지가 더 통통 튀는 느낌)
PACK_LAYOUT = (
    {"name": "yorkie", "file": "dog_yorkie.png", "scale": 0.78,
     "phase_offset": 0.0, "bob_scale": 1.10},
    {"name": "jindo",  "file": "dog_jindo.png",  "scale": 1.00,
     "phase_offset": 2.094, "bob_scale": 0.90},   # 2π/3
    {"name": "bichon", "file": "dog_bichon.png", "scale": 0.80,
     "phase_offset": 4.189, "bob_scale": 1.15},   # 4π/3
)
PACK_GAP = -10  # 살짝 겹치게


class State:
    WANDER = "wander"
    EXCITED = "excited"
    SLEEPING = "sleeping"


@dataclass
class PackMember:
    name: str
    pixmap: QPixmap
    x_anchor: int          # widget 안 좌측 x (left-facing 기준)
    bob_scale: float
    bob_phase: float = 0.0
    breath_phase: float = 0.0


class StatsBubble(QWidget):
    """Speech bubble shown next to the pet on click."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text = ""
        self.tail_left = True
        self._mac_configured = False
        self.resize(260, 200)

    def set_text(self, text: str) -> None:
        self.text = text
        self.update()

    def set_tail(self, left: bool) -> None:
        if left != self.tail_left:
            self.tail_left = left
            self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._mac_configured:
            _configure_mac_window(self)
            self._mac_configured = True

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(6, 6, -6, -22)
        p.setBrush(QColor(255, 252, 240, 235))
        p.setPen(QPen(QColor(60, 40, 20, 220), 2))
        p.drawRoundedRect(rect, 14, 14)

        tx = rect.left() + 30 if self.tail_left else rect.right() - 30
        tail = QPolygon([
            QPoint(tx - 10, rect.bottom()),
            QPoint(tx + 10, rect.bottom()),
            QPoint(tx + (-6 if self.tail_left else 6), rect.bottom() + 16),
        ])
        p.drawPolygon(tail)

        p.setPen(QColor(30, 20, 10))
        p.setFont(QFont("Menlo", 11))
        p.drawText(
            rect.adjusted(14, 10, -10, -8),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            self.text,
        )


class Pet(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._init_window()
        self._load_pack()
        self._init_runtime()
        self._init_bubble()
        self._init_tray()
        self._init_timers()
        self._place_initial(rest_seconds=5.0)

    def _init_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def _load_pack(self) -> None:
        loaded: list[tuple[dict, QPixmap]] = []
        for spec in PACK_LAYOUT:
            path = ASSET_DIR / spec["file"]
            if not path.exists():
                raise FileNotFoundError(
                    f"Sprite missing: {path}\n"
                    f"먼저 prep_pack_sprites.py 를 실행해 주세요."
                )
            raw = QPixmap(str(path))
            if raw.isNull():
                raise RuntimeError(f"Failed to load: {path}")
            scaled = raw.scaledToHeight(
                int(PET_HEIGHT * spec["scale"]),
                Qt.TransformationMode.SmoothTransformation,
            )
            loaded.append((spec, scaled))

        max_h = max(pix.height() for _, pix in loaded)
        members: list[PackMember] = []
        x = 0
        for spec, pix in loaded:
            members.append(PackMember(
                name=spec["name"],
                pixmap=pix,
                x_anchor=x,
                bob_scale=spec["bob_scale"],
                bob_phase=random.random() * math.tau + spec["phase_offset"],
                breath_phase=random.random() * math.tau,
            ))
            x += pix.width() + PACK_GAP
        x -= PACK_GAP
        self.pack: list[PackMember] = members
        self.pack_w = x
        self.pack_h = max_h
        self.tray_pix = next(m.pixmap for m in self.pack if m.name == "jindo")

        w = self.pack_w + WIDGET_PAD * 2
        h = self.pack_h + WIDGET_PAD * 2 + 12  # 점프 머리 위 여유
        self.resize(w, h)

    def _init_runtime(self) -> None:
        self.state = State.WANDER
        self.flip = False
        self.pos_f = QPointF(0, 0)
        self.target = QPointF(0, 0)
        self.last_active = time.time()
        self.rest_until = 0.0
        self.bubble_until = 0.0
        self.dragging = False
        self.drag_offset = QPoint()
        self._drag_start_pos = QPoint()
        self._drag_started_at = 0.0
        self.paused = False
        self._mac_configured = False
        self.monitor = HwMonitor()
        self.proc_tracker = ProcessTracker()
        self.macmon = MacmonReader(interval_ms=1000)
        self.core_layout = detect_core_layout()
        self.last_snap: HwSnapshot | None = None
        self.bubble_mode = 0  # 0: overview, 1: top CPU, 2: top memory, 3: per-core
        self.NUM_BUBBLE_MODES = 4

    def _init_bubble(self) -> None:
        self.bubble = StatsBubble()

    def _init_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        icon_pix = self.tray_pix.scaled(
            32, 32,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.tray.setIcon(QIcon(icon_pix))
        self.tray.setToolTip("Desktop Pet")

        menu = QMenu()
        a_stats = QAction("통계 보기", self)
        a_stats.triggered.connect(lambda: self.show_stats(8.0))
        menu.addAction(a_stats)

        a_pause = QAction("일시정지/재개", self)
        a_pause.triggered.connect(self.toggle_pause)
        menu.addAction(a_pause)

        a_recall = QAction("우하단으로 호출", self)
        a_recall.triggered.connect(lambda: self._place_initial(rest_seconds=20.0))
        menu.addAction(a_recall)

        menu.addSeparator()
        a_quit = QAction("종료", self)
        a_quit.triggered.connect(QApplication.quit)
        menu.addAction(a_quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _init_timers(self) -> None:
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._on_tick)
        self.tick_timer.start(TICK_MS)

        self.hw_timer = QTimer(self)
        self.hw_timer.timeout.connect(self._on_hw)
        self.hw_timer.start(HW_SAMPLE_MS)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._mac_configured:
            _configure_mac_window(self)
            self._mac_configured = True

    def _screen_rect(self):
        return QApplication.primaryScreen().availableGeometry()

    def _place_initial(self, rest_seconds: float = 20.0) -> None:
        if not self.isVisible():
            self.show()
        self.raise_()
        s = self._screen_rect()
        x = s.right() - self.width() - 20
        y = s.bottom() - self.height() - 20
        self.move(x, y)
        self.pos_f = QPointF(x, y)
        self.target = QPointF(x, y)
        self.rest_until = time.time() + rest_seconds

    def _pick_new_target(self) -> None:
        s = self._screen_rect()
        x = random.randint(s.left() + 10, s.right() - self.width() - 10)
        y_min = s.top() + s.height() // 2
        y_max = s.bottom() - self.height() - 20
        y = random.randint(y_min, max(y_min + 1, y_max))
        self.target = QPointF(x, y)
        self.rest_until = 0.0

    def _on_hw(self) -> None:
        snap = self.monitor.sample()
        self.last_snap = snap
        try:
            self.proc_tracker.sample(top_n=3)
        except Exception:
            pass
        now = time.time()
        prev_state = self.state

        if snap.cpu >= CPU_EXCITED:
            new_state = State.EXCITED
            self.last_active = now
        elif snap.cpu < CPU_SLEEP and (now - self.last_active) > SLEEP_AFTER_SEC:
            new_state = State.SLEEPING
        else:
            new_state = State.WANDER
            if snap.cpu >= CPU_SLEEP:
                self.last_active = now

        self.state = new_state

        if new_state == State.EXCITED and prev_state != State.EXCITED:
            self._pick_new_target()
        elif prev_state == State.SLEEPING and new_state != State.SLEEPING:
            self.rest_until = 0.0

        if self.bubble.isVisible() and now < self.bubble_until:
            self.bubble.set_text(self._current_bubble_text())

    def _format_stats(self, s: HwSnapshot) -> str:
        lines = [
            f"CPU   {s.cpu:5.1f} %",
            f"MEM   {s.memory:5.1f} %",
        ]
        t = self.macmon.latest()
        if t is not None and t.cpu_temp_c is not None:
            tag = "  🔥 더워!" if t.cpu_temp_c >= HOT_TEMP_C else ""
            gpu_part = f"  GPU {t.gpu_temp_c:.0f}°C" if t.gpu_temp_c is not None else ""
            lines.append(f"TEMP  CPU {t.cpu_temp_c:.0f}°C{gpu_part}{tag}")
            if t.cpu_power_w is not None:
                gpu_pw = f"  GPU {t.gpu_power_w:.1f}" if t.gpu_power_w is not None else ""
                lines.append(f"PWR   CPU {t.cpu_power_w:.1f}{gpu_pw}  W")
        lines.append(f"DISK  R {s.disk_read_mbps:5.1f}  W {s.disk_write_mbps:5.1f}  MB/s")
        lines.append(f"NET   ↓ {s.net_recv_mbps:5.1f}  ↑ {s.net_sent_mbps:5.1f}  MB/s")
        return "\n".join(lines)

    @staticmethod
    def _format_top(title: str, entries: list[ProcEntry], unit_fn) -> str:
        if not entries:
            return f"{title}\n  수집 중...  멍?"
        lines = [title]
        for e in entries:
            name = e.name if len(e.name) <= 18 else e.name[:17] + "…"
            lines.append(f"  {name:<18} {unit_fn(e)}")
        lines.append("           멍! 멍!")
        return "\n".join(lines)

    def _current_bubble_text(self) -> str:
        if self.last_snap is None:
            return "샘플링 중...  멍?"
        if self.bubble_mode == 0:
            return self._format_stats(self.last_snap)
        if self.bubble_mode == 1:
            return self._format_top(
                "🐾 CPU 많이 먹는 친구!",
                self.proc_tracker.top_cpu,
                lambda e: f"{e.cpu:5.1f} %",
            )
        if self.bubble_mode == 2:
            return self._format_top(
                "🐾 메모리 많이 먹는 친구!",
                self.proc_tracker.top_mem,
                lambda e: f"{e.mem_mb:6.0f} MB",
            )
        if self.bubble_mode == 3:
            return self._format_per_core(self.last_snap.per_core, self.core_layout)
        return ""

    @staticmethod
    def _bar(pct: float, width: int = 5) -> str:
        filled = int(round(max(0.0, min(100.0, pct)) / 100.0 * width))
        return "█" * filled + "░" * (width - filled)

    @classmethod
    def _format_per_core(cls, cores: list[float], layout: CoreLayout) -> str:
        if not cores:
            return "코어 정보 수집 중...  멍?"

        def line(idx: int) -> str:
            return f"{layout.label(idx):<3}{cls._bar(cores[idx], 5)} {cores[idx]:3.0f}"

        lines = ["🐾 코어별 점유율"]

        def emit_pairs(start: int, count: int) -> None:
            half = (count + 1) // 2
            for i in range(half):
                left = line(start + i)
                right_idx = start + i + half
                right = line(right_idx) if right_idx < start + count else ""
                lines.append(f"{left}   {right}".rstrip())

        if layout.is_apple_silicon and layout.n_e > 0:
            emit_pairs(0, layout.n_p)
            emit_pairs(layout.n_p, layout.n_e)
        else:
            emit_pairs(0, len(cores))
        return "\n".join(lines)

    def _on_tick(self) -> None:
        if self.paused or self.dragging:
            self.update()
            self._sync_bubble_pos()
            return

        dt = TICK_MS / 1000.0
        hot = self._is_hot()
        # 뛰는 모션을 위해 평소 wander 도 빠른 bob.
        bob_rate = 9.0 if self.state == State.EXCITED else 6.0
        breath_rate = 4.0 if self.state == State.EXCITED else 2.5
        if hot:
            breath_rate = max(breath_rate, 3.5)
            bob_rate = max(bob_rate, 7.0)
        if self.state == State.SLEEPING:
            bob_rate = 0.8
            breath_rate = 1.2

        for m in self.pack:
            m.bob_phase += dt * bob_rate
            m.breath_phase += dt * breath_rate

        if self.state == State.SLEEPING:
            speed = 0.0
        elif self.state == State.EXCITED:
            speed = EXCITED_SPEED_PX_S
        else:
            speed = WANDER_SPEED_PX_S

        if speed > 0.0:
            dx = self.target.x() - self.pos_f.x()
            dy = self.target.y() - self.pos_f.y()
            dist = math.hypot(dx, dy)
            now = time.time()
            if dist < 4.0:
                if self.rest_until == 0.0:
                    rest_range = (1.0, 4.0) if self.state == State.EXCITED else (3.0, 10.0)
                    self.rest_until = now + random.uniform(*rest_range)
                elif now >= self.rest_until:
                    self._pick_new_target()
            else:
                step = min(speed * dt, dist)
                self.pos_f = QPointF(
                    self.pos_f.x() + dx / dist * step,
                    self.pos_f.y() + dy / dist * step,
                )
                self.flip = dx < 0

        s = self._screen_rect()
        x = max(s.left(), min(s.right() - self.width(), int(self.pos_f.x())))
        y = max(s.top(), min(s.bottom() - self.height(), int(self.pos_f.y())))
        self.move(x, y)

        self.update()
        self._sync_bubble_pos()

        if self.bubble.isVisible() and time.time() > self.bubble_until:
            self.bubble.hide()
            self.bubble_mode = 0

    def _sync_bubble_pos(self) -> None:
        if not self.bubble.isVisible():
            return
        s = self._screen_rect()
        right_room = s.right() - (self.x() + self.width())
        left_room = self.x() - s.left()
        place_right = right_room >= self.bubble.width() or right_room >= left_room
        if place_right:
            bx = self.x() + self.width() - 10
            self.bubble.set_tail(left=True)
        else:
            bx = self.x() - self.bubble.width() + 10
            self.bubble.set_tail(left=False)
        by = self.y() - self.bubble.height() + 30
        by = max(s.top(), by)
        self.bubble.move(bx, by)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 점프 크기. 평소에도 뛰는 느낌 + EXCITED 면 더 크게.
        base_amp = 12.0 if self.state == State.EXCITED else 7.0
        if self.state == State.SLEEPING:
            base_amp = 1.5

        for m in self.pack:
            breath = 1.0 + 0.04 * math.sin(m.breath_phase)
            if self.state == State.EXCITED:
                breath *= 1.05
            sw = int(m.pixmap.width() * breath)
            sh = int(m.pixmap.height() * breath)
            sprite = m.pixmap.scaled(
                sw, sh,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if self.flip:
                sprite = sprite.transformed(QTransform().scale(-1, 1))

            # bob: sin 의 양수부만 → 땅에 붙어 있다가 위로 살짝 점프
            s_phase = math.sin(m.bob_phase)
            hop = max(0.0, s_phase) * base_amp * m.bob_scale

            slot_w = m.pixmap.width()
            ax = m.x_anchor
            if self.flip:
                ax = self.pack_w - m.x_anchor - slot_w
            # breath 로 폭이 변하므로 슬롯 안 가운데 정렬
            ax += (slot_w - sprite.width()) // 2
            cx = WIDGET_PAD + ax
            # 바닥 정렬 (가장 큰 강아지 발 = pack_h). 위로 hop 만큼 들림.
            cy = WIDGET_PAD + (self.pack_h - sprite.height()) - hop + 12
            p.drawPixmap(int(cx), int(cy), sprite)

        if self.state == State.SLEEPING:
            self._draw_zzz(
                p,
                WIDGET_PAD + self.pack_w - 30,
                WIDGET_PAD + 20,
            )

    def _draw_zzz(self, p: QPainter, x: int, y: int) -> None:
        p.setPen(QColor(80, 80, 200))
        offset = int(math.sin(self.pack[0].bob_phase) * 4)
        p.setFont(QFont("Helvetica", 22, QFont.Weight.Bold))
        p.drawText(x, y + offset, "Z")
        p.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
        p.drawText(x - 18, y + 18 + offset, "z")
        p.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        p.drawText(x - 32, y + 32 + offset, "z")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            self._drag_started_at = time.time()
            self._drag_start_pos = event.globalPosition().toPoint()
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu.addAction("통계 보기", lambda: self.show_stats(8.0))
            menu.addAction("일시정지/재개", self.toggle_pause)
            menu.addAction("우하단으로 호출", lambda: self._place_initial(rest_seconds=20.0))
            menu.addSeparator()
            menu.addAction("종료", QApplication.quit)
            menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.dragging:
            new_pos = event.globalPosition().toPoint() - self.drag_offset
            self.move(new_pos)
            self.pos_f = QPointF(new_pos.x(), new_pos.y())

    def mouseReleaseEvent(self, event):
        if not self.dragging or event.button() != Qt.MouseButton.LeftButton:
            self.dragging = False
            return
        self.dragging = False
        moved = (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength()
        if moved < 6 and (time.time() - self._drag_started_at) < 0.4:
            self.show_stats(6.0, advance=True)
            self.target = QPointF(self.pos_f)
            self.rest_until = time.time() + 4.0
        else:
            self.target = QPointF(self.pos_f)
            self.rest_until = time.time() + random.uniform(5.0, 12.0)

    def show_stats(self, seconds: float = 5.0, advance: bool = False) -> None:
        if advance and self.bubble.isVisible():
            self.bubble_mode = (self.bubble_mode + 1) % self.NUM_BUBBLE_MODES
        elif not self.bubble.isVisible():
            self.bubble_mode = 0
        self.bubble.show()
        self.bubble_until = time.time() + seconds
        self.bubble.set_text(self._current_bubble_text())
        self._sync_bubble_pos()

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def _is_hot(self) -> bool:
        t = self.macmon.latest()
        return t is not None and t.cpu_temp_c is not None and t.cpu_temp_c >= HOT_TEMP_C

    def cleanup(self) -> None:
        try:
            self.macmon.stop()
        except Exception:
            pass


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    _hide_dock_icon()
    pet = Pet()
    pet.show()
    app.aboutToQuit.connect(pet.cleanup)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
