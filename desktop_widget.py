# -*- coding: utf-8 -*-
"""
Desktop Widget – Thời tiết · Lịch âm dương · Việc cần làm · Ghi chú
Widget nền trong suốt cho Windows, chạy ở khay hệ thống, tự khởi động cùng máy.
"""
import os
import sys
import html
import json
import uuid
import ctypes
import shutil
import tempfile
import threading
import traceback
import subprocess
import datetime as dt
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QPoint, QPointF, QRect, QRectF, QLockFile, QDate, QLocale  # noqa: E402
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap, QCursor, QGuiApplication  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QFrame,
    QToolButton, QPushButton, QLineEdit, QPlainTextEdit, QCheckBox, QScrollArea, QSizeGrip,
    QSizePolicy, QMenu, QSystemTrayIcon, QDialog, QDialogButtonBox, QCalendarWidget, QInputDialog,
    QMessageBox, QTabWidget, QTabBar, QSlider, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget,
    QListWidgetItem, QColorDialog, QToolTip,
)

import amlich_vn as al  # noqa: E402
import core  # noqa: E402

VERSION = "1.0.1"
IS_WIN = core.IS_WIN
FROZEN = getattr(sys, "frozen", False)
SCRIPT = os.path.abspath(__file__)
ERRORS = []          # dùng cho --selftest


def log_error(text):
    try:
        with open(core.path_of("error.log"), "a", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] v{VERSION}\n{text}\n")
    except Exception:
        pass


# =============================================================== Win32 (ctypes)
GWLP_HWNDPARENT = -8
if IS_WIN:
    from ctypes import wintypes
    _user32 = ctypes.windll.user32
    _SetWLP = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
    _SetWLP.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _SetWLP.restype = ctypes.c_ssize_t
    _user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _user32.FindWindowW.restype = wintypes.HWND

    class _ACCENT(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                    ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

    class _WCAD(ctypes.Structure):
        _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


def win_find_progman():
    if not IS_WIN:
        return 0
    try:
        return _user32.FindWindowW("Progman", None) or 0
    except Exception:
        return 0


def win_set_owner(hwnd, owner):
    """Gắn cửa sổ vào desktop (Progman) để không bị ẩn khi bấm Win+D."""
    if not IS_WIN:
        return
    try:
        _SetWLP(hwnd, GWLP_HWNDPARENT, owner or 0)
    except Exception:
        pass


def win_set_blur(hwnd, on):
    if not IS_WIN:
        return
    try:
        accent = _ACCENT(3 if on else 0, 0, 0, 0)          # 3 = ACCENT_ENABLE_BLURBEHIND
        data = _WCAD(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent))
        _user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd), ctypes.byref(data))
    except Exception:
        pass


# =============================================================== HTTP chạy nền
class Http(QObject):
    finished = Signal(str, object, str)      # tag, dữ liệu json, lỗi

    def get_json(self, tag, url, timeout=15):
        def run():
            data, err = None, ""
            try:
                req = urllib.request.Request(url, headers={"User-Agent": f"DesktopWidget/{VERSION}"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                try:
                    err += ": " + str(json.loads(e.read().decode("utf-8")).get("reason", ""))
                except Exception:
                    pass
            except urllib.error.URLError as e:
                err = f"không kết nối được mạng ({e.reason})"
            except Exception as e:
                err = str(e) or e.__class__.__name__
            try:
                self.finished.emit(tag, data, err)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()


# =============================================================== Giao diện: màu & stylesheet
def lum(c):
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def qss_color(c, a=1.0):
    ai = int(round(max(0.0, min(1.0, a)) * 255))
    if ai == 1:            # Qt hiểu giá trị <=1 là tỉ lệ 0..1
        ai = 2
    return f"rgba({c.red()},{c.green()},{c.blue()},{ai})"


class Theme:
    def __init__(self, cfg):
        self.cfg = cfg

    def s(self):
        return max(0.6, self.cfg.get("scale", 100) / 100.0)

    @property
    def text(self):
        return QColor(self.cfg["text_color"])

    @property
    def accent(self):
        return QColor(self.cfg["accent_color"])

    @property
    def bg(self):
        return QColor(self.cfg["bg_color"])

    def light_text(self):
        return lum(self.text) > 140

    def sub(self, a):
        c = QColor(self.text)
        c.setAlphaF(a)
        return c

    def _pick(self, on_dark, on_light):
        return QColor(on_dark if self.light_text() else on_light)

    @property
    def sunday(self):
        return self._pick("#ff8a80", "#d32f2f")

    @property
    def holiday(self):
        return self._pick("#ffd54f", "#e65100")

    @property
    def danger(self):
        return self._pick("#ff6e6e", "#c62828")

    @property
    def warn(self):
        return self._pick("#ffb74d", "#ef6c00")

    @property
    def rain(self):
        return self._pick("#81d4fa", "#0277bd")

    @property
    def dot(self):
        return self._pick("#ff7043", "#e64a19")

    def font(self, pt, weight=QFont.Weight.Normal):
        f = QFont("Segoe UI")
        f.setPointSizeF(max(6.0, pt * self.s()))
        f.setWeight(weight)
        return f


def build_qss(th):
    s = th.s()

    def pt(v):
        return f"{v * s:.1f}pt"

    C = qss_color
    t, acc, bg = th.text, th.accent, th.bg
    field = QColor(255, 255, 255) if th.light_text() else QColor(0, 0, 0)
    menu_bg = QColor(bg)
    menu_bg.setAlpha(255)
    acc_txt = "#000000" if lum(acc) > 150 else "#ffffff"
    ind = max(11, int(13 * s))
    return f"""
QWidget#content {{ color: {C(t)}; font-family: "Segoe UI", "Arial"; font-size: {pt(10)}; }}
QLabel {{ color: {C(t)}; background: transparent; font-size: {pt(10)}; }}
QLabel[sub="true"] {{ color: {C(t, .64)}; font-size: {pt(9)}; }}
QLabel#section {{ color: {C(t, .55)}; font-size: {pt(8)}; font-weight: 700; }}
QLabel#clock {{ font-size: {pt(34)}; font-weight: 300; }}
QLabel#clockSec {{ color: {C(t, .55)}; font-size: {pt(14)}; font-weight: 300; }}
QLabel#date {{ font-size: {pt(12)}; font-weight: 600; }}
QLabel#lunar {{ color: {C(acc)}; font-size: {pt(10.5)}; font-weight: 600; }}
QLabel#holiday {{ color: {C(th.holiday)}; font-size: {pt(9.5)}; font-weight: 600; }}
QLabel#wIcon {{ font-family: "Segoe UI Emoji"; font-size: {pt(26)}; }}
QLabel#wTemp {{ font-size: {pt(26)}; font-weight: 300; }}
QLabel#wDesc {{ font-size: {pt(11)}; font-weight: 600; }}
QLabel#fDay {{ color: {C(t, .6)}; font-size: {pt(8.5)}; font-weight: 600; }}
QLabel#fIcon {{ font-family: "Segoe UI Emoji"; font-size: {pt(13)}; }}
QLabel#fTemp {{ font-size: {pt(9)}; }}
QLabel#fRain {{ color: {C(th.rain)}; font-size: {pt(8)}; }}
QLabel#calTitle {{ font-size: {pt(10.5)}; font-weight: 600; }}
QLabel#taskText {{ font-size: {pt(10)}; }}
QLabel#taskText[done="true"] {{ color: {C(t, .42)}; }}
QLabel#taskText[important="true"] {{ font-weight: 700; }}
QLabel#due {{ color: {C(t, .6)}; font-size: {pt(8.5)}; }}
QLabel#due[state="over"] {{ color: {C(th.danger)}; font-weight: 600; }}
QLabel#due[state="today"] {{ color: {C(th.warn)}; font-weight: 600; }}
QLabel#due[state="soon"] {{ color: {C(acc)}; }}
QFrame#sep {{ background: {C(t, .13)}; border: none; min-height: 1px; max-height: 1px; }}
QLineEdit, QPlainTextEdit {{
    background: {C(field, .07)}; color: {C(t)}; border: 1px solid {C(field, .15)}; border-radius: 7px;
    padding: 4px 6px; selection-background-color: {C(acc, .85)}; selection-color: {acc_txt}; font-size: {pt(10)}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {C(acc, .9)}; }}
QToolButton {{ background: transparent; color: {C(t, .8)}; border: none; border-radius: 6px; padding: 2px 6px; font-size: {pt(10)}; }}
QToolButton:hover {{ background: {C(t, .13)}; color: {C(t)}; }}
QToolButton:disabled {{ color: {C(t, .35)}; }}
QToolButton#del {{ color: {C(t, .35)}; padding: 0px 4px; }}
QToolButton#del:hover {{ color: {C(th.danger)}; }}
QCheckBox {{ spacing: 0px; background: transparent; }}
QCheckBox::indicator {{ width: {ind}px; height: {ind}px; border: 1px solid {C(t, .55)}; border-radius: 4px; background: transparent; }}
QCheckBox::indicator:hover {{ border: 1px solid {C(acc)}; }}
QCheckBox::indicator:checked {{ background: {C(acc)}; border: 1px solid {C(acc)}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget#qt_scrollarea_viewport {{ background: transparent; }}
QWidget#listHost {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0px; }}
QScrollBar::handle:vertical {{ background: {C(t, .25)}; border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {C(t, .4)}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {C(t, .5)}; border: none; border-bottom: 2px solid transparent;
    padding: 2px 9px 3px 9px; margin-right: 2px; font-size: {pt(9)}; }}
QTabBar::tab:selected {{ color: {C(t)}; border-bottom: 2px solid {C(acc)}; }}
QTabBar::tab:hover:!selected {{ color: {C(t, .85)}; }}
QTabBar QToolButton {{ background: {C(menu_bg)}; border: none; }}
QMenu {{ background: {C(menu_bg)}; color: {C(t)}; border: 1px solid {C(t, .2)}; padding: 4px; }}
QMenu::item {{ padding: 5px 20px 5px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C(acc)}; color: {acc_txt}; }}
QMenu::separator {{ height: 1px; background: {C(t, .15)}; margin: 4px 6px; }}
"""


def build_outer_qss(th):
    C = qss_color
    t = th.text
    return f"""
QScrollArea#outerScroll {{ background: transparent; border: none; }}
QScrollArea#outerScroll > QWidget#qt_scrollarea_viewport {{ background: transparent; }}
QScrollArea#outerScroll > QScrollBar:vertical {{ background: transparent; width: 6px; margin: 10px 2px 18px 0px; }}
QScrollArea#outerScroll > QScrollBar::handle:vertical {{ background: {C(t, .25)}; border-radius: 3px; min-height: 30px; }}
QScrollArea#outerScroll > QScrollBar::add-line:vertical, QScrollArea#outerScroll > QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollArea#outerScroll > QScrollBar::add-page:vertical, QScrollArea#outerScroll > QScrollBar::sub-page:vertical {{ background: none; }}
"""


# =============================================================== tiện ích tạo widget
def named_label(name, text=""):
    lb = QLabel(text)
    lb.setObjectName(name)
    return lb


def sub_label(text="", wrap=False):
    lb = QLabel(text)
    lb.setProperty("sub", True)
    lb.setWordWrap(wrap)
    return lb


def tool_btn(text, tip="", slot=None, name=None):
    b = QToolButton()
    b.setText(text)
    if tip:
        b.setToolTip(tip)
    if name:
        b.setObjectName(name)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot is not None:
        b.clicked.connect(lambda _=False: slot())
    return b


def make_action(parent, text, slot=None, checkable=False, checked=False):
    a = QAction(text, parent)
    if checkable:
        a.setCheckable(True)
        a.setChecked(bool(checked))
        if slot is not None:
            a.toggled.connect(slot)
    elif slot is not None:
        a.triggered.connect(lambda _=False: slot())
    return a


def later(fn):
    """Chạy fn sau khi menu đóng hẳn (tránh xóa widget đang mở menu)."""
    return lambda: QTimer.singleShot(0, fn)


def make_icon(day, accent="#4fc3f7", size=64):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    k = size / 64.0
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(4 * k, 6 * k, 56 * k, 54 * k), 10 * k, 10 * k)
    p.setBrush(QColor(accent))
    p.drawRoundedRect(QRectF(4 * k, 6 * k, 56 * k, 18 * k), 10 * k, 10 * k)
    p.drawRect(QRectF(4 * k, 16 * k, 56 * k, 8 * k))
    f = QFont("Segoe UI")
    f.setPixelSize(int(30 * k))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1b2330"))
    p.drawText(QRectF(4 * k, 23 * k, 56 * k, 37 * k), Qt.AlignmentFlag.AlignCenter, str(day))
    p.end()
    return QIcon(pm)


def pick_date(initial=None, title="Chọn ngày hạn"):
    """Hộp chọn ngày. Trả về ('set', date) | ('clear', None) | ('cancel', None)."""
    dlg = QDialog(None)
    dlg.setWindowTitle(title)
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    cal = QCalendarWidget()
    cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
    cal.setGridVisible(True)
    cal.setLocale(QLocale(QLocale.Language.Vietnamese))
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    d0 = initial or dt.date.today()
    cal.setSelectedDate(QDate(d0.year, d0.month, d0.day))
    bb = QDialogButtonBox()
    bb.addButton("Chọn", QDialogButtonBox.ButtonRole.AcceptRole)
    clr = bb.addButton("Không đặt hạn", QDialogButtonBox.ButtonRole.ResetRole)
    bb.addButton("Hủy", QDialogButtonBox.ButtonRole.RejectRole)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    clr.clicked.connect(lambda _=False: dlg.done(2))
    cal.activated.connect(lambda _d: dlg.accept())
    v = QVBoxLayout(dlg)
    v.addWidget(cal)
    v.addWidget(bb)
    dlg.move(QCursor.pos() - QPoint(170, 60))
    r = dlg.exec()
    if r == 1:
        q = cal.selectedDate()
        return "set", dt.date(q.year(), q.month(), q.day())
    if r == 2:
        return "clear", None
    return "cancel", None


# =============================================================== các khối nội dung
class Section(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(5)
        self.sep = QFrame()
        self.sep.setObjectName("sep")
        self.sep.setFixedHeight(1)
        self.v.addWidget(self.sep)


class ClockSection(Section):
    def __init__(self, app):
        super().__init__(app)
        row = QHBoxLayout()
        row.setSpacing(3)
        self.lbl_time = named_label("clock", "--:--")
        self.lbl_sec = named_label("clockSec", "")
        row.addWidget(self.lbl_time, 0, Qt.AlignmentFlag.AlignBottom)
        row.addWidget(self.lbl_sec, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        self.v.addLayout(row)
        self.lbl_date = named_label("date")
        self.lbl_lunar = named_label("lunar")
        self.lbl_lunar.setWordWrap(True)
        self.lbl_canchi = sub_label(wrap=True)
        self.lbl_gio = sub_label(wrap=True)
        self.lbl_le = named_label("holiday")
        self.lbl_le.setWordWrap(True)
        for w in (self.lbl_date, self.lbl_lunar, self.lbl_canchi, self.lbl_gio, self.lbl_le):
            self.v.addWidget(w)

    def tick(self, now):
        self.lbl_time.setText(now.strftime("%H:%M"))
        if self.app.cfg["show_seconds"]:
            self.lbl_sec.setText(now.strftime(":%S"))

    def refresh_day(self, today):
        info = al.day_info(today)
        self.lbl_date.setText(f"{info['thu']}, {today.day} tháng {today.month}, {today.year}")
        self.lbl_lunar.setText(f"🌙 Âm lịch: {info['lunar_day']} {info['ten_thang']}, năm {info['nam']}")
        self.lbl_canchi.setText(f"Ngày {info['ngay']} · Tháng {info['thang']} · Tiết {info['tiet_khi']}")
        self.lbl_gio.setText("Giờ hoàng đạo: " + ", ".join(info["gio_hd"]))
        extra = ["🎉 " + x for x in info["le"]]
        try:
            n, nam = al.days_to_tet(today)
            if 0 < n <= 100:
                extra.append(f"⏳ Còn {n} ngày đến Tết {nam}")
        except Exception:
            pass
        self.lbl_le.setText("\n".join(extra))
        self.lbl_le.setVisible(bool(extra))


class WeatherSection(Section):
    def __init__(self, app):
        super().__init__(app)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(named_label("section", "THỜI TIẾT"))
        self.lbl_loc = sub_label()
        head.addWidget(self.lbl_loc)
        head.addStretch(1)
        self.btn = tool_btn("⟳", "Cập nhật thời tiết", lambda: app.fetch_weather(manual=True))
        head.addWidget(self.btn)
        self.v.addLayout(head)

        main = QHBoxLayout()
        main.setSpacing(10)
        self.lbl_icon = named_label("wIcon", "🌡️")
        self.lbl_temp = named_label("wTemp", "--°")
        col = QVBoxLayout()
        col.setSpacing(1)
        self.lbl_desc = named_label("wDesc", "Đang tải thời tiết…")
        self.lbl_detail = sub_label(wrap=True)
        col.addWidget(self.lbl_desc)
        col.addWidget(self.lbl_detail)
        main.addWidget(self.lbl_icon)
        main.addWidget(self.lbl_temp)
        main.addLayout(col, 1)
        self.v.addLayout(main)

        self.lbl_sun = sub_label()
        self.v.addWidget(self.lbl_sun)

        grid = QGridLayout()
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(0)
        self.fc = []
        for i in range(5):
            cells = [named_label("fDay"), named_label("fIcon"), named_label("fTemp"), named_label("fRain")]
            for r, lb in enumerate(cells):
                lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(lb, r, i)
            self.fc.append(cells)
        self.v.addLayout(grid)

        self.lbl_status = sub_label(wrap=True)
        self.lbl_status.hide()
        self.v.addWidget(self.lbl_status)
        self.update_loc()

    def update_loc(self):
        name = self.app.cfg["weather"]["name"] or ""
        self.lbl_loc.setText("· " + name.split(",")[0].strip() if name else "")
        self.lbl_loc.setToolTip(name)

    def set_loading(self, on):
        self.btn.setEnabled(not on)
        self.btn.setText("…" if on else "⟳")

    def show_weather(self, w):
        desc, icon = core.wmo(w.get("code"), w.get("is_day", 1))
        self.lbl_icon.setText(icon)
        self.lbl_temp.setText(core.fmt_temp(w.get("temp")))
        self.lbl_desc.setText(desc)
        parts = []
        if w.get("feels") is not None:
            parts.append(f"Cảm giác {core.fmt_temp(w['feels'])}")
        if w.get("humidity") is not None:
            parts.append(f"Ẩm {round(w['humidity'])}%")
        if w.get("wind") is not None:
            parts.append(f"Gió {round(w['wind'])} km/h")
        self.lbl_detail.setText(" · ".join(parts))

        today_s = dt.date.today().isoformat()
        days = w.get("days") or []
        td = next((d for d in days if d.get("date") == today_s), days[0] if days else None)
        fetched = ""
        try:
            f_dt = dt.datetime.fromisoformat(w.get("fetched"))
            fetched = f_dt.strftime("%H:%M") if f_dt.date() == dt.date.today() else f_dt.strftime("%H:%M %d/%m")
        except Exception:
            f_dt = None
        sun = ""
        if td:
            sun = f"🌅 {core.hhmm(td.get('sunrise'))}   🌇 {core.hhmm(td.get('sunset'))}"
        if fetched:
            sun += ("   · " if sun else "") + f"cập nhật {fetched}"
        self.lbl_sun.setText(sun)

        fdays = [d for d in days if (d.get("date") or "") >= today_s][:5]
        for i, cells in enumerate(self.fc):
            if i < len(fdays):
                d = fdays[i]
                try:
                    dd = dt.date.fromisoformat(d["date"])
                    name = "Nay" if d["date"] == today_s else al.THU_NGAN[dd.weekday()]
                except Exception:
                    name = ""
                cells[0].setText(name)
                cells[1].setText(core.wmo(d.get("code"), 1)[1])
                cells[1].setToolTip(core.wmo(d.get("code"), 1)[0])
                cells[2].setText(f"{core.fmt_temp(d.get('tmax'))}/{core.fmt_temp(d.get('tmin'))}")
                cells[3].setText(f"💧{round(d['rain'])}%" if d.get("rain") is not None else "")
            else:
                for c in cells:
                    c.setText("")
        stale = f_dt is not None and (dt.datetime.now() - f_dt).total_seconds() > 3 * 3600
        if stale:
            self.lbl_status.setText(f"⚠ Dữ liệu cũ lúc {fetched} – chưa cập nhật được.")
            self.lbl_status.show()
        else:
            self.lbl_status.hide()

    def show_error(self, msg):
        self.lbl_status.setText("⚠ Chưa cập nhật được thời tiết: " + str(msg)[:140])
        self.lbl_status.show()
        if self.app.weather_data is None:
            self.lbl_desc.setText("Chưa có dữ liệu")


class MonthCalendar(QWidget):
    month_changed = Signal()
    day_clicked = Signal(object)

    def __init__(self, app):
        super().__init__()
        self.app = app
        t = app.today
        self.year, self.month = t.year, t.month
        self.selected = None
        self._cells = []
        self._hover = None
        self._lunar = {}
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_metrics()

    def update_metrics(self):
        s = self.app.theme.s()
        self.head_h = int(round(17 * s))
        self.cell_h = int(round(30 * s))
        self.setFixedHeight(self.head_h + 6 * self.cell_h + 2)
        self.update()

    def lunar_of(self, d):
        v = self._lunar.get(d)
        if v is None:
            ld, lm, ly, leap = al.solar_to_lunar(d.day, d.month, d.year)
            le = al.ngay_le(d.day, d.month, d.year, ld, lm, ly, leap)
            v = (ld, lm, leap, le)
            self._lunar[d] = v
        return v

    def shift(self, n):
        m0 = self.month - 1 + n
        self.year += m0 // 12
        self.month = m0 % 12 + 1
        self.update()
        self.month_changed.emit()

    def go_today(self):
        t = self.app.today
        self.year, self.month = t.year, t.month
        self.selected = None
        self.day_clicked.emit(None)
        self.update()
        self.month_changed.emit()

    def paintEvent(self, e):
        th = self.app.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cw = self.width() / 7.0
        p.setFont(th.font(8, QFont.Weight.DemiBold))
        for i, name in enumerate(al.THU_NGAN):
            p.setPen(th.sunday if i == 6 else th.sub(0.6))
            p.drawText(QRectF(i * cw, 0, cw, self.head_h), Qt.AlignmentFlag.AlignCenter, name)

        first = dt.date(self.year, self.month, 1)
        start = first - dt.timedelta(days=first.weekday())
        today = self.app.today
        due = self.app.due_dates()
        f_day = th.font(10.5, QFont.Weight.DemiBold)
        f_lunar = th.font(7)
        acc = th.accent
        on_acc = QColor("#000000") if lum(acc) > 150 else QColor("#ffffff")
        self._cells = []
        for idx in range(42):
            d = start + dt.timedelta(days=idx)
            r, c = divmod(idx, 7)
            rect = QRectF(c * cw, self.head_h + r * self.cell_h, cw, self.cell_h)
            self._cells.append((rect, d))
            inner = rect.adjusted(2, 1.5, -2, -1.5)
            in_month = d.month == self.month
            ld, lm, leap, le = self.lunar_of(d)
            is_today = d == today

            if is_today:
                bg = QColor(acc)
                bg.setAlpha(235)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(inner, 6, 6)
                main = QColor(on_acc)
                lun = QColor(on_acc)
                lun.setAlphaF(0.8)
            else:
                if d == self.selected:
                    pen = QPen(acc)
                    pen.setWidthF(1.3)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(inner, 6, 6)
                main = QColor(th.text) if in_month else th.sub(0.30)
                if c == 6:
                    main = QColor(th.sunday)
                    if not in_month:
                        main.setAlphaF(0.35)
                if le and in_month:
                    main = QColor(th.holiday)
                lun = th.sub(0.55 if in_month else 0.22)
                if ld in (1, 15) and in_month:
                    lun = QColor(acc)

            top = QRectF(inner.x(), inner.y(), inner.width(), inner.height() * 0.58)
            bot = QRectF(inner.x(), inner.y() + inner.height() * 0.58, inner.width(), inner.height() * 0.42)
            p.setFont(f_day)
            p.setPen(main)
            p.drawText(top, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, str(d.day))
            lt = f"{ld}/{lm}" + ("N" if leap else "") if ld == 1 else str(ld)
            p.setFont(f_lunar)
            p.setPen(lun)
            p.drawText(bot, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, lt)
            if d.isoformat() in due:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(on_acc if is_today else th.dot)
                p.drawEllipse(QPointF(inner.right() - 5, inner.top() + 5), 2.5, 2.5)
        p.end()

    def cell_at(self, pos):
        for rect, d in self._cells:
            if rect.contains(pos):
                return d
        return None

    def mouseMoveEvent(self, e):
        d = self.cell_at(e.position())
        if d is None:
            self._hover = None
            QToolTip.hideText()
        elif d != self._hover:
            self._hover = d
            QToolTip.showText(e.globalPosition().toPoint(), self.app.day_tooltip(d), self)

    def leaveEvent(self, e):
        self._hover = None
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        d = self.cell_at(e.position())
        if d is not None:
            if d.month != self.month or d.year != self.year:
                self.year, self.month = d.year, d.month
                self.month_changed.emit()
            self.selected = None if d == self.selected else d
            self.day_clicked.emit(self.selected)
            self.update()
        e.accept()

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if dy:
            self.shift(-1 if dy > 0 else 1)
        e.accept()


class CalendarSection(Section):
    def __init__(self, app):
        super().__init__(app)
        self.cal = MonthCalendar(app)
        head = QHBoxLayout()
        head.setSpacing(2)
        self.title = named_label("calTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(tool_btn("‹", "Tháng trước", lambda: self.cal.shift(-1)))
        head.addWidget(tool_btn("Hôm nay", "Về tháng hiện tại", self.cal.go_today))
        head.addWidget(tool_btn("›", "Tháng sau", lambda: self.cal.shift(1)))
        self.v.addLayout(head)
        self.v.addWidget(self.cal)
        self.detail = sub_label(wrap=True)
        self.detail.hide()
        self.v.addWidget(self.detail)
        self.cal.month_changed.connect(self.update_title)
        self.cal.day_clicked.connect(self.show_day)
        self.update_title()

    def update_title(self):
        _, _, ly, _ = al.solar_to_lunar(15, self.cal.month, self.cal.year)
        self.title.setText(f"Tháng {self.cal.month}/{self.cal.year} · {al.can_chi_nam(ly)}")

    def show_day(self, d):
        if d is None:
            self.detail.hide()
            return
        info = al.day_info(d)
        lines = [f"{info['thu']} {d:%d/%m/%Y} · Âm lịch {info['lunar_day']} {info['ten_thang']} "
                 f"năm {info['nam']} · Ngày {info['ngay']}"]
        lines += ["🎉 " + x for x in info["le"]]
        due = [t["text"] for t in self.app.data["tasks"] if t.get("due") == d.isoformat() and not t["done"]]
        if due:
            lines.append(f"📌 {len(due)} việc: " + "; ".join(due[:4]) + ("…" if len(due) > 4 else ""))
        self.detail.setText("\n".join(lines))
        self.detail.show()


class TaskRow(QWidget):
    def __init__(self, section, task):
        super().__init__()
        self.section = section
        self.tid = task["id"]
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 1, 0, 1)
        h.setSpacing(7)
        cb = QCheckBox()
        cb.setChecked(bool(task["done"]))
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setToolTip("Đánh dấu hoàn thành")
        tid = self.tid
        cb.toggled.connect(lambda v: section.toggle(tid, v))
        lbl = QLabel()
        lbl.setObjectName("taskText")
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        text = html.escape(task["text"])
        if task.get("important"):
            text = "★ " + text
        if task["done"]:
            text = f"<s>{text}</s>"
        lbl.setText(text)
        lbl.setProperty("done", bool(task["done"]))
        lbl.setProperty("important", bool(task.get("important")))
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        h.addWidget(cb, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(lbl, 1)
        txt, state = core.due_label(task.get("due"), section.app.today)
        if txt and not task["done"]:
            d = QLabel(txt)
            d.setObjectName("due")
            d.setProperty("state", state)
            h.addWidget(d, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(tool_btn("✕", "Xóa việc này", lambda: section.delete(tid), name="del"), 0, Qt.AlignmentFlag.AlignTop)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)
        self.setToolTip("Nhấp đúp để sửa · chuột phải để đặt hạn, đánh dấu quan trọng")

    def mouseDoubleClickEvent(self, e):
        tid, sec = self.tid, self.section
        QTimer.singleShot(0, lambda: sec.edit(tid))
        e.accept()

    def show_menu(self, pos):
        sec, tid = self.section, self.tid
        t = sec.find(tid)
        if not t:
            return
        m = QMenu(sec)
        m.addAction(make_action(m, "Sửa nội dung…", later(lambda: sec.edit(tid))))
        m.addAction(make_action(m, "Đặt hạn…", later(lambda: sec.set_due(tid))))
        if t.get("due"):
            m.addAction(make_action(m, "Bỏ hạn", later(lambda: sec.clear_due(tid))))
        m.addAction(make_action(m, "Bỏ đánh dấu quan trọng" if t.get("important") else "Đánh dấu quan trọng ★",
                                later(lambda: sec.toggle_important(tid))))
        m.addSeparator()
        m.addAction(make_action(m, "Xóa", later(lambda: sec.delete(tid))))
        m.exec(self.mapToGlobal(pos))


class TasksSection(Section):
    def __init__(self, app):
        super().__init__(app)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(named_label("section", "VIỆC CẦN LÀM"))
        self.lbl_count = sub_label()
        head.addWidget(self.lbl_count)
        head.addStretch(1)
        head.addWidget(tool_btn("🧹", "Xóa các việc đã hoàn thành", self.clear_done))
        self.v.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.ed = QLineEdit()
        self.ed.setPlaceholderText("Thêm việc mới… (Enter)")
        self.ed.returnPressed.connect(self.add_from_input)
        self.btn_due = tool_btn("📅", "Đặt hạn cho việc mới", self.pick_new_due)
        row.addWidget(self.ed, 1)
        row.addWidget(self.btn_due)
        row.addWidget(tool_btn("＋", "Thêm việc", self.add_from_input))
        self.v.addLayout(row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("listHost")
        self.list_lay = QVBoxLayout(host)
        self.list_lay.setContentsMargins(0, 2, 6, 2)
        self.list_lay.setSpacing(3)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(host)
        self.scroll.viewport().setAutoFillBackground(False)
        host.setAutoFillBackground(False)
        self.scroll.setMinimumHeight(60)
        self.v.addWidget(self.scroll, 1)
        self._new_due = None
        self.rebuild()

    @property
    def tasks(self):
        return self.app.data["tasks"]

    def find(self, tid):
        return next((t for t in self.tasks if t["id"] == tid), None)

    def changed(self):
        self.app.schedule_save()
        self.rebuild()
        self.app.calendar.cal.update()

    def rebuild(self):
        while self.list_lay.count() > 1:
            it = self.list_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        items = sorted(self.tasks, key=core.task_sort_key)
        if not items:
            self.list_lay.insertWidget(0, sub_label("Chưa có việc nào. Gõ vào ô trên rồi nhấn Enter.", wrap=True))
        for i, t in enumerate(items):
            self.list_lay.insertWidget(i, TaskRow(self, t))
        today_s = self.app.today.isoformat()
        open_n = sum(1 for t in self.tasks if not t["done"])
        over = sum(1 for t in self.tasks if not t["done"] and t.get("due") and t["due"] < today_s)
        self.lbl_count.setText(f"· {open_n} việc" + (f" · {over} quá hạn" if over else ""))

    def add_task(self, text, due=None, important=False):
        self.tasks.append({
            "id": uuid.uuid4().hex[:12], "text": text, "done": False,
            "due": due.isoformat() if due else None, "important": important,
            "created": dt.datetime.now().isoformat(timespec="seconds"), "done_at": None,
        })
        self.changed()

    def add_from_input(self):
        text = self.ed.text().strip()
        if not text:
            return
        self.add_task(text, self._new_due)
        self.ed.clear()
        self._new_due = None
        self.update_due_btn()

    def pick_new_due(self):
        act, d = pick_date(self._new_due)
        if act == "set":
            self._new_due = d
        elif act == "clear":
            self._new_due = None
        self.update_due_btn()

    def update_due_btn(self):
        self.btn_due.setText("📅 " + self._new_due.strftime("%d/%m") if self._new_due else "📅")

    def toggle(self, tid, done):
        t = self.find(tid)
        if t:
            t["done"] = bool(done)
            t["done_at"] = dt.datetime.now().isoformat(timespec="seconds") if done else None
            self.changed()

    def delete(self, tid):
        t = self.find(tid)
        if not t:
            return
        if not t["done"]:
            r = QMessageBox.question(None, "Xóa việc", f"Xóa việc chưa hoàn thành này?\n\n{t['text']}")
            if r != QMessageBox.StandardButton.Yes:
                return
        self.tasks.remove(t)
        self.changed()

    def edit(self, tid):
        t = self.find(tid)
        if not t:
            return
        text, ok = QInputDialog.getText(None, "Sửa việc", "Nội dung:", QLineEdit.EchoMode.Normal, t["text"])
        if ok and text.strip():
            t["text"] = text.strip()
            self.changed()

    def set_due(self, tid):
        t = self.find(tid)
        if not t:
            return
        init = dt.date.fromisoformat(t["due"]) if t.get("due") else None
        act, d = pick_date(init)
        if act == "cancel":
            return
        t["due"] = d.isoformat() if d else None
        self.changed()

    def clear_due(self, tid):
        t = self.find(tid)
        if t:
            t["due"] = None
            self.changed()

    def toggle_important(self, tid):
        t = self.find(tid)
        if t:
            t["important"] = not t.get("important")
            self.changed()

    def clear_done(self):
        n = sum(1 for t in self.tasks if t["done"])
        if not n:
            return
        r = QMessageBox.question(None, "Dọn việc đã xong", f"Xóa {n} việc đã hoàn thành?")
        if r == QMessageBox.StandardButton.Yes:
            self.app.data["tasks"] = [t for t in self.tasks if not t["done"]]
            self.changed()


class NotesSection(Section):
    def __init__(self, app):
        super().__init__(app)
        head = QHBoxLayout()
        head.setSpacing(4)
        head.addWidget(named_label("section", "GHI CHÚ"))
        head.addStretch(1)
        head.addWidget(tool_btn("＋", "Thêm ghi chú mới", self.add_note))
        head.addWidget(tool_btn("🗑", "Xóa ghi chú đang mở", lambda: self.delete(self.bar.currentIndex())))
        self.v.addLayout(head)
        self.bar = QTabBar()
        self.bar.setExpanding(False)
        self.bar.setDrawBase(False)
        self.bar.setUsesScrollButtons(True)
        self.bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bar.customContextMenuRequested.connect(self.tab_menu)
        self.bar.tabBarDoubleClicked.connect(self.rename)
        self.bar.setToolTip("Nhấp đúp để đổi tên · chuột phải để xóa")
        self.v.addWidget(self.bar)
        self.ed = QPlainTextEdit()
        self.ed.setPlaceholderText("Viết ghi chú… (tự động lưu)")
        self.ed.setMinimumHeight(70)
        self.ed.textChanged.connect(self.on_text)
        self.v.addWidget(self.ed, 1)
        for n in self.notes:
            self.bar.addTab(n["title"])
        self.bar.currentChanged.connect(self.on_tab)
        self.on_tab(self.bar.currentIndex())

    @property
    def notes(self):
        return self.app.data["notes"]

    def on_tab(self, i):
        if 0 <= i < len(self.notes):
            self.ed.blockSignals(True)
            self.ed.setPlainText(self.notes[i]["text"])
            self.ed.blockSignals(False)

    def on_text(self):
        i = self.bar.currentIndex()
        if 0 <= i < len(self.notes):
            self.notes[i]["text"] = self.ed.toPlainText()
            self.app.schedule_save()

    def add_note(self):
        title = f"Ghi chú {len(self.notes) + 1}"
        self.notes.append({"title": title, "text": ""})
        i = self.bar.addTab(title)
        self.bar.setCurrentIndex(i)
        self.ed.setFocus()
        self.app.schedule_save()

    def rename(self, i):
        if not (0 <= i < len(self.notes)):
            return
        t, ok = QInputDialog.getText(None, "Đổi tên ghi chú", "Tên ghi chú:", QLineEdit.EchoMode.Normal,
                                     self.notes[i]["title"])
        if ok and t.strip():
            self.notes[i]["title"] = t.strip()
            self.bar.setTabText(i, t.strip())
            self.app.schedule_save()

    def delete(self, i):
        if not (0 <= i < len(self.notes)):
            return
        n = self.notes[i]
        if n["text"].strip():
            r = QMessageBox.question(None, "Xóa ghi chú", f"Xóa ghi chú “{n['title']}”?")
            if r != QMessageBox.StandardButton.Yes:
                return
        if len(self.notes) == 1:
            n["text"] = ""
            self.on_tab(0)
        else:
            self.notes.pop(i)
            self.bar.removeTab(i)
            self.on_tab(self.bar.currentIndex())
        self.app.schedule_save()

    def tab_menu(self, pos):
        i = self.bar.tabAt(pos)
        if i < 0:
            return
        m = QMenu(self)
        m.addAction(make_action(m, "Đổi tên…", later(lambda: self.rename(i))))
        m.addAction(make_action(m, "Xóa ghi chú", later(lambda: self.delete(i))))
        m.exec(self.bar.mapToGlobal(pos))


# =============================================================== hộp thoại cài đặt
PRESETS = [
    ("Tối", {"bg_color": "#141a24", "text_color": "#ffffff", "accent_color": "#4fc3f7"}),
    ("Sáng", {"bg_color": "#f4f6fa", "text_color": "#1b2330", "accent_color": "#1976d2"}),
    ("Xanh đêm", {"bg_color": "#0d2137", "text_color": "#e8f1ff", "accent_color": "#ffd166"}),
    ("Trong suốt", {"bg_opacity": 0, "text_color": "#ffffff", "accent_color": "#4fc3f7"}),
]


class SettingsDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowTitle("Cài đặt – Desktop Widget")
        self.setWindowIcon(app.windowIcon())
        self.setMinimumWidth(480)
        self._w0 = dict(app.cfg["weather"])
        self.geo_http = Http()
        self.geo_http.finished.connect(self.on_geo)
        self._geo_query = ""
        self._geo_retry = False
        tabs = QTabWidget()
        tabs.addTab(self.tab_look(), "Giao diện")
        tabs.addTab(self.tab_show(), "Hiển thị")
        tabs.addTab(self.tab_weather(), "Thời tiết")
        tabs.addTab(self.tab_system(), "Hệ thống")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.button(QDialogButtonBox.StandardButton.Close).setText("Đóng")
        bb.rejected.connect(self.reject)
        v = QVBoxLayout(self)
        v.addWidget(tabs)
        v.addWidget(bb)
        self.finished.connect(self.on_finished)

    # ---- giao diện
    def slider(self, lo, hi, val, key, suffix):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(val))
        lb = QLabel(f"{int(val)}{suffix}")
        lb.setMinimumWidth(52)

        def changed(v):
            lb.setText(f"{v}{suffix}")
            self.app.set_cfg(key, v)
        s.valueChanged.connect(changed)
        h.addWidget(s, 1)
        h.addWidget(lb)
        return box, s

    def tab_look(self):
        cfg = self.app.cfg
        w = QWidget()
        f = QFormLayout(w)
        box, self.sl_op = self.slider(0, 100, cfg["bg_opacity"], "bg_opacity", " %")
        f.addRow("Độ đậm của nền:", box)
        hint = QLabel("0 % = nền trong suốt hoàn toàn, chỉ còn chữ.")
        hint.setStyleSheet("color: gray;")
        f.addRow("", hint)
        f.addRow("Bo góc:", self.slider(0, 30, cfg["radius"], "radius", " px")[0])
        sp = QSpinBox()
        sp.setRange(70, 180)
        sp.setSingleStep(5)
        sp.setSuffix(" %")
        sp.setValue(cfg["scale"])
        sp.valueChanged.connect(lambda v: self.app.set_cfg("scale", v))
        f.addRow("Cỡ chữ:", sp)
        self.color_btns = {}
        for key, label in (("bg_color", "Màu nền:"), ("text_color", "Màu chữ:"), ("accent_color", "Màu nhấn:")):
            b = QPushButton()
            b.setFixedWidth(130)
            b.clicked.connect(lambda _=False, k=key: self.pick_color(k))
            self.color_btns[key] = b
            f.addRow(label, b)
        self.refresh_color_btns()
        row = QWidget()
        rh = QHBoxLayout(row)
        rh.setContentsMargins(0, 0, 0, 0)
        for name, preset in PRESETS:
            b = QPushButton(name)
            b.clicked.connect(lambda _=False, p=preset: self.apply_preset(p))
            rh.addWidget(b)
        rh.addStretch(1)
        f.addRow("Mẫu có sẵn:", row)
        cb = QCheckBox("Làm mờ phía sau kiểu kính mờ (thử nghiệm, góc sẽ vuông)")
        cb.setChecked(bool(cfg["blur"]))
        cb.toggled.connect(lambda v: self.app.set_cfg("blur", v))
        f.addRow("", cb)
        return w

    def refresh_color_btns(self):
        for key, b in self.color_btns.items():
            c = QColor(self.app.cfg[key])
            fg = "#000" if lum(c) > 150 else "#fff"
            b.setText(c.name())
            b.setStyleSheet(f"background:{c.name()}; color:{fg}; border:1px solid #888; padding:4px; border-radius:4px;")

    def pick_color(self, key):
        c = QColorDialog.getColor(QColor(self.app.cfg[key]), self, "Chọn màu")
        if c.isValid():
            self.app.set_cfg(key, c.name())
            self.refresh_color_btns()

    def apply_preset(self, preset):
        for k, v in preset.items():
            self.app.set_cfg(k, v)
        if "bg_opacity" in preset:
            self.sl_op.setValue(preset["bg_opacity"])
        elif self.app.cfg["bg_opacity"] < 20:
            self.sl_op.setValue(55)
        self.refresh_color_btns()

    # ---- hiển thị
    def tab_show(self):
        w = QWidget()
        v = QVBoxLayout(w)
        items = [("show_clock", "Đồng hồ và lịch âm dương hôm nay"),
                 ("show_seconds", "    Hiện giây"),
                 ("show_gio_hd", "    Hiện giờ hoàng đạo"),
                 ("show_weather", "Thời tiết"),
                 ("show_calendar", "Lịch tháng (âm – dương)"),
                 ("show_tasks", "Việc cần làm"),
                 ("show_notes", "Ghi chú")]
        for key, text in items:
            cb = QCheckBox(text)
            cb.setChecked(bool(self.app.cfg[key]))
            cb.toggled.connect(lambda val, k=key: self.app.set_cfg(k, val))
            v.addWidget(cb)
        v.addStretch(1)
        return w

    # ---- thời tiết
    def tab_weather(self):
        wcfg = self.app.cfg["weather"]
        w = QWidget()
        v = QVBoxLayout(w)
        f = QFormLayout()
        self.ed_name = QLineEdit(wcfg["name"])
        self.ed_name.textEdited.connect(self.on_name)
        self.sp_lat = QDoubleSpinBox()
        self.sp_lat.setDecimals(4)
        self.sp_lat.setRange(-90, 90)
        self.sp_lat.setValue(float(wcfg["lat"]))
        self.sp_lat.valueChanged.connect(lambda x: self.set_w("lat", float(x)))
        self.sp_lon = QDoubleSpinBox()
        self.sp_lon.setDecimals(4)
        self.sp_lon.setRange(-180, 180)
        self.sp_lon.setValue(float(wcfg["lon"]))
        self.sp_lon.valueChanged.connect(lambda x: self.set_w("lon", float(x)))
        sp_int = QSpinBox()
        sp_int.setRange(10, 240)
        sp_int.setSingleStep(10)
        sp_int.setSuffix(" phút")
        sp_int.setValue(int(wcfg["interval"]))
        sp_int.valueChanged.connect(lambda x: self.set_w("interval", int(x)))
        f.addRow("Tên hiển thị:", self.ed_name)
        f.addRow("Vĩ độ:", self.sp_lat)
        f.addRow("Kinh độ:", self.sp_lon)
        f.addRow("Cập nhật mỗi:", sp_int)
        v.addLayout(f)
        v.addWidget(QLabel("Tìm địa điểm (tên xã/phường, huyện, thành phố…):"))
        row = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("VD: Vinh, Quỳnh Lưu, Hà Nội…")
        self.ed_search.returnPressed.connect(self.do_search)
        b = QPushButton("Tìm")
        b.clicked.connect(lambda _=False: self.do_search())
        row.addWidget(self.ed_search, 1)
        row.addWidget(b)
        v.addLayout(row)
        self.lst = QListWidget()
        self.lst.itemClicked.connect(self.choose)
        v.addWidget(self.lst, 1)
        self.lbl_geo = QLabel("Nguồn dữ liệu: Open-Meteo (miễn phí, không cần tài khoản).")
        self.lbl_geo.setStyleSheet("color: gray;")
        self.lbl_geo.setWordWrap(True)
        v.addWidget(self.lbl_geo)
        return w

    def set_w(self, key, val):
        self.app.cfg["weather"][key] = val
        self.app.schedule_save()

    def on_name(self, text):
        self.set_w("name", text.strip())
        self.app.weather.update_loc()

    def do_search(self):
        q = self.ed_search.text().strip()
        if not q:
            return
        self._geo_query = q
        self._geo_retry = True
        self.lbl_geo.setText("Đang tìm…")
        self.lst.clear()
        self.geo_http.get_json("geo", core.geocode_url(q))

    def on_geo(self, tag, data, err):
        if err:
            self.lbl_geo.setText("Lỗi: " + err)
            return
        results = (data or {}).get("results") or []
        if not results and self._geo_retry:
            self._geo_retry = False
            plain = core.strip_accents(self._geo_query)
            if plain != self._geo_query:
                self.geo_http.get_json("geo", core.geocode_url(plain))
                return
        if not results:
            self.lbl_geo.setText("Không tìm thấy. Thử tên khác (có thể gõ không dấu) hoặc nhập toạ độ trực tiếp.")
            return
        self.lbl_geo.setText(f"{len(results)} kết quả – bấm vào một dòng để chọn.")
        for r in results:
            lat, lon = r.get("latitude"), r.get("longitude")
            if lat is None or lon is None:
                continue
            parts = [r.get("name"), r.get("admin2"), r.get("admin1"), r.get("country")]
            text = ", ".join(p for p in parts if p) + f"   ({lat:.3f}, {lon:.3f})"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, r)
            self.lst.addItem(it)

    def choose(self, it):
        r = it.data(Qt.ItemDataRole.UserRole)
        if not isinstance(r, dict):
            return
        name = ", ".join(p for p in [r.get("name"), r.get("admin1")] if p)
        self.ed_name.setText(name)
        self.set_w("name", name)
        self.sp_lat.setValue(float(r["latitude"]))
        self.sp_lon.setValue(float(r["longitude"]))
        self.app.weather.update_loc()
        self._w0 = dict(self.app.cfg["weather"])
        self.app.fetch_weather(manual=True)
        self.lbl_geo.setText(f"Đã chọn: {name}")

    # ---- hệ thống
    def tab_system(self):
        cfg = self.app.cfg
        w = QWidget()
        f = QFormLayout(w)
        cb_mode = QComboBox()
        modes = [("Dưới cùng – nằm trên màn hình nền như widget", "desktop"),
                 ("Luôn nổi trên các cửa sổ khác", "top"),
                 ("Cửa sổ bình thường", "normal")]
        for text, val in modes:
            cb_mode.addItem(text, val)
        cb_mode.setCurrentIndex(max(0, [m[1] for m in modes].index(cfg["z_mode"])))
        cb_mode.currentIndexChanged.connect(lambda _i: self.app.set_cfg("z_mode", cb_mode.currentData()))
        f.addRow("Vị trí cửa sổ:", cb_mode)
        for key, text in (("pin_desktop", "Không bị ẩn khi bấm Win+D (chế độ dưới cùng)"),
                          ("locked", "Khóa vị trí và kích thước widget")):
            cb = QCheckBox(text)
            cb.setChecked(bool(cfg[key]))
            cb.toggled.connect(lambda val, k=key: self.app.set_cfg(k, val))
            f.addRow("", cb)
        cb_auto = QCheckBox("Khởi động cùng Windows")
        cb_auto.setChecked(self.app.autostart_on())
        cb_auto.toggled.connect(self.app.toggle_autostart)
        f.addRow("", cb_auto)
        path = QLabel(core.data_dir())
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path.setWordWrap(True)
        f.addRow("Dữ liệu lưu tại:", path)
        b = QPushButton("Mở thư mục dữ liệu")
        b.clicked.connect(lambda _=False: self.open_data_dir())
        f.addRow("", b)
        about = QLabel(f"Desktop Widget v{VERSION}\nChuột phải vào widget hoặc biểu tượng ở khay hệ thống để mở menu.")
        about.setStyleSheet("color: gray;")
        f.addRow("", about)
        return w

    def open_data_dir(self):
        if IS_WIN:
            try:
                os.startfile(core.data_dir())
            except Exception:
                pass

    def on_finished(self, _r):
        w = self.app.cfg["weather"]
        if abs(w["lat"] - self._w0["lat"]) > 1e-6 or abs(w["lon"] - self._w0["lon"]) > 1e-6:
            self.app.fetch_weather(manual=True)
        if w["interval"] != self._w0["interval"]:
            self.app.restart_weather_timer()
        self.app.save_all()


# =============================================================== cửa sổ widget chính
THEME_KEYS = {"bg_color", "text_color", "accent_color", "scale"}
REPAINT_KEYS = {"bg_opacity", "radius"}
VIS_KEYS = {"show_clock", "show_seconds", "show_gio_hd", "show_weather", "show_calendar", "show_tasks", "show_notes"}


class DesktopWidget(QWidget):
    def __init__(self, cfg, data, selftest=False):
        super().__init__(None)
        self.cfg = cfg
        self.data = data
        self.selftest = selftest
        self.theme = Theme(cfg)
        self.today = dt.date.today()
        self.native_win = IS_WIN and QGuiApplication.platformName() == "windows"
        self.weather_data = None
        self.tray = None
        self._owner = 0
        self._drag = None
        self._settings = None
        self._geom_ready = False
        self._fetching = False
        self._fetch_loc = None

        if self.cfg.get("x") is None:                 # lần đầu chạy: màn hình thấp thì thu gọn
            avail_h = QGuiApplication.primaryScreen().availableGeometry().height()
            if avail_h < 900 and self.cfg.get("scale", 100) == 100:
                self.cfg["scale"] = 90
                self.cfg["show_gio_hd"] = False

        self.setWindowTitle(core.APP_TITLE)
        self.setWindowFlags(self.window_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(260, 160)
        self.update_icon()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.content = QWidget()
        self.content.setObjectName("content")
        self.content.setAutoFillBackground(False)
        self.scroller = QScrollArea()                 # màn hình thấp: cuộn thay vì bóp méo nội dung
        self.scroller.setObjectName("outerScroll")
        self.scroller.setWidgetResizable(True)
        self.scroller.setFrameShape(QFrame.Shape.NoFrame)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroller.setWidget(self.content)
        self.scroller.viewport().setAutoFillBackground(False)
        outer.addWidget(self.scroller)
        lay = QVBoxLayout(self.content)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(9)
        self.clock = ClockSection(self)
        self.weather = WeatherSection(self)
        self.calendar = CalendarSection(self)
        self.tasks = TasksSection(self)
        self.notes = NotesSection(self)
        lay.addWidget(self.clock)
        lay.addWidget(self.weather)
        lay.addWidget(self.calendar)
        lay.addWidget(self.tasks, 3)
        lay.addWidget(self.notes, 2)
        self.filler = QWidget()
        self.filler.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        lay.addWidget(self.filler, 1)

        self.grip = QSizeGrip(self)
        self.grip.setStyleSheet("QSizeGrip { background: transparent; width: 16px; height: 16px; }")
        self.grip.resize(16, 16)
        self.grip.setToolTip("Kéo để đổi kích thước")

        self.http = Http()
        self.http.finished.connect(self.on_http)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self.save_all)
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(500)
        self._clock_timer.timeout.connect(self.tick)
        self._clock_timer.start()
        self._wtimer = QTimer(self)
        self._wtimer.timeout.connect(self.fetch_weather)
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.setInterval(3 * 60 * 1000)
        self._retry.timeout.connect(self.fetch_weather)
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(15000)
        self._watchdog.timeout.connect(self.watchdog)

        if not selftest:
            self.setup_tray()
            self.restart_weather_timer()
            self._watchdog.start()
        self.apply_theme()
        self.apply_visibility()
        self.clock.refresh_day(self.today)
        self.tick()
        self.restore_geometry()
        self.load_weather_cache()

    # ---------------------------------------------------------- cửa sổ
    def window_flags(self):
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.cfg["z_mode"] == "top":
            f |= Qt.WindowType.WindowStaysOnTopHint
        elif self.cfg["z_mode"] == "desktop":
            f |= Qt.WindowType.WindowStaysOnBottomHint
        return f

    def apply_window_flags(self):
        vis = self.isVisible()
        geo = self.geometry()
        self.setWindowFlags(self.window_flags())
        self.setGeometry(geo)
        if vis:
            self.show()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self.apply_native)

    def apply_native(self):
        if not self.native_win:
            return
        hwnd = int(self.winId())
        if self.cfg["pin_desktop"] and self.cfg["z_mode"] == "desktop":
            pm = win_find_progman()
            if pm:
                win_set_owner(hwnd, pm)
                self._owner = pm
        elif self._owner:
            win_set_owner(hwnd, 0)
            self._owner = 0
        win_set_blur(hwnd, bool(self.cfg["blur"]))

    def watchdog(self):
        # Explorer khởi động lại -> gắn lại vào desktop mới
        if self.native_win and self.isVisible() and self.cfg["pin_desktop"] and self.cfg["z_mode"] == "desktop":
            pm = win_find_progman()
            if pm and pm != self._owner:
                self.apply_native()

    def restore_geometry(self):
        scr = QGuiApplication.primaryScreen().availableGeometry()
        w = max(260, int(self.cfg.get("w") or 340))
        h = max(200, min(int(self.cfg.get("h") or 900), scr.height() - 40))
        x, y = self.cfg.get("x"), self.cfg.get("y")
        ok = False
        if isinstance(x, int) and isinstance(y, int):
            r = QRect(x, y, w, h).adjusted(40, 40, -40, -40)
            ok = any(s.availableGeometry().intersects(r) for s in QGuiApplication.screens())
        if not ok:
            x, y = scr.right() - w - 24, scr.top() + 24
        self.setGeometry(x, y, w, h)
        self._geom_ready = True

    def remember_geometry(self):
        if self._geom_ready:
            self.cfg["x"], self.cfg["y"] = self.x(), self.y()
            self.cfg["w"], self.cfg["h"] = self.width(), self.height()
            self.schedule_save()

    def moveEvent(self, e):
        super().moveEvent(e)
        self.remember_geometry()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.grip.move(self.width() - self.grip.width(), self.height() - self.grip.height())
        self.grip.raise_()
        self.remember_geometry()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self.cfg["bg_color"])
        a = int(round(self.cfg["bg_opacity"] * 255 / 100))
        c.setAlpha(max(a, 1))        # alpha >= 1 để vẫn bấm/kéo được trên nền trong suốt
        r = 0 if self.cfg["blur"] else self.cfg["radius"]
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if a > 12:
            border = QColor(self.theme.text)
            border.setAlphaF(0.10)
            p.setPen(QPen(border, 1))
        else:
            p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(rect, r, r)
        if not self.cfg["locked"]:
            dot = self.theme.sub(0.35)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot)
            W, H = self.width(), self.height()
            for dx, dy in ((6, 6), (10, 6), (6, 10)):
                p.drawEllipse(QPointF(W - dx, H - dy), 1.1, 1.1)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.cfg["locked"]:
            wh = self.windowHandle()
            if self.native_win and wh is not None and wh.startSystemMove():
                e.accept()
                return
            self._drag = e.globalPosition().toPoint() - self.pos()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        self.populate_menu(m)
        m.exec(e.globalPos())

    # ---------------------------------------------------------- khay hệ thống & menu
    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(core.APP_TITLE)
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(self.fill_tray_menu)
        self.fill_tray_menu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()

    def fill_tray_menu(self):
        self.tray_menu.clear()
        self.populate_menu(self.tray_menu)

    def populate_menu(self, m):
        m.addAction(make_action(m, "Ẩn widget" if self.isVisible() else "Hiện widget", self.toggle_visible))
        m.addAction(make_action(m, "Cập nhật thời tiết", lambda: self.fetch_weather(manual=True)))
        m.addSeparator()
        m.addAction(make_action(m, "Khóa vị trí", lambda v: self.set_cfg("locked", v), True, self.cfg["locked"]))
        if IS_WIN:
            m.addAction(make_action(m, "Khởi động cùng Windows", self.toggle_autostart, True, self.autostart_on()))
        m.addAction(make_action(m, "Cài đặt…", self.open_settings))
        m.addSeparator()
        m.addAction(make_action(m, "Thoát", self.quit_app))

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

    def update_icon(self):
        icon = make_icon(dt.date.today().day, self.cfg["accent_color"])
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        if self.tray is not None:
            self.tray.setIcon(icon)

    def open_settings(self):
        if self._settings is None:
            self._settings = SettingsDialog(self)
            self._settings.finished.connect(self._settings_closed)
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()
        return self._settings

    def _settings_closed(self, _r):
        # bỏ tham chiếu sau khi tín hiệu kết thúc hẳn (tránh xóa hộp thoại giữa chừng)
        QTimer.singleShot(0, lambda: setattr(self, "_settings", None))

    def quit_app(self):
        self.save_all()
        if self.tray is not None:
            self.tray.hide()
        QApplication.instance().quit()

    # ---------------------------------------------------------- cấu hình
    def set_cfg(self, key, value):
        if self.cfg.get(key) == value:
            return
        self.cfg[key] = value
        if key in THEME_KEYS:
            self.apply_theme()
        if key in REPAINT_KEYS:
            self.update()
        if key in VIS_KEYS:
            self.apply_visibility()
            self.tick()
        if key == "z_mode":
            self.apply_window_flags()
        if key in ("pin_desktop", "blur"):
            self.apply_native()
            self.update()
        if key == "locked":
            self.grip.setVisible(not value)
            self.update()
        self.schedule_save()

    def apply_theme(self):
        self.scroller.setStyleSheet(build_outer_qss(self.theme))
        self.content.setStyleSheet(build_qss(self.theme))
        self.calendar.cal.update_metrics()
        self.update_icon()
        self.update()

    def apply_visibility(self):
        sections = [("show_clock", self.clock), ("show_weather", self.weather), ("show_calendar", self.calendar),
                    ("show_tasks", self.tasks), ("show_notes", self.notes)]
        first = True
        for key, sec in sections:
            on = bool(self.cfg.get(key, True))
            sec.setVisible(on)
            if on:
                sec.sep.setVisible(not first)
                first = False
        self.clock.lbl_gio.setVisible(bool(self.cfg["show_gio_hd"]))
        self.clock.lbl_sec.setVisible(bool(self.cfg["show_seconds"]))
        self.filler.setVisible(not (self.cfg["show_tasks"] or self.cfg["show_notes"]))
        self.grip.setVisible(not self.cfg["locked"])

    def schedule_save(self):
        self._save_timer.start()

    def save_all(self):
        try:
            core.save_json(core.path_of("config.json"), self.cfg)
            core.save_json(core.path_of("data.json"), self.data)
        except Exception:
            log_error(traceback.format_exc())

    def autostart_on(self):
        return core.autostart_value() is not None

    def toggle_autostart(self, on):
        if not core.set_autostart(bool(on), SCRIPT) and IS_WIN:
            QMessageBox.warning(None, core.APP_TITLE, "Không ghi được cài đặt khởi động cùng Windows.")

    def startup_autostart(self):
        if not IS_WIN:
            return
        if self.cfg.get("first_run", True):
            core.set_autostart(True, SCRIPT)
            self.cfg["first_run"] = False
            self.schedule_save()
            if self.tray is not None:
                self.tray.showMessage(core.APP_TITLE,
                                      "Widget đã chạy và sẽ tự khởi động cùng Windows.\n"
                                      "Chuột phải vào widget hoặc biểu tượng này để mở cài đặt.",
                                      QSystemTrayIcon.MessageIcon.Information, 7000)
        else:
            cur = core.autostart_value()
            if cur is not None and cur != core.autostart_command(SCRIPT):
                core.set_autostart(True, SCRIPT)     # app đã chuyển chỗ -> cập nhật đường dẫn

    # ---------------------------------------------------------- đồng hồ & ngày mới
    def tick(self):
        now = dt.datetime.now()
        self.clock.tick(now)
        if now.date() != self.today:
            self.today = now.date()
            self.on_new_day()

    def on_new_day(self):
        self.clock.refresh_day(self.today)
        self.calendar.cal.go_today()
        self.tasks.rebuild()
        self.update_icon()
        if self.weather_data:
            self.weather.show_weather(self.weather_data)

    def due_dates(self):
        return {t["due"] for t in self.data["tasks"] if t.get("due") and not t["done"]}

    def day_tooltip(self, d):
        info = al.day_info(d)
        e = html.escape
        lines = [f"<b>{e(info['thu'])}, {d:%d/%m/%Y}</b>",
                 e(f"Âm lịch: {info['lunar_day']} {info['ten_thang']} năm {info['nam']}"),
                 e(f"Ngày {info['ngay']} · Tháng {info['thang']}"),
                 e(f"Tiết {info['tiet_khi']}")]
        lines += ["🎉 " + e(x) for x in info["le"]]
        due = [t for t in self.data["tasks"] if t.get("due") == d.isoformat() and not t["done"]]
        if due:
            lines.append(f"📌 {len(due)} việc đến hạn:")
            lines += ["&nbsp;&nbsp;• " + e(t["text"]) for t in due[:6]]
        return "<br>".join(lines)

    # ---------------------------------------------------------- thời tiết
    def restart_weather_timer(self):
        self._wtimer.start(int(self.cfg["weather"]["interval"]) * 60 * 1000)

    def load_weather_cache(self):
        c = core.load_json(core.path_of("weather.json"), {})
        w = self.cfg["weather"]
        try:
            same = abs(c.get("lat", 999) - w["lat"]) < 1e-4 and abs(c.get("lon", 999) - w["lon"]) < 1e-4
        except Exception:
            same = False
        if isinstance(c, dict) and c.get("days") and same:
            self.weather_data = c
            self.weather.show_weather(c)
            try:
                age = (dt.datetime.now() - dt.datetime.fromisoformat(c["fetched"])).total_seconds() / 60
            except Exception:
                age = 1e9
            if age < w["interval"] or self.selftest:
                return
        if not self.selftest:
            QTimer.singleShot(1500, self.fetch_weather)

    def fetch_weather(self, manual=False):
        if self._fetching:
            return
        w = self.cfg["weather"]
        self._fetching = True
        self._fetch_loc = (w["lat"], w["lon"])
        self.weather.set_loading(True)
        self.http.get_json("weather", core.weather_url(w["lat"], w["lon"]))

    def on_http(self, tag, data, err):
        if tag != "weather":
            return
        self._fetching = False
        self.weather.set_loading(False)
        w = self.cfg["weather"]
        if self._fetch_loc != (w["lat"], w["lon"]):      # đã đổi địa điểm trong lúc tải
            QTimer.singleShot(0, self.fetch_weather)
            return
        if err:
            self.weather.show_error(err)
            self._retry.start()
            return
        try:
            parsed = core.parse_weather(data)
        except Exception as ex:
            self.weather.show_error(str(ex))
            self._retry.start()
            return
        self.apply_weather(parsed)

    def apply_weather(self, parsed):
        w = self.cfg["weather"]
        parsed.update(fetched=dt.datetime.now().isoformat(timespec="seconds"),
                      lat=w["lat"], lon=w["lon"], name=w["name"])
        self.weather_data = parsed
        self.weather.show_weather(parsed)
        try:
            core.save_json(core.path_of("weather.json"), parsed)
        except Exception:
            pass


# =============================================================== "cài đặt" bản .exe vào máy
def install_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", core.APP_NAME)


def create_start_menu_shortcut(target):
    try:
        programs = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
        lnk = os.path.join(programs, "Desktop Widget.lnk")

        def q(s):
            return s.replace("'", "''")
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(lnk)}');"
              f"$s.TargetPath='{q(target)}';$s.WorkingDirectory='{q(os.path.dirname(target))}';"
              f"$s.IconLocation='{q(target)},0';$s.Description='Desktop Widget';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       creationflags=0x08000000, timeout=30)          # CREATE_NO_WINDOW: không hiện CMD
    except Exception:
        log_error(traceback.format_exc())


def maybe_install(cfg):
    """Bản .exe chạy từ chỗ khác (Downloads, USB…) -> đề nghị cài vào máy. True = đã chuyển sang bản cài."""
    if not (FROZEN and IS_WIN) or not cfg.get("ask_install", True):
        return False
    target_dir = install_dir()
    target = os.path.join(target_dir, os.path.basename(sys.executable))
    if os.path.normcase(os.path.abspath(sys.executable)) == os.path.normcase(os.path.abspath(target)):
        return False
    box = QMessageBox()
    box.setWindowTitle("Cài đặt Desktop Widget")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("Cài Desktop Widget vào máy này?")
    box.setInformativeText("Ứng dụng sẽ được chép vào thư mục chương trình của bạn, có lối tắt trong Start Menu "
                           "và tự chạy mỗi khi bật máy. Không cần quyền quản trị.\n\n"
                           "Chọn “Chạy luôn” nếu chỉ muốn dùng tạm từ vị trí hiện tại.")
    b_install = box.addButton("Cài đặt", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Chạy luôn", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(b_install)
    box.exec()
    if box.buttonRole(box.clickedButton()) != QMessageBox.ButtonRole.AcceptRole:
        cfg["ask_install"] = False
        try:
            core.save_json(core.path_of("config.json"), cfg)
        except Exception:
            pass
        return False
    try:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(sys.executable, target)
    except PermissionError:
        QMessageBox.warning(None, core.APP_TITLE,
                            "Bản Desktop Widget đã cài đang chạy nên không ghi đè được.\n"
                            "Hãy thoát nó (chuột phải biểu tượng ở khay hệ thống → Thoát) rồi mở lại file này để cập nhật.")
        return True
    except Exception as ex:
        QMessageBox.warning(None, core.APP_TITLE, f"Không cài được: {ex}\nỨng dụng sẽ chạy từ vị trí hiện tại.")
        return False
    create_start_menu_shortcut(target)
    try:
        subprocess.Popen([target], close_fds=True, cwd=target_dir, creationflags=0x00000008)   # DETACHED_PROCESS
    except Exception as ex:
        QMessageBox.warning(None, core.APP_TITLE, f"Đã chép nhưng không khởi chạy được: {ex}")
        return False
    return True


# =============================================================== tự kiểm tra (CI)
def sample_weather():
    today = dt.date.today()
    days = [(today + dt.timedelta(days=i)).isoformat() for i in range(7)]
    return {
        "current": {"time": f"{today}T14:00", "temperature_2m": 27.4, "relative_humidity_2m": 78,
                    "apparent_temperature": 29.8, "is_day": 1, "weather_code": 2, "wind_speed_10m": 11.6},
        "daily": {"time": days, "weather_code": [2, 61, 80, 3, 1, 95, 0],
                  "temperature_2m_max": [30.1, 28.0, 27.2, 29.5, 31.0, 30.2, 32.1],
                  "temperature_2m_min": [22.3, 22.0, 21.5, 21.9, 23.0, 24.1, 23.3],
                  "precipitation_probability_max": [10, 80, 65, 20, None, 90, 0],
                  "sunrise": [f"{d}T05:58" for d in days], "sunset": [f"{d}T17:15" for d in days]},
    }


def run_selftest(app, w, out):
    os.makedirs(out, exist_ok=True)
    try:
        today = dt.date.today()
        w.tasks.add_task("Hoàn thiện dự toán phát sinh", today, important=True)
        w.tasks.add_task("Gửi hồ sơ thẩm tra", today + dt.timedelta(days=3))
        w.tasks.add_task("Họp giao ban tuần", today - dt.timedelta(days=1))
        w.tasks.add_task("Kiểm tra bản vẽ biện pháp")
        w.tasks.toggle(w.data["tasks"][-1]["id"], True)
        w.tasks.toggle_important(w.data["tasks"][1]["id"])
        w.notes.ed.setPlainText("Gọi nhà cung cấp thép\nNhắc kế toán thanh toán đợt 2")
        w.notes.add_note()
        w.notes.ed.setPlainText("Ghi chú thứ hai")
        w.notes.bar.setCurrentIndex(0)
        w.apply_weather(core.parse_weather(sample_weather()))
        for _ in range(20):
            app.processEvents()
        w.grab().save(os.path.join(out, "widget-dark.png"))
        w.content.grab().save(os.path.join(out, "widget-dark-full.png"))
        with open(os.path.join(out, "layout.txt"), "w", encoding="utf-8") as f:
            f.write(f"window {w.width()}x{w.height()} | content {w.content.width()}x{w.content.height()} | "
                    f"content min {w.content.minimumSizeHint().height()} | scale {w.cfg['scale']} | "
                    f"screen {QGuiApplication.primaryScreen().availableGeometry().height()}\n")
        cal = w.calendar.cal
        cal.shift(1)
        cal.shift(-14)
        cal.go_today()
        for rect, d in cal._cells:
            w.day_tooltip(d)
        w.calendar.show_day(today)
        w.weather.show_error("thử thông báo lỗi")
        w.apply_weather(core.parse_weather(sample_weather()))
        for k, v in (("bg_color", "#f4f6fa"), ("text_color", "#1b2330"), ("accent_color", "#1976d2"),
                     ("bg_opacity", 80), ("scale", 115), ("show_seconds", True)):
            w.set_cfg(k, v)
        for _ in range(20):
            app.processEvents()
        w.grab().save(os.path.join(out, "widget-light.png"))
        w.set_cfg("bg_opacity", 0)
        w.set_cfg("text_color", "#ffffff")
        for key in ("show_weather", "show_calendar", "show_tasks", "show_notes", "show_clock"):
            w.set_cfg(key, False)
            app.processEvents()
            w.set_cfg(key, True)
        w.set_cfg("z_mode", "top")
        app.processEvents()
        w.set_cfg("z_mode", "normal")
        app.processEvents()
        w.set_cfg("z_mode", "desktop")
        w.set_cfg("blur", True)
        w.set_cfg("blur", False)
        w.set_cfg("locked", True)
        w.set_cfg("locked", False)
        w.on_new_day()
        dlg = w.open_settings()
        for _ in range(10):
            app.processEvents()
        dlg.grab().save(os.path.join(out, "settings.png"))
        dlg.close()
        app.processEvents()
        w.save_all()
        d2 = core.normalize_data(core.load_json(core.path_of("data.json"), {}))
        assert len(d2["tasks"]) == 4, "lưu việc cần làm"
        assert len(d2["notes"]) == 2, "lưu ghi chú"
        assert al.solar_to_lunar(17, 2, 2026) == (1, 1, 2026, 0), "lịch âm"
    except Exception:
        ERRORS.append(traceback.format_exc())
    for _ in range(5):
        app.processEvents()
    with open(os.path.join(out, "result.txt"), "w", encoding="utf-8") as f:
        f.write("OK\n" if not ERRORS else "FAIL\n\n" + "\n".join(ERRORS))
    app.exit(1 if ERRORS else 0)


# =============================================================== main
def main():
    args = sys.argv[1:]
    selftest_out = None
    if "--selftest" in args:
        i = args.index("--selftest")
        selftest_out = os.path.abspath(args[i + 1] if i + 1 < len(args) else "selftest-output")
        os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dw-test-")
    if IS_WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TanPhong.DesktopWidget")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(core.APP_NAME)
    app.setApplicationDisplayName(core.APP_TITLE)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet("QToolTip { color: #1b2330; background: #fffdf3; border: 1px solid #c9c2a6; padding: 4px; }")

    def hook(t, v, tb):
        txt = "".join(traceback.format_exception(t, v, tb))
        log_error(txt)
        if selftest_out:
            ERRORS.append(txt)
            if sys.__stderr__:
                print(txt, file=sys.__stderr__)
    sys.excepthook = hook

    cfg = core.merge_config(core.load_json(core.path_of("config.json"), {}))
    cfg.setdefault("ask_install", True)
    lock = None
    if not selftest_out:
        if maybe_install(cfg):
            return 0
        lock = QLockFile(core.path_of("app.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(300):
            QMessageBox.information(None, core.APP_TITLE,
                                    "Desktop Widget đang chạy rồi.\n"
                                    "Xem biểu tượng lịch ở khay hệ thống (góc phải thanh tác vụ).")
            return 0
        core.backup_data_file()
    data = core.normalize_data(core.load_json(core.path_of("data.json"), {}))

    w = DesktopWidget(cfg, data, selftest=bool(selftest_out))
    w.show()
    if not selftest_out:
        w.startup_autostart()
    app.aboutToQuit.connect(w.save_all)
    if selftest_out:
        QTimer.singleShot(400, lambda: run_selftest(app, w, selftest_out))
    rc = app.exec()
    if lock is not None:
        lock.unlock()
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        txt = traceback.format_exc()
        log_error(txt)
        try:
            QMessageBox.critical(None, core.APP_TITLE, "Desktop Widget gặp lỗi khi khởi động:\n\n" + txt[-1500:])
        except Exception:
            pass
        sys.exit(1)
