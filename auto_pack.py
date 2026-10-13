import os
import gzip
import hashlib
import base64
import UnityPy

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE, "bundle_template.bin")
PATCH_BYTES_PATH = os.path.join(BASE, "Assembly-CSharp-patch.bytes")
OUT_BUNDLE_PATH = os.path.join(BASE, "assembly-csharp-patch")
OUT_GZ_PATH = os.path.join(BASE, "assembly-csharp-patch.gz")

def pack():
    if not os.path.isfile(PATCH_BYTES_PATH):
        print(f"[!] Không tìm thấy file: {PATCH_BYTES_PATH}")
        return False

    with open(PATCH_BYTES_PATH, "rb") as f:
        patch_bytes = f.read()

    print(f"[*] Đọc file Assembly-CSharp-patch.bytes: {len(patch_bytes)} bytes")

    if not os.path.isfile(TEMPLATE_PATH):
        print(f"[!] Không tìm thấy template: {TEMPLATE_PATH}")
        return False

    with open(TEMPLATE_PATH, "rb") as f:
        template_data = f.read()

    # Nạp UnityFS bundle template
    env = UnityPy.load(template_data)
    found = False
    for obj in env.objects:
        if obj.type.name == "TextAsset":
            ta = obj.read()
            print(f"[*] Tìm thấy TextAsset: '{ta.m_Name}' (kích thước cũ: {len(ta.m_Script)} bytes)")
            ta.m_Script = patch_bytes.decode("utf-8", "surrogateescape")
            ta.save()
            found = True
            break

    if not found:
        print("[!] Không tìm thấy TextAsset trong bundle template!")
        return False

    # Đóng gói AssetBundle mới
    new_bundle = env.file.save()
    print(f"[OK] Đã đóng gói UnityFS bundle mới: {len(new_bundle)} bytes")

    # Lưu file thô assembly-csharp-patch
    with open(OUT_BUNDLE_PATH, "wb") as f:
        f.write(new_bundle)

    # Nén gzip assembly-csharp-patch.gz
    gz_data = gzip.compress(new_bundle, compresslevel=9, mtime=0)
    with open(OUT_GZ_PATH, "wb") as f:
        f.write(gz_data)
    print(f"[OK] Đã tạo file gzip assembly-csharp-patch.gz: {len(gz_data)} bytes")

    # Tính hash
    raw_sha1 = base64.b64encode(hashlib.sha1(new_bundle).digest()).decode("ascii")
    gz_sha1 = base64.b64encode(hashlib.sha1(gz_data).digest()).decode("ascii")
    print(f"[*] Raw SHA1: {raw_sha1}")
    print(f"[*] Gzip SHA1: {gz_sha1}")

    # Xác thực giải nén kiểm tra lại
    env_verify = UnityPy.load(new_bundle)
    for obj in env_verify.objects:
        if obj.type.name == "TextAsset":
            ta = obj.read()
            verified = ta.m_Script.encode("utf-8", "surrogateescape") if isinstance(ta.m_Script, str) else ta.m_Script
            if verified == patch_bytes:
                print("[SUCCESS] Xác thực thành công: Ruột TextAsset khớp 100% với file Assembly-CSharp-patch.bytes!")
            else:
                print("[!] CẢNH BÁO: Dữ liệu sau đóng gói không khớp!")
    return True

if __name__ == "__main__":
    pack()
