# -*- coding: utf-8 -*-
"""Kiểm thử phần lõi (không cần giao diện): lịch âm, cấu hình, việc cần làm, thời tiết."""
import os, sys, json, tempfile, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dw-core-")
import amlich_vn as al
import core

fails = []
def check(label, got, exp):
    ok = got == exp
    print(("OK  " if ok else "FAIL"), label, "" if ok else f"-> {got!r} (cần {exp!r})")
    if not ok: fails.append(label)

# Lịch âm
for (d, m, y), ly in [((21, 1, 1985), 1985), ((17, 2, 2007), 2007), ((10, 2, 2024), 2024),
                      ((29, 1, 2025), 2025), ((17, 2, 2026), 2026), ((6, 2, 2027), 2027)]:
    check(f"Tết {ly}", al.solar_to_lunar(d, m, y), (1, 1, ly, 0))
check("tháng 6 nhuận 2025", al.solar_to_lunar(25, 7, 2025), (1, 6, 2025, 1))
check("tháng 2 nhuận 2023", al.solar_to_lunar(22, 3, 2023), (1, 2, 2023, 1))
bad, d = 0, dt.date(1990, 1, 1)
while d < dt.date(2051, 1, 1):
    ld, lm, ly, lp = al.solar_to_lunar(d.day, d.month, d.year)
    if al.lunar_to_solar(ld, lm, ly, lp) != (d.day, d.month, d.year): bad += 1
    d += dt.timedelta(days=1)
check("khứ hồi âm-dương 1990-2050", bad, 0)
check("Giao thừa 2027", al.ngay_le(5, 2, 2027), ["Giao thừa"])
check("Trung thu 2026", al.ngay_le(25, 9, 2026), ["Tết Trung Thu"])

# Cấu hình
cfg = core.merge_config({"bg_opacity": 250, "z_mode": "abc", "weather": {"lat": "21.0", "foo": 1}, "unknown": 1})
check("merge: giới hạn opacity", cfg["bg_opacity"], 100)
check("merge: z_mode sai -> desktop", cfg["z_mode"], "desktop")
check("merge: lat chuỗi -> số", cfg["weather"]["lat"], 21.0)
check("merge: bỏ khóa lạ", "unknown" in cfg or "foo" in cfg["weather"], False)
check("merge: dữ liệu hỏng", core.merge_config("xyz")["w"], 340)

data = core.normalize_data({"tasks": [{"text": "A"}, {"text": "  "}, "rác", {"text": "B", "done": 1, "due": "2026-11-20"}],
                            "notes": []})
check("normalize: lọc việc rỗng", [t["text"] for t in data["tasks"]], ["A", "B"])
check("normalize: ghi chú mặc định", len(data["notes"]), 1)

# Lưu / đọc + tệp hỏng
p = core.path_of("data.json")
core.save_json(p, data)
check("save/load", core.normalize_data(core.load_json(p, {}))["tasks"][1]["due"], "2026-11-20")
with open(p, "w", encoding="utf-8") as f: f.write("{hỏng")
check("tệp hỏng -> mặc định", core.load_json(p, {"x": 1}), {"x": 1})
check("tệp hỏng được giữ lại", any(n.startswith("data.json.hong-") for n in os.listdir(core.data_dir())), True)

# Hạn công việc
today = dt.date(2026, 11, 15)
check("hạn quá", core.due_label("2026-11-14", today), ("Quá hạn 14/11", "over"))
check("hạn hôm nay", core.due_label("2026-11-15", today), ("Hôm nay", "today"))
check("hạn mai", core.due_label("2026-11-16", today), ("Ngày mai", "soon"))
check("hạn xa", core.due_label("2026-11-20", today), ("T6 20/11", "normal"))
tasks = [{"done": True, "created": "1"}, {"done": False, "due": "2026-12-01", "created": "2"},
         {"done": False, "important": True, "created": "3"}, {"done": False, "due": "2026-11-20", "created": "4"}]
check("sắp xếp việc", [t["created"] for t in sorted(tasks, key=core.task_sort_key)], ["3", "4", "2", "1"])

# Thời tiết
url = core.weather_url(19.15, 105.63)
check("url thời tiết", url.startswith("https://api.open-meteo.com/v1/forecast?latitude=19.1500&longitude=105.6300"), True)
check("url có timezone", "timezone=auto" in url and "forecast_days=7" in url, True)
check("url geocode có dấu", "name=Qu%E1%BB%B3nh+L%C6%B0u" in core.geocode_url("Quỳnh Lưu"), True)
check("bỏ dấu", core.strip_accents("Quỳnh Lưu, Đức Hòa"), "Quynh Luu, Duc Hoa")
sample = {"current": {"time": "2026-11-15T14:00", "temperature_2m": 27.4, "relative_humidity_2m": 78,
                      "apparent_temperature": 29.8, "is_day": 0, "weather_code": 61, "wind_speed_10m": 11.6},
          "daily": {"time": ["2026-11-15", "2026-11-16"], "weather_code": [61, 3],
                    "temperature_2m_max": [30.1, 28.0], "temperature_2m_min": [22.3, 22.0],
                    "precipitation_probability_max": [80, None],
                    "sunrise": ["2026-11-15T05:58", "2026-11-16T05:59"], "sunset": ["2026-11-15T17:15", None]}}
w = core.parse_weather(sample)
check("parse: nhiệt độ", core.fmt_temp(w["temp"]), "27°")
check("parse: mô tả + ban đêm", core.wmo(w["code"], w["is_day"]), ("Mưa nhỏ", "🌧️"))
check("parse: ngày 2 thiếu mưa", w["days"][1]["rain"], None)
check("parse: giờ mặt trời", (core.hhmm(w["days"][0]["sunrise"]), core.hhmm(w["days"][1]["sunset"])), ("05:58", "--:--"))
check("mã thời tiết lạ", core.wmo(1234)[0], "Không rõ")
try:
    core.parse_weather({"error": True, "reason": "x"}); check("parse lỗi", "không báo lỗi", "ValueError")
except ValueError:
    check("parse lỗi -> ValueError", True, True)

print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{len(fails)} LỖI: {fails}")
sys.exit(1 if fails else 0)
