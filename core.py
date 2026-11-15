# -*- coding: utf-8 -*-
"""
Phần lõi không phụ thuộc giao diện: cấu hình, lưu dữ liệu, thời tiết, tự khởi động.
"""
import os
import sys
import json
import copy
import shutil
import unicodedata
import urllib.parse
import datetime as dt

from amlich_vn import THU_NGAN

APP_NAME = "DesktopWidget"
APP_TITLE = "Desktop Widget"
IS_WIN = sys.platform.startswith("win")

Z_MODES = ("desktop", "top", "normal")

DEFAULT_CONFIG = {
    "x": None, "y": None, "w": 340, "h": 900,
    "bg_color": "#141a24",
    "bg_opacity": 55,          # % độ đậm của nền: 0 = trong suốt hoàn toàn
    "text_color": "#ffffff",
    "accent_color": "#4fc3f7",
    "radius": 16,
    "scale": 100,              # % cỡ chữ
    "blur": False,             # làm mờ phía sau (Windows 10/11, thử nghiệm)
    "show_clock": True,
    "show_seconds": False,
    "show_gio_hd": True,
    "show_weather": True,
    "show_calendar": True,
    "show_tasks": True,
    "show_notes": True,
    "z_mode": "desktop",       # desktop | top | normal
    "pin_desktop": True,       # không bị ẩn khi bấm Win+D
    "locked": False,
    "weather": {"name": "Quỳnh Lưu, Nghệ An", "lat": 19.15, "lon": 105.63, "interval": 30},
    "first_run": True,
}

DEFAULT_DATA = {
    "version": 1,
    "tasks": [],
    "notes": [{"title": "Ghi chú", "text": ""}],
}


# ----------------------------------------------------------------- tệp dữ liệu
def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def path_of(name):
    return os.path.join(data_dir(), name)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return copy.deepcopy(default)
    except Exception:
        # Tệp hỏng: giữ lại bản hỏng để khôi phục thủ công, không ghi đè
        try:
            shutil.copy2(path, path + ".hong-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
        except Exception:
            pass
        return copy.deepcopy(default)


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def backup_data_file():
    """Sao lưu data.json mỗi lần khởi động (giữ 1 bản)."""
    src = path_of("data.json")
    if os.path.exists(src):
        try:
            shutil.copy2(src, path_of("data.backup.json"))
        except Exception:
            pass


def merge_config(loaded):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(loaded, dict):
        return cfg
    for k, v in loaded.items():
        if k == "weather" and isinstance(v, dict):
            cfg["weather"].update({kk: vv for kk, vv in v.items() if kk in cfg["weather"]})
        elif k in cfg:
            cfg[k] = v
    if cfg["z_mode"] not in Z_MODES:
        cfg["z_mode"] = "desktop"
    try:
        cfg["bg_opacity"] = max(0, min(100, int(cfg["bg_opacity"])))
        cfg["scale"] = max(70, min(180, int(cfg["scale"])))
        cfg["radius"] = max(0, min(40, int(cfg["radius"])))
        cfg["weather"]["lat"] = float(cfg["weather"]["lat"])
        cfg["weather"]["lon"] = float(cfg["weather"]["lon"])
        cfg["weather"]["interval"] = max(10, min(240, int(cfg["weather"]["interval"])))
    except (TypeError, ValueError):
        pass
    return cfg


def normalize_data(data):
    if not isinstance(data, dict):
        data = {}
    out = copy.deepcopy(DEFAULT_DATA)
    out.update({k: v for k, v in data.items() if k in out})
    tasks = []
    for i, t in enumerate(out.get("tasks") or []):
        if not isinstance(t, dict) or not str(t.get("text", "")).strip():
            continue
        tasks.append({
            "id": str(t.get("id") or f"t{i}-{dt.datetime.now().timestamp()}"),
            "text": str(t["text"]),
            "done": bool(t.get("done", False)),
            "due": t.get("due") or None,
            "important": bool(t.get("important", False)),
            "created": t.get("created") or dt.datetime.now().isoformat(timespec="seconds"),
            "done_at": t.get("done_at"),
        })
    out["tasks"] = tasks
    notes = [n for n in (out.get("notes") or []) if isinstance(n, dict)]
    notes = [{"title": str(n.get("title") or "Ghi chú"), "text": str(n.get("text") or "")} for n in notes]
    out["notes"] = notes or copy.deepcopy(DEFAULT_DATA["notes"])
    return out


# ----------------------------------------------------------------- việc cần làm
def task_sort_key(t):
    return (bool(t.get("done")), not t.get("important"), t.get("due") or "9999-12-31", t.get("created", ""))


def due_label(due, today):
    """Trả về (chuỗi hiển thị, trạng thái) với trạng thái: over | today | soon | normal | ''."""
    if not due:
        return "", ""
    try:
        d = dt.date.fromisoformat(due)
    except ValueError:
        return "", ""
    diff = (d - today).days
    if diff < 0:
        return f"Quá hạn {d:%d/%m}", "over"
    if diff == 0:
        return "Hôm nay", "today"
    if diff == 1:
        return "Ngày mai", "soon"
    return f"{THU_NGAN[d.weekday()]} {d:%d/%m}", "normal"


# ----------------------------------------------------------------- thời tiết (Open-Meteo, miễn phí, không cần key)
WMO = {
    0: ("Trời quang", "☀️", "🌙"),
    1: ("Ít mây", "🌤️", "🌙"),
    2: ("Có mây", "⛅", "☁️"),
    3: ("Nhiều mây", "☁️", "☁️"),
    45: ("Sương mù", "🌫️", "🌫️"),
    48: ("Sương mù giá", "🌫️", "🌫️"),
    51: ("Mưa phùn nhẹ", "🌦️", "🌧️"),
    53: ("Mưa phùn", "🌦️", "🌧️"),
    55: ("Mưa phùn dày", "🌧️", "🌧️"),
    56: ("Mưa phùn lạnh", "🌧️", "🌧️"),
    57: ("Mưa phùn lạnh", "🌧️", "🌧️"),
    61: ("Mưa nhỏ", "🌦️", "🌧️"),
    63: ("Mưa vừa", "🌧️", "🌧️"),
    65: ("Mưa to", "🌧️", "🌧️"),
    66: ("Mưa lạnh", "🌧️", "🌧️"),
    67: ("Mưa lạnh to", "🌧️", "🌧️"),
    71: ("Tuyết nhẹ", "🌨️", "🌨️"),
    73: ("Tuyết", "🌨️", "🌨️"),
    75: ("Tuyết dày", "❄️", "❄️"),
    77: ("Hạt tuyết", "🌨️", "🌨️"),
    80: ("Mưa rào nhẹ", "🌦️", "🌧️"),
    81: ("Mưa rào", "🌧️", "🌧️"),
    82: ("Mưa rào rất to", "⛈️", "⛈️"),
    85: ("Mưa tuyết", "🌨️", "🌨️"),
    86: ("Mưa tuyết dày", "🌨️", "🌨️"),
    95: ("Dông", "⛈️", "⛈️"),
    96: ("Dông, mưa đá nhẹ", "⛈️", "⛈️"),
    99: ("Dông, mưa đá", "⛈️", "⛈️"),
}


def wmo(code, is_day=1):
    desc, day_icon, night_icon = WMO.get(code, ("Không rõ", "🌡️", "🌡️"))
    return desc, (day_icon if is_day else night_icon)


def weather_url(lat, lon):
    q = {
        "latitude": f"{float(lat):.4f}",
        "longitude": f"{float(lon):.4f}",
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        "timezone": "auto",
        "forecast_days": "7",
    }
    return "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)


def geocode_url(name):
    q = {"name": name, "count": "8", "language": "vi", "format": "json"}
    return "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(q)


def parse_weather(data):
    if not isinstance(data, dict) or not isinstance(data.get("current"), dict):
        raise ValueError("Dữ liệu thời tiết không hợp lệ")
    cur = data["current"]
    daily = data.get("daily") or {}
    times = daily.get("time") or []

    def col(name, i):
        arr = daily.get(name) or []
        return arr[i] if i < len(arr) else None

    days = []
    for i, t in enumerate(times):
        days.append({
            "date": t,
            "code": col("weather_code", i),
            "tmax": col("temperature_2m_max", i),
            "tmin": col("temperature_2m_min", i),
            "rain": col("precipitation_probability_max", i),
            "sunrise": col("sunrise", i),
            "sunset": col("sunset", i),
        })
    return {
        "temp": cur.get("temperature_2m"),
        "feels": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "wind": cur.get("wind_speed_10m"),
        "code": cur.get("weather_code"),
        "is_day": cur.get("is_day", 1),
        "time": cur.get("time"),
        "days": days,
    }


def fmt_temp(v):
    return "--" if v is None else f"{round(v)}°"


def hhmm(iso):
    """'2026-11-15T05:58' -> '05:58'."""
    if not iso or "T" not in str(iso):
        return "--:--"
    return str(iso).split("T", 1)[1][:5]


def strip_accents(s):
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# ----------------------------------------------------------------- tự khởi động cùng Windows
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command(script_path):
    if getattr(sys, "frozen", False):            # bản .exe đóng gói bằng PyInstaller
        return f'"{sys.executable}"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{os.path.abspath(script_path)}"'


def autostart_value():
    if not IS_WIN:
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, APP_NAME)[0]
    except OSError:
        return None


def set_autostart(on, script_path):
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command(script_path))
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
