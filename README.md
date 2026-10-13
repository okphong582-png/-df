# Proxy Free Fire + Telegram

## Lỗi đăng nhập trong ảnh

Log đã cho thấy proxy trả HTTP 403 vì IP chưa có quyền. `BLOCK_MSG` là
`Cút khỏi server ch có quyền truy cập`. JSON/text của proxy không thay được
hộp thoại lỗi dựng sẵn trong game. Xem câu này và lý do tại
`http://IP-MAY-CHU:1297/status`. Không tuyên bố đã đổi được giao diện game.

Bot chỉ báo kích hoạt thành công khi ghi quyền IP vào Firebase thành công.
IP hết hạn, sai IP hoặc dữ liệu Firebase mất cập nhật quá 15 giây đều bị từ chối.
Địa chỉ IP mạng di động có thể đổi: cần nhận diện lại và cấp quyền đúng IP.

## Chạy khi tắt PC

**Chưa có VPS thì chưa thể chạy độc lập với PC.** GitHub lưu mã; GitHub Pages
không chạy Python hoặc mở cổng TCP proxy. Workflow trong repo chỉ kiểm tra mã
và build Docker, không dùng Actions làm máy chủ chạy liên tục.

Khi đã có máy Linux/VPS với Docker Engine và Docker Compose:

```sh
git clone https://github.com/okphong582-png/-df.git ff-proxy
cd ff-proxy
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 proxy bot
```

Điền `BOT_TOKEN`, `ADMIN_ID`, `FIREBASE_URL`, `LINK4M_TOKEN`,
`PUBLIC_PROXY_HOST` (IP/domain của VPS **của bạn**) trong `.env`.
Không đưa token, `.env`, `config.json` hoặc private key lên GitHub.
Các bản cũ chứa token Link4m trong mã; bản này đọc từ cấu hình riêng.
Firebase REST phải có quyền đọc/ghi theo cách dự án hiện đang sử dụng;
bản này chưa tích hợp Firebase Admin SDK hoặc thay đổi Database Rules.

Mở TCP 1297 trên firewall/cloud firewall; không mở API quản trị 8088 ra Internet.
Để Docker chạy sau khi reboot trên hệ có systemd: `sudo systemctl enable --now docker`.
Container tự khởi động lại khi tiến trình thoát và sau khi Docker/máy chủ khởi động lại.
`docker compose stop` là dừng chủ động; cần `docker compose up -d` để bật lại.
Healthcheck chỉ báo trạng thái, không tự sửa treo tiến trình hoặc VPS mất điện/mạng.
Để cập nhật mã: `git pull --ff-only` rồi `docker compose up -d --build`.

**159.223.110.159 trong bản cũ là địa chỉ tunnel đã được ghi cứng, không phải VPS
đã được cấp cho bạn.** Tunnel vẫn cần PC chạy. Kết nối Bore làm proxy thấy
127.0.0.1 nên không xác định được IP gốc. Bản này không cấp quyền cho mọi người
chỉ vì có một IP đang hoạt động; cũng không tin `X-Forwarded-For` do khách gửi.
Nên kết nối thẳng tới VPS và dùng cùng mạng khi lấy key / mở game.

## iPhone / Potatso

Đã kèm `client/potatso-uri.txt`, QR và subscription cho **địa chỉ cũ**
159.223.110.159:1297 để tiện nhập. Đây là cấu hình, không phải bằng chứng server
đang online. Khi có VPS thật, tạo lại:

```sh
python -m pip install 'qrcode[pil]'
python make_potatso.py --host IP-VPS-CUA-BAN --port 1297
```

Trong Potatso, Add Proxy / Import → URI, dán dòng trong `potatso-uri.txt`,
hoặc quét `potatso-qr.png`. Nếu phiên bản app không nhận URI HTTP, nhập thủ công:
Type **HTTP**, Host **IP-VPS**, Port **1297**, không nhập username/password.
Không chọn SOCKS5, Shadowsocks hoặc HTTPS: server hiện là HTTP proxy có CONNECT.
Subscription là danh sách URI được base64; hỗ trợ nhập tùy phiên bản app.
Lấy key và cấp quyền IP khi VPN đang tắt trước; dùng cùng mạng khi bật lại VPN.
Lưu proxy, chọn proxy rồi nhấn Connect và cho phép iOS tạo cấu hình VPN.
File không thể tự cài/bật VPN hoặc đảm bảo tự nối lại nếu app không hỗ trợ.
Chưa kiểm thử trực tiếp trên iPhone/Potatso của bạn.

Game đang dùng MITM cần chứng chỉ CA của **đúng máy chủ**. Sau khi IP đã được
cấp quyền, bật proxy, mở `http://mitm.it`, tải chứng chỉ iOS, cài hồ sơ trong
Cài đặt → Cài đặt chung → VPN & Quản lý thiết bị; sau đó bật tin cậy CA trong
Cài đặt chung → Giới thiệu → Cài đặt tin cậy chứng nhận. Chỉ tin CA từ máy chủ
bạn quản lý. Volume `proxy-ca` giữ CA qua các lần khởi động lại; không xóa volume
hoặc chia sẻ `mitmproxy-ca.pem` (chứa private key).

## Tốc độ mạng / game

- Kiểm tra IP dùng snapshot trong RAM; một worker cập nhật mỗi 5 giây, không
  gọi Firebase cho từng request hoặc mỗi lần gặp IP lạ.
- Bật HTTP/2, giữ kết nối upstream, giảm timeout thử CDN khác xuống 4 giây mỗi
  máy; thử CDN dự phòng chạy ở worker để không chặn toàn bộ event loop.
- TLS ngoài các miền game đi qua tunnel, không giải mã. Với Potatso chế độ
  toàn bộ proxy, lưu lượng đó **vẫn qua máy chủ**, không phải kết nối DIRECT.
- Muốn Internet ngoài game đi thẳng: dùng quy tắc định tuyến của phiên bản
  Potatso có hỗ trợ, chỉ đưa `freefiremobile.com`, `purplevioleto.com`,
  `ppmainecoonghj.com` và subdomain qua proxy, mặc định DIRECT. Không đổi cổng
  thành SOCKS để thử tăng tốc. HTTP proxy không cung cấp UDP relay cho game.
- `client/game-only.pac` là lựa chọn riêng cho HTTP proxy tự động của Wi-Fi
  iOS, **không phải file VPN Potatso**. Host PAC bằng HTTPS ở nơi bạn quản lý
  rồi nhập URL trong Wi-Fi → Định cấu hình proxy → Tự động. Nó đưa các miền
  game qua proxy và phần còn lại DIRECT. Không dùng đồng thời với VPN toàn bộ
  lưu lượng vì VPN có thể ghi đè đường đi; PAC không áp dụng cho dữ liệu di động.

Chưa đo ping/tốc độ trên thiết bị; không bảo đảm giảm ping. Bỏ tunnel công cộng
và chọn VPS gần người chơi thường loại bỏ được một chặng trung gian, nhưng kết
quả phụ thuộc nhà mạng, tuyến và tải máy chủ.

## Chạy trên Windows để thử

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item config.example.json config.json   # Chỉ dùng nếu chưa có config.json
# Điền cấu hình trong config.json
.\.venv\Scripts\python.exe run_local.py
```

`start all.bat` và `start_proxy.bat` gọi supervisor này. Ctrl+C dừng đúng các
tiến trình con của lần chạy, không taskkill mọi Python trên máy. Không tự tạo
tunnel Bore, không in thông báo giả là địa chỉ public đã online.
Muốn thử trên LAN, cấp quyền IP LAN thực tế của iPhone; public IP lấy ngoài
Internet không khớp IP LAN mà proxy nhìn thấy.

Giữ `admin-config.js` riêng cho dashboard trên máy của bạn; mẫu là
`admin-config.example.js`. API tạo key chỉ bind 127.0.0.1. Quản trị VPS bằng bot
Telegram; dashboard local không tự kết nối API nằm trong container ở VPS.

## Kiểm tra

```sh
python -m pytest -q
```

Bao gồm kiểm tra quyền chính xác, hết hạn, snapshot quá cũ, giả mạo header,
không mở proxy công cộng cho IP chưa cấp quyền, phản hồi 403 giữ nguyên,
host ngoài game không bị thay patch, cấu hình URI và tính toàn vẹn gzip.

Nguồn: [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages),
[Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/),
[Potatso trên App Store](https://apps.apple.com/us/app/potatso/id1239860606),
[Chứng chỉ mitmproxy](https://docs.mitmproxy.org/stable/concepts/certificates/).
