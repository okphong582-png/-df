# Proxy Free Fire + Telegram

## Lỗi đăng nhập trong ảnh

Log đã cho thấy proxy trả HTTP 403 vì IP chưa có quyền. `BLOCK_MSG` là
`Cút khỏi server ch có quyền truy cập`. JSON/text của proxy không thay được
hộp thoại lỗi dựng sẵn trong game. Xem câu này và lý do tại
`http://IP-MAY-CHU:1297/status`. Không tuyên bố đã đổi được giao diện game.

Bot chỉ báo kích hoạt thành công khi ghi quyền IP vào Firebase thành công.
IP hết hạn, sai IP hoặc dữ liệu Firebase mất cập nhật quá 6 giây đều bị từ chối.
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
đã được cấp cho bạn.** Tunnel vẫn cần PC chạy. Kết nối Bore làm proxy thấy 127.0.0.1.
**Đã bỏ quyền dùng chung tunnel.** Chế độ PC dùng `AUTH_MODE=tunnel_credentials`:
mỗi người cần username/password proxy riêng, gắn với bản ghi quyền IP trong
Firebase. Thu hồi/xóa bản ghi hoặc hết hạn sẽ chặn tài khoản tương ứng dù
người khác vẫn còn quyền. Chế độ cũ `tunnel_compat` cũng yêu cầu tài khoản;
không có nhánh nào cho qua chỉ vì có một IP khác đang hoạt động.

Bot lưu hash SHA-256 của mật khẩu; mật khẩu chỉ trả riêng cho người yêu cầu.
Proxy kiểm tra lại quyền trên từng lượt tải fileinfo/codepatch và đăng nhập,
kể cả kết nối HTTPS đã mở. Worker lấy quyền khoảng mỗi 2 giây; thay đổi thường
có hiệu lực trong 2–4 giây. Nếu Firebase không cập nhật quá 6 giây, proxy từ
chối lượt tải được bảo vệ. Đây không phải cam kết ngắt tức thì.

**File đã tải, cache hoặc nạp trong game không thể thu hồi/xóa từ xa bằng proxy.**
Thu hồi quyền chặn các lượt tải mới đi qua proxy; không bảo đảm đá được phiên
chơi/UDP đã tồn tại hoặc ngăn người dùng đọc bản file đã lưu trước đó.

Chế độ VPS/Docker vẫn kiểm tra đúng IP trên mọi kết nối; không tin header
X-Forwarded-For do khách gửi. Chế độ tunnel kiểm tra tài khoản thay cho IP gốc
vì Bore không chuyển tiếp IP gốc. Mật khẩu được gửi theo HTTP Basic tới proxy;
Bore/HTTP không cung cấp mã hóa cho phần thông tin xác thực này. Không dùng lại
mật khẩu tài khoản khác. Firebase Database Rules hiện có vẫn cần kiểm soát
quyền ghi; bản này chưa triển khai Firebase Auth/Rules mới.

## iPhone / Potatso

**Cấu hình cũ chỉ có IP/cổng không còn được tải patch qua Bore.**
Trong Telegram bot: bấm `/start` → **📲 Cấu hình Potatso riêng**. Nếu bản ghi
quyền của bạn còn hạn, bot cấp username/password và URI để nhập. Người chưa
có quyền hoặc đã bị thu hồi phải xác thực key trước; nút này không tự cấp lại
quyền. Mỗi lần lấy lại cấu hình sẽ đổi mật khẩu của bản ghi được chọn và làm
cấu hình trước đó hết hiệu lực sau khi proxy cập nhật.

Trong Potatso: Add Proxy / Import → URI, dán URI có username/password mà bot
trả về. Hoặc nhập Type **HTTP**, Host **159.223.110.159**, Port **1297**,
Username/Password theo bot. Lưu, chọn proxy và nhấn Connect. Lấy cấu hình khi
VPN đang tắt để bot/trình duyệt có thể hoạt động trước khi cấp quyền.
Đổi IP/domain thành VPS của bạn khi có VPS; địa chỉ trên là tunnel cũ.

Các file mẫu trong `client/` chỉ chứa endpoint, không phải cấu hình được cấp
quyền. Không đăng URI/mật khẩu riêng lên GitHub hoặc chia sẻ cho người khác.
Muốn xuất file/QR cá nhân trên máy:

```sh
python -m pip install 'qrcode[pil]'
python make_potatso.py --host 159.223.110.159 --port 1297 --username TELEGRAM_USER_ID
# Nhập password khi được hỏi; kết quả ở dist/potatso (được gitignore).
```

File không tự cài/bật VPN hoặc đảm bảo app tự nối lại. Chưa thử trực tiếp trên
Potatso/iPhone của bạn; kiểm tra giao thức HTTP Basic qua CONNECT bằng mitmdump
thật đã có trong bộ test.

Game đang dùng MITM cần chứng chỉ CA của **đúng máy chủ**. Sau khi IP đã được
cấp quyền, bật proxy, mở `http://mitm.it`, tải chứng chỉ iOS, cài hồ sơ trong
Cài đặt → Cài đặt chung → VPN & Quản lý thiết bị; sau đó bật tin cậy CA trong
Cài đặt chung → Giới thiệu → Cài đặt tin cậy chứng nhận. Chỉ tin CA từ máy chủ
bạn quản lý. Volume `proxy-ca` giữ CA qua các lần khởi động lại; không xóa volume
hoặc chia sẻ `mitmproxy-ca.pem` (chứa private key).

## Tốc độ mạng / game

- Kiểm tra IP dùng snapshot trong RAM; một worker cập nhật khoảng mỗi 2 giây, không
  gọi Firebase cho từng request hoặc mỗi lần gặp IP lạ.
- Bật HTTP/2 ở chế độ VPS, giữ kết nối upstream, giảm timeout thử CDN khác xuống 4 giây mỗi
  máy; thử CDN dự phòng chạy ở worker để không chặn toàn bộ event loop.
- TLS ngoài các miền game đi qua tunnel, không giải mã. Với Potatso chế độ
  toàn bộ proxy, lưu lượng đó **vẫn qua máy chủ**, không phải kết nối DIRECT.
- Muốn Internet ngoài game đi thẳng: dùng quy tắc định tuyến của phiên bản
  Potatso có hỗ trợ, chỉ đưa `freefiremobile.com`, `purplevioleto.com`,
  `ppmainecoonghj.com` và subdomain qua proxy, mặc định DIRECT. Không đổi cổng
  thành SOCKS để thử tăng tốc. HTTP proxy không cung cấp UDP relay cho game.
- `client/game-only.pac` là mẫu HTTP proxy tự động cho Wi-Fi ở chế độ VPS/LAN
  cấp quyền trực tiếp theo IP, **không dùng cho chế độ Bore cần tài khoản riêng**.
  PAC không tự chứa username/password và không phải file VPN Potatso. Host PAC bằng HTTPS ở nơi bạn quản lý
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

`start_proxy.bat` tự mở **MITMDump Server + Bore Public Tunnel** ở hai cửa sổ.
`start all.bat` mở thêm **Telegram Bot**. Chỉ chạy một trong hai launcher, không
mở mitmdump thủ công lần nữa. Các dịch vụ tự khởi động lại khi thoát; Ctrl+C
ở cửa sổ launcher dừng đúng các tiến trình con của lần chạy.
Bore phải báo kết nối/listening thành công thì IP/cổng public mới dùng được.
Log nằm trong `logs/`; không commit log lên GitHub. `bore.exe` cần có sẵn trong
thư mục khi dùng tunnel. Launcher ưu tiên mitmdump đã cài trên máy và giữ nguyên
CA ở thư mục cấu hình người dùng, không thay CA đang cài trên iPhone.
Để chạy trực tiếp LAN/VPS không có Bore: `python run_local.py --direct`.
Chế độ PC khôi phục HTTP/1.1 như bản cũ; HTTP/2 vẫn bật trong chế độ VPS.
Theo yêu cầu chẩn đoán, launcher hiển thị log kết nối và các dòng `[GAME]`
cho biết bước xác thực/API/mã phản hồi. Không in body đăng nhập, mật khẩu hoặc
query string trong dòng chẩn đoán. File `logs/proxy-events.log` có thời gian
chờ, kích thước phản hồi và tuổi cache quyền. Log kiểm tra nằm ở file riêng.
Bore chỉ hiện cảnh báo/lỗi; lỗi socket 10053 lặp lại được giới hạn hiển thị mỗi 30 giây.
Kết nối HTTPS tới miền game trả chuẩn `407 Proxy Authentication Required`
với `Proxy-Authenticate: Basic` nếu chưa xác thực, để ứng dụng proxy có thể
gửi/nhập lại tài khoản trước khi tạo tunnel TLS. Quyền vẫn kiểm tra lại trên
từng request sau khi TLS đã mở; không giữ kết quả cho phép sau thu hồi.
Bore dùng IPv4 tới máy chủ và `--local-host 127.0.0.1` tới mitmdump để tránh
nhầm localhost sang IPv6. Bot bỏ qua hàng đợi cũ khi khởi động; nếu đã gửi key
trong lúc bot tắt, hãy gửi lại sau khi bot bật.
Ẩn log không làm tăng băng thông tunnel. Trên 4G/Wi-Fi khác, đường truyền vẫn
đi vòng qua Bore và PC; cần đo trên iPhone để đánh giá tốc độ game.
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
host ngoài game không bị thay patch, cấu hình URI, tài khoản riêng, thu hồi trên kết nối HTTPS đang mở dù người khác còn quyền, và tính toàn vẹn gzip.

Nguồn: [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages),
[Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/),
[Potatso trên App Store](https://apps.apple.com/us/app/potatso/id1239860606),
[Chứng chỉ mitmproxy](https://docs.mitmproxy.org/stable/concepts/certificates/).

Việc cấp lại mật khẩu dùng [Firebase conditional requests](https://firebase.google.com/docs/database/rest/save-data#section-conditional-requests) để tránh ghi đè khôi phục bản ghi vừa bị admin xóa.
