"""Tạo 10 bài slide (PDF 1080x1920) từ mẫu. Sửa nội dung trong POSTS rồi chạy: python tao_slide.py"""
import html, os, shutil, subprocess, sys, tempfile
from pathlib import Path


def find_browser():
    """Chrome hoặc Edge (Windows/macOS/Linux) để xuất PDF."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    found = [p for p in candidates if os.path.isfile(p)]
    found += filter(None, map(shutil.which, ["google-chrome", "chromium", "chromium-browser", "microsoft-edge"]))
    if not found:
        sys.exit("Không tìm thấy Chrome hoặc Edge. Cài Google Chrome rồi chạy lại.")
    return found[0]


CHROME = find_browser()
OUT = Path(__file__).parent / "10_bai"
CHANNEL = "@tienichhangngay"

# tag, tiêu đề bìa (*chữ cam*), [(tên, mô tả, giá/nhãn hoặc None)], tiêu đề chốt, dòng phụ chốt
POSTS = [
    ("phong_tro", "PHÒNG TRỌ 🏠", "5 món dưới *100K* tiện gấp đôi", [
        ("Kệ dán tường", "Không khoan tường, không mất cọc", "~50K"),
        ("Đèn LED cảm biến", "Tối đi vệ sinh khỏi mò công tắc", "~60K"),
        ("Móc treo đa tầng", "Tủ nhỏ treo được gấp đôi", "~45K"),
        ("Thùng rác mini có nắp", "Gọn, kín mùi, để bàn được", "~70K"),
        ("Ổ cắm có cổng USB", "Sạc cùng lúc 3–4 thiết bị", "~90K"),
    ], "Món nào bạn cần nhất? 👇", "Lưu lại để mua dần 📌"),
    ("bep_luoi", "NHÀ BẾP 🍳", "Lười nấu ăn? *5 món* này cứu bạn", [
        ("Máy xay tỏi kéo tay", "Băm tỏi 10 giây, không hôi tay", None),
        ("Dụng cụ bào rau", "Thái, bào, cắt hạt lựu một bộ", None),
        ("Kéo nhà bếp đa năng", "Cắt gà, cắt rau, mở nắp chai", None),
        ("Chảo chống dính nhỏ", "Chiên trứng không dính, rửa nhanh", None),
        ("Hộp chia ngăn", "Nấu một lần, ăn cả tuần", None),
    ], "Bếp nhỏ vẫn nấu ngon 😋", "Link đủ 5 món ở giỏ hàng"),
    ("don_nha", "DỌN NHÀ 🧽", "Dọn nhà nhanh *gấp đôi* với 4 món này", [
        ("Bàn chải điện vệ sinh", "Chà ron gạch, bồn rửa không mỏi tay", None),
        ("Cây lau nhà tự vắt", "Không đụng tay vào nước bẩn", None),
        ("Chổi cao su", "Quét sạch tóc rụng trên sàn, thảm", None),
        ("Khăn microfiber", "Lau kính, lau bếp không để vệt", None),
    ], "Cuối tuần dọn 30 phút là xong ✨", "Lưu lại để mua dần 📌"),
    ("tu_do_truoc_sau", "TỦ ĐỒ 👕", "Tủ đồ của mình: trước 😩 và *sau* 😍", [
        ("Trước", "Nhét đâu rơi đó", None),
        ("Hộp vải chia ngăn", "Gấp đồ dựng đứng, nhìn là thấy", None),
        ("Móc treo đa tầng", "Một móc treo 5 áo", None),
        ("Túi hút chân không", "Chăn mền mùa đông gọn hẳn", None),
        ("Sau", "Gọn gàng, dễ lấy", None),
    ], "Tủ nhỏ cũng gọn được nè", "Combo sắp tủ ở giỏ hàng 👇"),
    ("mon_nho", "ĐỒ TIỆN ÍCH ✨", "Mua xong mới thấy: sao không mua *sớm hơn* 😭", [
        ("Kẹp miệng túi", "Bánh, snack mở ra không bị ỉu", None),
        ("Lót chống trượt thớt", "Thái đồ không lo thớt trượt", None),
        ("Đồ gỡ tóc", "Hết cảnh tóc kẹt đầy lược", None),
        ("Giá đỡ điện thoại", "Coi phim, gọi video rảnh tay", None),
        ("Băng keo chống thấm", "Rỉ nước? Xử lý tạm trong 1 phút", None),
    ], "Bạn đã có món nào rồi? 👇", "Link ở giỏ hàng"),
    ("theo_muc_gia", "NGÂN SÁCH 💸", "Có *50K, 100K, 200K* thì mua gì cho nhà?", [
        ("Kệ dán tường", "Gọn nhà tắm ngay", "50K"),
        ("Đèn cảm biến + móc treo", "Tối sáng, tủ gọn", "100K"),
        ("Bàn chải điện vệ sinh", "Dọn nhà nhẹ cả tuần", "200K"),
    ], "Bạn chọn mức nào?", "Comment 50, 100 hay 200 👇"),
    ("qua_tang", "QUÀ TẶNG 🎁", "Quà tặng dưới *150K* mà ai cũng xài", [
        ("Bình giữ nhiệt", "Hợp tặng đồng nghiệp, thầy cô", None),
        ("Đèn ngủ cảm ứng", "Tặng bạn ở trọ, sinh viên", None),
        ("Bộ hộp đựng đồ ăn", "Tặng mẹ, tặng người hay nấu", None),
        ("Quạt mini cầm tay", "Tặng bạn hay đi ngoài đường", None),
    ], "Lưu lại cho dịp lễ Tết 📌", "Link ở giỏ hàng"),
    ("sai_lam", "MẸO MUA SẮM ⚠️", "*3 sai lầm* khi mua đồ gia dụng online", [
        ("1. Chỉ nhìn giá rẻ", "Chọn shop từ 4.8⭐, nhiều lượt bán", None),
        ("2. Bỏ qua ảnh thật", "Xem ảnh khách chụp, đừng chỉ xem ảnh shop", None),
        ("3. Không đo kích thước", "Đo chỗ đặt trước khi mua kệ, tủ", None),
        ("Mấy món mình đã lọc kỹ", "Shop uy tín, đánh giá tốt", None),
    ], "Mua đúng ngay từ đầu ✅", "Link các món uy tín ở giỏ hàng"),
    ("phong_tam", "PHÒNG TẮM 🛁", "Phòng tắm nhỏ – gọn như *khách sạn*", [
        ("Kệ góc dán tường", "Tận dụng góc chết", None),
        ("Hộp nhấn kem đánh răng", "Gọn bồn rửa, đỡ phí kem", None),
        ("Móc dán treo khăn", "Không khoan, chịu lực tốt", None),
        ("Thảm chống trơn", "An toàn cho người già, trẻ nhỏ", None),
    ], "Phòng tắm nhỏ vẫn xịn 😍", "Combo phòng tắm ở giỏ hàng 👇"),
    ("top_ban_chay", "BÁN CHẠY 🔥", "Top 5 đồ gia dụng *bán chạy* tháng này", [
        (f"Tên món {i}", "Một dòng nói công dụng", "Đã bán ?+") for i in range(1, 6)
    ], "Món nào đáng mua nhất? 👇", "Follow để xem top tháng sau 📈"),
]

CSS = """
@page { size: 1080px 1920px; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
.page { position: relative; width: 1080px; height: 1920px; overflow: hidden; background: #FFF8EE;
        color: #1F2933; font-family: "Be Vietnam Pro", sans-serif; page-break-after: always; }
.abs { position: absolute; }
.h1 { font-family: Montserrat, sans-serif; font-weight: 900; text-transform: uppercase; line-height: 1.05; }
.accent { color: #FF6B35; }
.tag { background: #FF6B35; color: #fff; font-weight: 700; border-radius: 999px; }
.photo { background: #fff; border-radius: 40px; box-shadow: 0 20px 50px rgba(31,41,51,.12); display: flex;
         align-items: center; justify-content: center; color: #9AA5B1; font-size: 44px; font-weight: 700; text-align: center; }
.channel { left: 60px; top: 110px; font-size: 32px; opacity: .6; }
"""


def esc(s):
    return html.escape(s)


def title_html(s):
    parts = esc(s).split("*")  # đoạn lẻ nằm giữa hai dấu * -> tô cam
    return "".join(f'<span class="accent">{p}</span>' if i % 2 else p for i, p in enumerate(parts))


def fit(text, big, mid, small):
    n = len(text.replace("*", ""))
    return big if n <= 26 else mid if n <= 36 else small


def build(tag, cover, items, cta, cta_sub, imgs=()):
    """imgs: danh sách đường dẫn ảnh theo thứ tự món; thiếu ảnh thì để ô trống như cũ."""
    def ph(i, label):
        if 0 <= i < len(imgs) and imgs[i]:
            return f'<img src="{Path(imgs[i]).resolve().as_uri()}" style="width:100%; height:100%; object-fit:contain; border-radius:inherit;">'
        return label
    ch = f'<div class="abs channel">{esc(CHANNEL)}</div>'
    pages = [f"""<section class="page">{ch}
  <div class="abs tag" style="left:60px; top:220px; padding:18px 40px; font-size:44px;">{esc(tag)}</div>
  <div class="abs h1" style="left:60px; top:340px; width:900px; font-size:{fit(cover, 130, 110, 92)}px;">{title_html(cover)}</div>
  <div class="abs" style="left:240px; top:880px; width:680px; height:680px; border-radius:50%; background:#FF6B35; opacity:.15;"></div>
  <div class="abs photo" style="left:100px; top:900px; width:460px; height:460px; transform:rotate(-4deg);">{ph(0, "ẢNH<br>SẢN PHẨM")}</div>
  <div class="abs photo" style="left:500px; top:980px; width:420px; height:420px; transform:rotate(5deg);">{ph(min(1, len(imgs) - 1), "ẢNH<br>SẢN PHẨM")}</div>
  <div class="abs" style="left:60px; top:1430px; font-size:44px; font-weight:500; color:#2EC4B6;">Lướt xem →</div>
</section>"""]
    for i, (name, desc, price) in enumerate(items, 1):
        price_html = (f'<div class="tag" style="padding:14px 40px; border-radius:24px; font-family:Montserrat, sans-serif; '
                      f'font-weight:800; font-size:{72 if len(price) <= 5 else 52}px; white-space:nowrap;">{esc(price)}</div>') if price else ""
        pages.append(f"""<section class="page">{ch}
  <div class="abs h1 accent" style="left:60px; top:170px; font-size:90px;">{i:02d}</div>
  <div class="abs photo" style="left:80px; top:300px; width:920px; height:880px;">{ph(i - 1, "ẢNH SẢN PHẨM")}</div>
  <div class="abs" style="left:60px; top:1220px; width:960px; display:flex; justify-content:space-between; align-items:flex-end; gap:30px;">
    <div><div style="font-size:{76 if len(name) <= 20 else 64}px; font-weight:700; line-height:1.15;">{esc(name)}</div>
         <div style="margin-top:16px; font-size:48px; font-weight:500; line-height:1.3;">{esc(desc)}</div></div>
    {price_html}
  </div>
</section>""")
    thumbs = "".join(f'<div class="photo" style="height:240px; font-size:32px;">{ph(i - 1, f"Ảnh {i}")}</div>' for i in range(1, min(len(items), 6) + 1))
    pages.append(f"""<section class="page">{ch}
  <div class="abs h1" style="left:60px; top:260px; width:900px; font-size:{fit(cta, 110, 96, 84)}px;">{title_html(cta)}</div>
  <div class="abs" style="left:60px; top:680px; width:880px; display:grid; grid-template-columns:repeat(3,1fr); gap:30px;">{thumbs}</div>
  <div class="abs tag" style="left:60px; top:1250px; width:880px; padding:34px 0; text-align:center; font-family:Montserrat, sans-serif; font-weight:800; font-size:60px;">🛒 LINK Ở GIỎ HÀNG</div>
  <div class="abs" style="left:60px; top:1420px; width:880px; text-align:center; font-size:44px; font-weight:500; color:#2EC4B6;">{esc(cta_sub)}</div>
</section>""")
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Be+Vietnam+Pro:wght@500;700&display=block" rel="stylesheet">
<style>{CSS}</style></head><body>{''.join(pages)}</body></html>""", len(pages)


def render(html_text, pdf, png=None, n=1):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_text)
    url = Path(f.name).as_uri()
    base = [CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=8000"]
    subprocess.run(base + ["--no-pdf-header-footer", f"--print-to-pdf={pdf}", url], capture_output=True)
    if png:
        subprocess.run(base + ["--hide-scrollbars", "--force-device-scale-factor=1",
                               f"--window-size=1080,{1920 * n}", f"--screenshot={png}", url], capture_output=True)
    os.unlink(f.name)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for k, (slug, *post) in enumerate(POSTS, 1):
        doc, n = build(*post)
        pdf = OUT / f"bai_{k:02d}_{slug}.pdf"
        pdf.unlink(missing_ok=True)
        render(doc, pdf)
        print(f"{pdf.name}  ({n} trang)" if pdf.exists() else f"LỖI: không tạo được {pdf.name}")
    print(f"\nXong. File nằm trong thư mục: {OUT}")
