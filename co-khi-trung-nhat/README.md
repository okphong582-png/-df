# Cơ Khí Trung Nhất

Website giới thiệu hệ thống hút mùi, chuyền in, ống gió và các phụ kiện cơ khí.
HTML, CSS và JavaScript thuần; ảnh và video nằm trong `media/`.

## Triển khai trên Vercel

Import repository `okphong582-png/-df` với các thiết lập:

| Thiết lập | Giá trị |
| --- | --- |
| Production Branch | `main` |
| Root Directory | `co-khi-trung-nhat` |
| Framework Preset | `Other` |
| Build Command | Không cần |
| Install Command | Không cần |
| Output Directory | `.` |
| Environment Variables | Không cần |

`vercel.json` cấu hình website tĩnh. Không chọn thư mục gốc của repository:
những file ngoài thư mục này thuộc dự án khác.

## Kiểm tra tại máy

Dùng static HTTP server với thư mục gốc là thư mục chứa `index.html`.
Đã kiểm tra bố cục desktop/mobile, menu, các đích liên hệ, điều khiển video,
gallery ảnh và thao tác Tab/Escape trong gallery.

## Nội dung

Giữ nguyên ảnh, video, số điện thoại, địa chỉ, mã số thuế, liên kết Zalo và
Google Maps từ bản nguồn. Giao diện có menu trên điện thoại, nhãn sản phẩm
tách khỏi ảnh và lưới ảnh công trình.
