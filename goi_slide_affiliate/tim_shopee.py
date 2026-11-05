# Tìm sản phẩm trên Shopee bằng trình duyệt thật, lưu kết quả ra CSV.
# Cách dùng:  python tim_shopee.py "tai nghe bluetooth" "kệ dán tường"
# Lần đầu: cửa sổ Chrome mở ra -> tự đăng nhập Shopee bằng tay (và tự giải captcha nếu có).
# Session lưu trong thư mục shopee_profile, lần sau không cần đăng nhập lại.
import csv, random, sys, time
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROFILE = "shopee_profile"
OUT = "ket_qua_shopee.csv"
WAIT_MS = 180_000  # chờ tối đa 3 phút (đủ để đăng nhập/giải captcha tay)


def parse(data, keyword):
    rows = []
    for it in data.get("items") or []:
        b = it.get("item_basic") or it
        if not b.get("itemid"):
            continue
        rows.append({
            "tu_khoa": keyword,
            "ten": b.get("name", ""),
            "gia": (b.get("price") or 0) // 100000,  # Shopee lưu giá x100000
            "da_ban": b.get("historical_sold") or b.get("sold") or 0,
            "sao": round((b.get("item_rating") or {}).get("rating_star") or 0, 1),
            "link": f"https://shopee.vn/product/{b['shopid']}/{b['itemid']}",
            "anh": f"https://down-vn.img.susercontent.com/file/{b.get('image', '')}",
        })
    return rows


def search(page, keyword):
    got = []

    def on_resp(r):
        if "/api/v4/search/search_items" not in r.url:
            return
        try:
            data = r.json()  # đọc ngay, trước khi trang chuyển đi mất body
        except Exception:
            return
        if data.get("items"):
            got.append(data)
        else:  # Shopee trả lỗi/chặn: in ra để biết lý do
            print("  Shopee trả về không có sản phẩm:", str(data)[:200])

    page.on("response", on_resp)
    try:
        page.goto(f"https://shopee.vn/search?keyword={quote(keyword)}")
        deadline = time.time() + WAIT_MS / 1000
        while not got and time.time() < deadline:
            page.wait_for_timeout(1000)  # trong lúc này bạn đăng nhập/giải captcha tay
    finally:
        page.remove_listener("response", on_resp)
    if not got:
        raise PWTimeout("no search data")
    return parse(got[0], keyword)


def main(keywords):
    rows = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False, channel="chrome", viewport=None, locale="vi-VN")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for kw in keywords:
            print(f"Đang tìm: {kw} ...")
            try:
                found = search(page, kw)
            except PWTimeout:
                print("  Hết giờ chờ. Đăng nhập/giải captcha trong cửa sổ rồi chạy lại.")
                continue
            print(f"  -> {len(found)} sản phẩm")
            rows += found
            time.sleep(random.uniform(5, 10))  # chạy chậm để đỡ bị chặn
        ctx.close()

    if rows:
        with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        print(f"Đã lưu {len(rows)} dòng vào {OUT}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Cách dùng: python tim_shopee.py "từ khóa 1" "từ khóa 2"')
    main(sys.argv[1:])
