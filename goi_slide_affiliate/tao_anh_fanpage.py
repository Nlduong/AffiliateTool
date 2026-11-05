"""Ảnh đại diện (720x720) + ảnh bìa (1640x624) cho Fanpage, cùng màu/phông với slide.
Đổi TEN / SLOGAN rồi chạy: python tao_anh_fanpage.py  -> thư mục fanpage\\"""
import subprocess, tempfile
from pathlib import Path

import tao_slide as T

TEN = ("TIỆN ÍCH", "HẰNG NGÀY")  # 2 dòng tên Trang
SLOGAN = ("Đồ gia dụng *tiện ích*", "giá rẻ, dùng sướng")  # 2 dòng tiêu đề ảnh bìa
PHU = "Review thật · Mỗi ngày 1 món hay · Link mua ở bình luận 👇"
OUT = Path(__file__).parent / "fanpage"

FONT = ('<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Be+Vietnam+Pro:wght@500;700'
        '&display=block" rel="stylesheet">')
BASE = """* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Be Vietnam Pro",sans-serif; color:#1F2933; overflow:hidden; }
.h { font-family:Montserrat,sans-serif; font-weight:900; text-transform:uppercase; line-height:1.02; }
.cam, .accent { color:#FF6B35; }"""

# ngôi nhà + tia sáng: vẽ bằng SVG cho nét, không phụ thuộc phông emoji
NHA = """<svg viewBox="0 0 100 100" width="{w}" height="{w}"><g fill="none" stroke="{c}" stroke-width="7"
 stroke-linecap="round" stroke-linejoin="round"><path d="M16 48 L50 18 L84 48"/><path d="M26 42 V82 H74 V42"/>
 <path d="M43 82 V62 H57 V82"/></g><g stroke="{s}" stroke-width="5" stroke-linecap="round">
 <path d="M86 14 V24"/><path d="M81 19 H91"/></g></svg>"""

AVATAR = f"""<style>{BASE}
body {{ width:720px; height:720px; background:#FF6B35; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.c {{ width:600px; height:600px; border-radius:50%; background:#FFF8EE; display:flex; flex-direction:column;
      align-items:center; justify-content:center; gap:6px; }}
</style><div class="c">{NHA.format(w=230, c="#FF6B35", s="#2EC4B6")}
<div class="h" style="font-size:78px; text-align:center;">{TEN[0]}</div>
<div class="h cam" style="font-size:60px; text-align:center;">{TEN[1]}</div></div>"""

THE = [("🧺", -6), ("💡", 4), ("🔌", -3), ("🍳", 5), ("🧽", -4), ("🛁", 3)]  # món + độ nghiêng
the = lambda i, x, y, s: (f'<div class="t" style="left:{x}px; top:{y}px; width:{s}px; height:{s}px; font-size:{s * .5:.0f}px; '
                          f'transform:rotate({THE[i][1]}deg);">{THE[i][0]}</div>')
BIA = f"""<style>{BASE}
body {{ width:1640px; height:624px; background:#FFF8EE; position:relative; }}
.t {{ position:absolute; background:#fff; border-radius:36px; box-shadow:0 18px 40px rgba(31,41,51,.12);
      display:flex; align-items:center; justify-content:center; }}
.blob {{ position:absolute; border-radius:50%; background:#FF6B35; opacity:.13; }}
</style>
<div class="blob" style="left:-120px; top:-160px; width:520px; height:520px;"></div>
<div class="blob" style="right:-140px; bottom:-200px; width:560px; height:560px; background:#2EC4B6; opacity:.15;"></div>
{the(0, 70, 70, 190)}{the(1, 120, 330, 170)}{the(2, 1380, 60, 180)}{the(3, 1420, 320, 190)}{the(4, 1240, 400, 130)}{the(5, 300, 440, 120)}
<div style="position:absolute; left:330px; right:330px; top:140px; text-align:center;">
  <div style="display:inline-block; background:#FF6B35; color:#fff; font-weight:700; font-size:30px; padding:10px 30px;
       border-radius:999px;">{TEN[0].title()} {TEN[1].title()}</div>
  <div class="h" style="font-size:76px; margin-top:28px;">{T.title_html(SLOGAN[0])}<br>{T.title_html(SLOGAN[1])}</div>
  <div style="font-size:32px; font-weight:500; margin-top:26px; color:#2EC4B6;">{T.esc(PHU)}</div>
</div>"""


def chup(html, png, w, h):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(f'<!doctype html><html lang="vi"><head><meta charset="utf-8">{FONT}</head><body>{html}</body></html>')
    subprocess.run([T.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--virtual-time-budget=8000", f"--window-size={w},{h}", f"--screenshot={png}", Path(f.name).as_uri()],
                   capture_output=True)
    Path(f.name).unlink()


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    chup(AVATAR, OUT / "anh_dai_dien.png", 720, 720)
    chup(BIA, OUT / "anh_bia.png", 1640, 624)
    print(f"Xong: {OUT}")
