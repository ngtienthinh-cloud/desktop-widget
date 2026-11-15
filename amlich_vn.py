# -*- coding: utf-8 -*-
"""
Lịch âm Việt Nam (múi giờ GMT+7).
Thuật toán thiên văn của Hồ Ngọc Đức (https://www.informatik.uni-leipzig.de/~duc/amlich/).

Hàm chính:
    solar_to_lunar(d, m, y)          -> (ngày_âm, tháng_âm, năm_âm, nhuận)
    lunar_to_solar(ld, lm, ly, leap) -> (ngày, tháng, năm) dương lịch
    day_info(date)                   -> dict đầy đủ thông tin một ngày
"""
import math
import datetime as _dt

TZ = 7.0

CAN = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
CHI = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]
TIET_KHI = ["Xuân phân", "Thanh minh", "Cốc vũ", "Lập hạ", "Tiểu mãn", "Mang chủng",
            "Hạ chí", "Tiểu thử", "Đại thử", "Lập thu", "Xử thử", "Bạch lộ",
            "Thu phân", "Hàn lộ", "Sương giáng", "Lập đông", "Tiểu tuyết", "Đại tuyết",
            "Đông chí", "Tiểu hàn", "Đại hàn", "Lập xuân", "Vũ thủy", "Kinh trập"]
THU = ["Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật"]
THU_NGAN = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
TEN_THANG_AM = ["Giêng", "Hai", "Ba", "Tư", "Năm", "Sáu", "Bảy", "Tám", "Chín", "Mười", "Một", "Chạp"]

# Bảng giờ hoàng đạo theo chi của ngày (Tý/Ngọ, Sửu/Mùi, ...)
_GIO_HD = ["110100101100", "001101001011", "110011010010",
           "101100110100", "001011001101", "010010110011"]

NGAY_LE_DUONG = {
    (1, 1): "Tết Dương lịch",
    (3, 2): "Thành lập Đảng CSVN",
    (14, 2): "Lễ Tình nhân",
    (27, 2): "Thầy thuốc Việt Nam",
    (8, 3): "Quốc tế Phụ nữ",
    (26, 3): "Thành lập Đoàn TNCS HCM",
    (30, 4): "Giải phóng miền Nam",
    (1, 5): "Quốc tế Lao động",
    (19, 5): "Ngày sinh Chủ tịch Hồ Chí Minh",
    (1, 6): "Quốc tế Thiếu nhi",
    (28, 6): "Ngày Gia đình Việt Nam",
    (27, 7): "Thương binh Liệt sĩ",
    (19, 8): "Cách mạng Tháng Tám",
    (2, 9): "Quốc khánh",
    (10, 10): "Giải phóng Thủ đô",
    (20, 10): "Phụ nữ Việt Nam",
    (20, 11): "Nhà giáo Việt Nam",
    (22, 12): "Thành lập QĐND Việt Nam",
    (24, 12): "Đêm Giáng sinh",
    (25, 12): "Lễ Giáng sinh",
}

NGAY_LE_AM = {
    (1, 1): "Tết Nguyên Đán",
    (2, 1): "Mùng 2 Tết",
    (3, 1): "Mùng 3 Tết",
    (15, 1): "Tết Nguyên Tiêu",
    (3, 3): "Tết Hàn thực",
    (10, 3): "Giỗ Tổ Hùng Vương",
    (15, 4): "Lễ Phật Đản",
    (5, 5): "Tết Đoan Ngọ",
    (15, 7): "Lễ Vu Lan",
    (15, 8): "Tết Trung Thu",
    (9, 9): "Tết Trùng Cửu",
    (10, 10): "Tết Thường Tân",
    (23, 12): "Ông Công Ông Táo",
}


# ----------------------------------------------------------------- lõi thiên văn
def jd_from_date(dd, mm, yy):
    a = (14 - mm) // 12
    y = yy + 4800 - a
    m = mm + 12 * a - 3
    jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    if jd < 2299161:
        jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083
    return jd


def jd_to_date(jd):
    if jd > 2299160:
        a = jd + 32044
        b = (4 * a + 3) // 146097
        c = a - (b * 146097) // 4
    else:
        b = 0
        c = jd + 32082
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = b * 100 + d - 4800 + m // 10
    return day, month, year


def _new_moon(k):
    T = k / 1236.85
    T2 = T * T
    T3 = T2 * T
    dr = math.pi / 180
    jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * T2 - 0.000000155 * T3
    jd1 = jd1 + 0.00033 * math.sin((166.56 + 132.87 * T - 0.009173 * T2) * dr)
    M = 359.2242 + 29.10535608 * k - 0.0000333 * T2 - 0.00000347 * T3
    Mpr = 306.0253 + 385.81691806 * k + 0.0107306 * T2 + 0.00001236 * T3
    F = 21.2964 + 390.67050646 * k - 0.0016528 * T2 - 0.00000239 * T3
    C1 = (0.1734 - 0.000393 * T) * math.sin(M * dr) + 0.0021 * math.sin(2 * dr * M)
    C1 = C1 - 0.4068 * math.sin(Mpr * dr) + 0.0161 * math.sin(dr * 2 * Mpr)
    C1 = C1 - 0.0004 * math.sin(dr * 3 * Mpr)
    C1 = C1 + 0.0104 * math.sin(dr * 2 * F) - 0.0051 * math.sin(dr * (M + Mpr))
    C1 = C1 - 0.0074 * math.sin(dr * (M - Mpr)) + 0.0004 * math.sin(dr * (2 * F + M))
    C1 = C1 - 0.0004 * math.sin(dr * (2 * F - M)) - 0.0006 * math.sin(dr * (2 * F + Mpr))
    C1 = C1 + 0.0010 * math.sin(dr * (2 * F - Mpr)) + 0.0005 * math.sin(dr * (2 * Mpr + M))
    if T < -11:
        deltat = 0.001 + 0.000839 * T + 0.0002261 * T2 - 0.00000845 * T3 - 0.000000081 * T * T3
    else:
        deltat = -0.000278 + 0.000265 * T + 0.000262 * T2
    return jd1 + C1 - deltat


def _new_moon_day(k, tz=TZ):
    return int(math.floor(_new_moon(k) + 0.5 + tz / 24.0))


def _sun_longitude_rad(jdn):
    T = (jdn - 2451545.0) / 36525
    T2 = T * T
    dr = math.pi / 180
    M = 357.52910 + 35999.05030 * T - 0.0001559 * T2 - 0.00000048 * T * T2
    L0 = 280.46645 + 36000.76983 * T + 0.0003032 * T2
    DL = (1.914600 - 0.004817 * T - 0.000014 * T2) * math.sin(dr * M)
    DL = DL + (0.019993 - 0.000101 * T) * math.sin(dr * 2 * M) + 0.000290 * math.sin(dr * 3 * M)
    L = (L0 + DL) * dr
    L = L - math.pi * 2 * math.floor(L / (math.pi * 2))
    return L


def _sun_longitude_sector(day_number, tz=TZ):
    """0..11 – cung hoàng đạo 30° chứa Mặt Trời lúc 0h ngày day_number."""
    return int(math.floor(_sun_longitude_rad(day_number - 0.5 - tz / 24.0) / math.pi * 6))


def _lunar_month11(yy, tz=TZ):
    off = jd_from_date(31, 12, yy) - 2415021
    k = int(math.floor(off / 29.530588853))
    nm = _new_moon_day(k, tz)
    if _sun_longitude_sector(nm, tz) >= 9:
        nm = _new_moon_day(k - 1, tz)
    return nm


def _leap_month_offset(a11, tz=TZ):
    k = int(math.floor((a11 - 2415021.076998695) / 29.530588853 + 0.5))
    i = 1
    arc = _sun_longitude_sector(_new_moon_day(k + i, tz), tz)
    while True:
        last = arc
        i += 1
        arc = _sun_longitude_sector(_new_moon_day(k + i, tz), tz)
        if not (arc != last and i < 14):
            break
    return i - 1


# ----------------------------------------------------------------- chuyển đổi
def solar_to_lunar(dd, mm, yy, tz=TZ):
    day_number = jd_from_date(dd, mm, yy)
    k = int(math.floor((day_number - 2415021.076998695) / 29.530588853))
    month_start = _new_moon_day(k + 1, tz)
    if month_start > day_number:
        month_start = _new_moon_day(k, tz)
    a11 = _lunar_month11(yy, tz)
    b11 = a11
    if a11 >= month_start:
        lunar_year = yy
        a11 = _lunar_month11(yy - 1, tz)
    else:
        lunar_year = yy + 1
        b11 = _lunar_month11(yy + 1, tz)
    lunar_day = day_number - month_start + 1
    diff = int(math.floor((month_start - a11) / 29))
    lunar_leap = 0
    lunar_month = diff + 11
    if b11 - a11 > 365:
        leap_month_diff = _leap_month_offset(a11, tz)
        if diff >= leap_month_diff:
            lunar_month = diff + 10
            if diff == leap_month_diff:
                lunar_leap = 1
    if lunar_month > 12:
        lunar_month -= 12
    if lunar_month >= 11 and diff < 4:
        lunar_year -= 1
    return lunar_day, lunar_month, lunar_year, lunar_leap


def lunar_to_solar(lunar_day, lunar_month, lunar_year, lunar_leap=0, tz=TZ):
    if lunar_month < 11:
        a11 = _lunar_month11(lunar_year - 1, tz)
        b11 = _lunar_month11(lunar_year, tz)
    else:
        a11 = _lunar_month11(lunar_year, tz)
        b11 = _lunar_month11(lunar_year + 1, tz)
    k = int(math.floor(0.5 + (a11 - 2415021.076998695) / 29.530588853))
    off = lunar_month - 11
    if off < 0:
        off += 12
    if b11 - a11 > 365:
        leap_off = _leap_month_offset(a11, tz)
        leap_month = leap_off - 2
        if leap_month < 0:
            leap_month += 12
        if lunar_leap != 0 and lunar_month != leap_month:
            return 0, 0, 0
        elif lunar_leap != 0 or off >= leap_off:
            off += 1
    month_start = _new_moon_day(k + off, tz)
    return jd_to_date(month_start + lunar_day - 1)


# ----------------------------------------------------------------- Can Chi & tiện ích
def can_chi_nam(lunar_year):
    return f"{CAN[(lunar_year + 6) % 10]} {CHI[(lunar_year + 8) % 12]}"


def can_chi_thang(lunar_month, lunar_year):
    return f"{CAN[(lunar_year * 12 + lunar_month + 3) % 10]} {CHI[(lunar_month + 1) % 12]}"


def can_chi_ngay(jd):
    return f"{CAN[(jd + 9) % 10]} {CHI[(jd + 1) % 12]}"


def tiet_khi(jd, tz=TZ):
    idx = int(math.floor(_sun_longitude_rad(jd + 1 - 0.5 - tz / 24.0) / math.pi * 12))
    return TIET_KHI[idx % 24]


def gio_hoang_dao(jd):
    pattern = _GIO_HD[((jd + 1) % 12) % 6]
    out = []
    for i, c in enumerate(pattern):
        if c == "1":
            out.append(f"{CHI[i]} ({(i * 2 + 23) % 24}-{(i * 2 + 1) % 24}h)")
    return out


def ten_thang_am(lunar_month, leap=0):
    s = f"tháng {TEN_THANG_AM[lunar_month - 1]}"
    return s + " nhuận" if leap else s


def ngay_le(d, m, y, ld=None, lm=None, ly=None, leap=None):
    """Danh sách ngày lễ (dương + âm) của một ngày."""
    if ld is None:
        ld, lm, ly, leap = solar_to_lunar(d, m, y)
    out = []
    if (d, m) in NGAY_LE_DUONG:
        out.append(NGAY_LE_DUONG[(d, m)])
    if not leap:
        if (ld, lm) in NGAY_LE_AM:
            out.append(NGAY_LE_AM[(ld, lm)])
        if lm == 12 and ld >= 29:
            nxt = _dt.date(y, m, d) + _dt.timedelta(days=1)
            nld, nlm, _, _ = solar_to_lunar(nxt.day, nxt.month, nxt.year)
            if nld == 1 and nlm == 1:
                out.append("Giao thừa")
    return out


def days_to_tet(date):
    """(số ngày còn lại, tên năm âm sắp tới) tính đến mùng 1 Tết kế tiếp."""
    ld, lm, ly, leap = solar_to_lunar(date.day, date.month, date.year)
    target_year = ly + 1
    d, m, y = lunar_to_solar(1, 1, target_year)
    delta = (_dt.date(y, m, d) - date).days
    return delta, can_chi_nam(target_year)


def day_info(date):
    """Thông tin đầy đủ của một ngày dương lịch (datetime.date)."""
    d, m, y = date.day, date.month, date.year
    ld, lm, ly, leap = solar_to_lunar(d, m, y)
    jd = jd_from_date(d, m, y)
    return {
        "date": date,
        "thu": THU[date.weekday()],
        "lunar_day": ld,
        "lunar_month": lm,
        "lunar_year": ly,
        "leap": leap,
        "nam": can_chi_nam(ly),
        "thang": can_chi_thang(lm, ly) + (" (nhuận)" if leap else ""),
        "ngay": can_chi_ngay(jd),
        "tiet_khi": tiet_khi(jd),
        "gio_hd": gio_hoang_dao(jd),
        "le": ngay_le(d, m, y, ld, lm, ly, leap),
        "ten_thang": ten_thang_am(lm, leap),
    }


if __name__ == "__main__":
    today = _dt.date.today()
    info = day_info(today)
    print(f"{info['thu']}, {today:%d/%m/%Y}")
    print(f"Âm lịch: {info['lunar_day']}/{info['lunar_month']}"
          f"{' nhuận' if info['leap'] else ''} năm {info['nam']}")
    print(f"Ngày {info['ngay']}, tháng {info['thang']}, tiết {info['tiet_khi']}")
    print("Giờ hoàng đạo:", ", ".join(info["gio_hd"]))
    if info["le"]:
        print("Ngày lễ:", ", ".join(info["le"]))
