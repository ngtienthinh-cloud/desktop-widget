# Desktop Widget – Thời tiết · Lịch âm dương · Việc cần làm · Ghi chú

Widget nền trong suốt cho Windows 10/11. Nằm trên màn hình nền, tự chạy cùng máy, chỉ hiện một biểu tượng lịch nhỏ ở khay hệ thống (góc phải thanh tác vụ). Không mở cửa sổ CMD.

## Cài đặt (mọi máy Windows, không cần Python)

1. Vào mục **Releases** của repo, tải file **`DesktopWidget.exe`**.
2. Nhấp đúp để chạy. Nếu Windows SmartScreen hiện cảnh báo "Windows protected your PC", bấm **More info → Run anyway** (file chưa ký số nên Windows cảnh báo lần đầu).
3. Hộp thoại hỏi **Cài đặt** hoặc **Chạy luôn**:
   - **Cài đặt** (nên chọn): app tự chép vào `%LOCALAPPDATA%\Programs\DesktopWidget`, tạo lối tắt trong Start Menu và tự chạy mỗi khi bật máy. Không cần quyền quản trị.
   - **Chạy luôn**: dùng ngay tại chỗ (vẫn tự khởi động cùng Windows từ vị trí hiện tại).

Muốn chép sang máy khác: chỉ cần mang theo file `DesktopWidget.exe`.

## Sử dụng

| Thao tác | Cách làm |
|---|---|
| Di chuyển widget | Giữ chuột trái vào chỗ trống rồi kéo |
| Đổi kích thước | Kéo góc dưới bên phải |
| Mở menu / Cài đặt | Chuột phải vào widget, hoặc chuột phải biểu tượng ở khay hệ thống |
| Ẩn / hiện nhanh | Nhấp trái vào biểu tượng ở khay hệ thống |
| Thêm việc | Gõ vào ô "Thêm việc mới…" rồi Enter; bấm 📅 để đặt hạn trước khi thêm |
| Sửa / đặt hạn / đánh dấu quan trọng | Nhấp đúp vào việc để sửa; chuột phải để có thêm tuỳ chọn |
| Ghi chú nhiều trang | Bấm ＋ để thêm trang; nhấp đúp tên trang để đổi tên |
| Xem chi tiết một ngày | Rê chuột lên ngày trong lịch tháng; bấm vào ngày để ghim thông tin; lăn chuột để đổi tháng |

**Cài đặt** gồm:
- **Giao diện**: độ đậm của nền (0 % là trong suốt hoàn toàn), màu nền, màu chữ, màu nhấn, bo góc, cỡ chữ, các mẫu màu có sẵn, hiệu ứng kính mờ (thử nghiệm).
- **Hiển thị**: bật/tắt từng khối: đồng hồ & lịch âm, giây, giờ hoàng đạo, thời tiết, lịch tháng, việc cần làm, ghi chú.
- **Thời tiết**: tìm địa điểm theo tên (có dấu hoặc không dấu) hoặc nhập toạ độ; chu kỳ cập nhật. Dữ liệu lấy từ Open-Meteo, miễn phí, không cần tài khoản.
- **Hệ thống**: vị trí cửa sổ (dưới cùng như widget / luôn nổi trên cùng / bình thường), không bị ẩn khi bấm Win+D, khoá vị trí, khởi động cùng Windows.

## Lịch âm

Tính theo thuật toán thiên văn của Hồ Ngọc Đức, múi giờ Việt Nam (GMT+7): ngày tháng âm, tháng nhuận, Can Chi năm/tháng/ngày, tiết khí, giờ hoàng đạo, các ngày lễ âm/dương, đếm ngược đến Tết. Đã kiểm tra khớp các mốc Tết 1985, 2007, 2023–2027 và tháng nhuận 2020, 2023, 2025.

## Dữ liệu

Lưu tại `%APPDATA%\DesktopWidget\`:
- `data.json`: việc cần làm và ghi chú (mỗi lần khởi động tự sao lưu ra `data.backup.json`)
- `config.json`: cài đặt
- `weather.json`: bản thời tiết gần nhất (dùng khi mất mạng)
- `error.log`: nhật ký lỗi, nếu có

## Gỡ bỏ

Chuột phải biểu tượng ở khay → bỏ chọn **Khởi động cùng Windows** → **Thoát**. Sau đó xoá thư mục `%LOCALAPPDATA%\Programs\DesktopWidget`, lối tắt "Desktop Widget" trong Start Menu và (nếu muốn xoá cả dữ liệu) thư mục `%APPDATA%\DesktopWidget`.

## Dành cho người phát triển

- Mã nguồn: `desktop_widget.py` (giao diện PySide6), `core.py` (cấu hình, thời tiết, tự khởi động), `amlich_vn.py` (lịch âm).
- Mỗi lần push lên nhánh `main`, GitHub Actions sẽ chạy kiểm thử, tự kiểm tra giao diện trên Windows, build `DesktopWidget.exe` bằng PyInstaller và đăng lên Releases.
- Tự build trên máy có Python: chạy `build_exe.bat` → `dist\DesktopWidget.exe`.
