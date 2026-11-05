"""Link sản phẩm -> lấy ảnh -> chèn vào mẫu slide -> video MP4 1080x1920.
Sửa san_pham.txt rồi chạy: python tao_video.py"""
import hashlib, html, json, random, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

import tao_slide as T

HERE = Path(__file__).parent
OUT = HERE / "video"
_env = HERE / ".env"
ENV = dict(l.split("=", 1) for l in _env.read_text("utf-8-sig").splitlines()
           if "=" in l and not l.lstrip().startswith("#")) if _env.exists() else {}
APP_ID, SECRET = ENV.get("SHOPEE_APP_ID", "").strip(), ENV.get("SHOPEE_SECRET", "").strip()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
GIAY_MOI_TRANG, GIAY_CHUYEN = 3.0, 0.5
GIAY_VIDEO = 5.0  # trang có video sản phẩm: lấy 5 giây đầu của video
DUOI_VIDEO = (".mp4", ".webm", ".mov", ".mkv", ".m4v")
FPS = 30
# hiệu ứng chuyển trang của ffmpeg xfade, mỗi lần chuyển bốc ngẫu nhiên 1 cái; xóa bớt cái không thích
HIEU_UNG = ["slideleft", "slideup", "smoothleft", "smoothup", "fade", "fadewhite", "circleopen", "circlecrop",
            "radial", "wipeleft", "vertopen", "horzopen", "zoomin", "dissolve", "pixelize", "squeezeh", "diagtl", "hlslice"]
TIEN_DO = None  # giao diện gán hàm f(0..1) để nhận % xuất video


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "vi,en;q=0.8"})
    for lan in range(3):  # mạng chập chờn (lỗi DNS) thì thử lại
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except urllib.error.URLError as e:
            if lan == 2 or isinstance(e, urllib.error.HTTPError):
                raise
            time.sleep(2)


def shop_ids(s):
    """(shopId, itemId) từ link Shopee, link rút gọn thì mở ra trước."""
    m = re.search(r"i\.(\d+)\.(\d+)|/product/(\d+)/(\d+)", s)
    if not m and s.startswith("http"):
        try:
            with urllib.request.urlopen(urllib.request.Request(s, headers={"User-Agent": UA}), timeout=20) as r:
                m = re.search(r"i\.(\d+)\.(\d+)|/product/(\d+)/(\d+)", r.geturl())
        except Exception:
            pass
    return m and tuple(x for x in m.groups() if x)


def shopee(s):
    """Tra Shopee Affiliate Open API theo link hoặc tên món -> dict sản phẩm (bán chạy nhất trong 5 kết quả) hoặc None."""
    if not (APP_ID and SECRET):
        return None
    ids = shop_ids(s)
    if s.startswith("http") and not ids:
        return None
    args = f"shopId:{ids[0]}, itemId:{ids[1]}" if ids else f"keyword:{json.dumps(s, ensure_ascii=False)}, sortType:1"
    q = ("{productOfferV2(%s, page:1, limit:5){nodes{productName imageUrl priceMin sales ratingStar shopName offerLink}}}" % args)
    payload = json.dumps({"query": q}, ensure_ascii=False)
    ts = str(int(time.time()))
    sig = hashlib.sha256((APP_ID + ts + payload + SECRET).encode()).hexdigest()
    req = urllib.request.Request("https://open-api.affiliate.shopee.vn/graphql", payload.encode(), {
        "Content-Type": "application/json", "Authorization": f"SHA256 Credential={APP_ID}, Timestamp={ts}, Signature={sig}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except Exception as e:
        print(f"   API lỗi: {e}")
        return None
    if data.get("errors"):
        print(f"   API lỗi: {data['errors'][0].get('message')}")
        return None
    nodes = (data.get("data") or {}).get("productOfferV2", {}).get("nodes") or []
    return max(nodes, key=lambda n: int(n.get("sales") or 0)) if nodes else None


TIKI_CHAN = False


def tiki(name):
    """Dự phòng khi chưa có Shopee API: tìm tên món trên Tiki (JSON công khai của web Tiki), lấy ảnh món bán chạy nhất trong 5 kết quả.
    Chỉ lấy ảnh minh họa, không lấy giá/lượt bán vì đó là số của Tiki, không phải món trong giỏ hàng của bạn."""
    global TIKI_CHAN
    if TIKI_CHAN:
        return None
    try:
        data = json.loads(get("https://tiki.vn/api/v2/products?limit=5&q=" + urllib.parse.quote(name)))["data"]
    except json.JSONDecodeError:  # Tiki trả trang kiểm tra chống bot -> ngưng hỏi Tiki trong lần chạy này
        TIKI_CHAN = True
        print("   Tiki đang tạm chặn vì tìm nhiều. Chờ 15-30 phút rồi chạy lại, ảnh đã có sẽ được giữ.")
        return None
    except Exception as e:
        print(f"   Tiki lỗi: {e}")
        return None
    best = max(data, key=lambda p: (p.get("quantity_sold") or {}).get("value") or 0, default=None)
    return best and re.sub(r"/cache/\d+x\d+/", "/cache/750x750/", best.get("thumbnail_url") or "") or None


def gia_k(v):
    v = float(v or 0)
    return "" if not v else f"{v / 1e6:.1f}tr".replace(".0tr", "tr") if v >= 1e6 else f"{round(v / 1000)}K"


def meta(page, *keys):
    for k in keys:
        m = (re.search(rf'<meta[^>]+(?:property|name)=["\']{k}["\'][^>]+content=["\']([^"\']+)', page, re.I)
             or re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{k}["\']', page, re.I))
        if m:
            return html.unescape(m.group(1)).strip()
    return None


def info(url):
    """(tên, link ảnh) từ trang sản phẩm. Thử tải thường, không được thì nhờ Chrome mở trang (trang chạy JS)."""
    def plain():
        try:
            return get(url).decode("utf-8", "ignore")
        except Exception as e:
            print(f"   tải thường lỗi: {e}")
            return ""

    def chrome():
        with tempfile.TemporaryDirectory() as prof:
            try:
                return subprocess.run([T.CHROME, "--headless=new", "--disable-gpu", f"--user-agent={UA}",
                                       f"--user-data-dir={prof}", "--virtual-time-budget=8000", "--dump-dom", url],
                                      capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=40).stdout
            except subprocess.TimeoutExpired:
                print("   Chrome mở trang quá lâu, bỏ qua")
                return ""

    name = img = None
    for get_page in (plain, chrome):  # chỉ mở Chrome khi tải thường không đủ
        p = get_page()
        img = meta(p, "og:image", "twitter:image")
        if not img:  # JSON-LD của trang sản phẩm
            m = re.search(r'"image"\s*:\s*\[?\s*"(https?:[^"]+)"', p)
            img = m and m.group(1).replace("\\/", "/")
        if img:  # trang không có ảnh thường là trang chặn/captcha -> tên trên đó cũng vô nghĩa
            name = meta(p, "og:title", "twitter:title")
            break
    return name, img


def parse(path):
    """Mỗi khối (cách nhau dòng trống) = 1 video. Dòng đầu: tiêu đề bìa. Các dòng sau: link | tên | mô tả | giá"""
    blocks = [b for b in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig")) if b.strip()]
    for b in blocks:
        lines = [l.strip() for l in b.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        if len(lines) < 2:
            continue
        yield lines[0], [[*(x.strip() for x in l.split("|")), "", "", ""][:4] for l in lines[1:]]


def make_video(png, n, mp4, nhac, clips=None):
    """clips: {số trang: file video sản phẩm} -> trang đó phát video trong khung ảnh (tắt tiếng gốc) thay cho zoom."""
    clips, t = clips or {}, GIAY_CHUYEN
    dur = [GIAY_VIDEO if i in clips else GIAY_MOI_TRANG for i in range(n)]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(png)]
    f = [f"[0]split={n}" + "".join(f"[s{i}]" for i in range(n))]
    for i in range(n):
        k = int(dur[i] * FPS)
        # trang có video: nền đứng yên; trang ảnh: zoom chậm cho đỡ tĩnh, ngẫu nhiên phóng to hoặc thu nhỏ
        z = "1" if i in clips else random.choice([f"1+0.06*on/{k}", f"1.06-0.06*on/{k}"])
        f.append(f"[s{i}]crop=1080:1920:0:{1920 * i},scale=2160:3840,"
                 f"zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':"
                 f"d={k}:s=1080x1920:fps={FPS},setsar=1,format=yuv420p[{'b' if i in clips else 'v'}{i}]")
        if i in clips:  # thu video vừa khung ảnh 920x880 ở (80,300) như mẫu slide, đặt giữa khung
            cmd += ["-t", f"{dur[i]}", "-i", str(clips[i])]
            vi = cmd.count("-i") - 1  # số thứ tự input vừa thêm
            f.append(f"[{vi}:v]fps={FPS},scale=920:880:force_original_aspect_ratio=decrease,setsar=1,"
                     f"tpad=stop_mode=clone:stop_duration={dur[i]}[c{i}];"
                     f"[b{i}][c{i}]overlay=x=80+(920-w)/2:y=300+(880-h)/2:shortest=0:eof_action=repeat,"
                     f"trim=duration={dur[i]},format=yuv420p[v{i}]")
    last, at = "v0", 0.0
    hu = random.sample(HIEU_UNG, len(HIEU_UNG))  # xáo trộn: các lần chuyển trong 1 video không lặp nhau
    for i in range(1, n):
        at += dur[i - 1] - t
        f.append(f"[{last}][v{i}]xfade=transition={hu[(i - 1) % len(hu)]}:duration={t}:offset={at:.2f}[x{i}]")
        last = f"x{i}"
    total = sum(dur) - (n - 1) * t
    if nhac:
        ai = cmd.count("-i")
        cmd += ["-stream_loop", "-1", "-i", str(nhac)]
        f.append(f"[{ai}:a]afade=t=out:st={total - 1:.2f}:d=1[a]")
    cmd += ["-filter_complex", ";".join(f), "-map", f"[{last}]"]
    if nhac:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-t", f"{total:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart",
            "-progress", "pipe:1", str(mp4)]
    r = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in r.stdout:  # ffmpeg báo "out_time_us=..." liên tục -> % cho thanh tiến độ của giao diện
        if line.startswith("out_time_us=") and TIEN_DO and line[12:].strip().isdigit():
            TIEN_DO(min(1.0, int(line[12:]) / 1e6 / total))
    if r.wait():
        print(r.stderr.read()[-1500:])


def ds_nhac():
    """nhac.mp3 ở thư mục chính thì luôn dùng bài đó; không có thì các bài trong thư mục nhac"""
    return list(HERE.glob("nhac.*")) or [f for f in (HERE / "nhac").glob("*") if f.suffix.lower() in (".mp3", ".m4a", ".wav")]


def tao(cover, rows, folder, nhac=None):
    """1 video: rows = [[link, tên, mô tả, giá], ...] -> folder/video.mp4 (None nếu lỗi)."""
    (folder / "anh").mkdir(parents=True, exist_ok=True)
    items, imgs, aff, clips = [], [], [], {}
    # ảnh tự tải về để nguyên tên (không phải 1.jpg / 1_tay.jpg) -> gắn theo thứ tự thời gian tải: cũ nhất = món 1
    loose = sorted((f for f in (folder / "anh").iterdir() if not re.fullmatch(r"\d+(_tay|_poster)?\.\w+", f.name)),
                   key=lambda f: f.stat().st_mtime)
    for j, (link, ten, mota, gia) in enumerate(rows, 1):
        own = next((folder / "anh").glob(f"{j}_tay.*"), None) or (loose[j - 1] if j <= len(loose) else None)
        p = shopee(link)
        if p:
            name, img_url = p.get("productName"), p.get("imageUrl")
            gia = gia or gia_k(p.get("priceMin"))
            mota = mota or f"⭐ {float(p.get('ratingStar') or 0):.1f} · Đã bán {p.get('sales') or 0}"
            aff.append(f"{j}. {name}\n   {p.get('offerLink')}")
        else:
            name, img_url = info(link) if link.startswith("http") and not (own and ten) else (None, None)
        if not link.startswith("http"):
            ten = ten or link  # dòng là tên món -> giữ tên ngắn bạn gõ
            cached = folder / "anh" / f"{j}.jpg"
            if cached.exists() and not img_url:  # ảnh Tiki đã tải lần trước -> dùng lại (đổi món thì xóa thư mục anh)
                own = own or cached
            elif not (img_url or own):
                time.sleep(1.5)  # ponytail: nghỉ cố định cho Tiki đỡ chặn; chặn nữa thì tăng lên
                img_url = tiki(link)
        file = own
        if not file and img_url:
            try:
                file = folder / "anh" / f"{j}.jpg"
                file.write_bytes(get(img_url))
            except Exception as e:
                print(f"   tải ảnh lỗi: {e}")
                file = None
        if file and file.suffix.lower() in DUOI_VIDEO:
            # video sản phẩm: slide dùng 1 khung hình làm ảnh (bìa, trang chốt), lúc xuất video thì phát video đè lên khung
            poster = folder / "anh" / f"{j}_poster.jpg"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(file), "-frames:v", "1", str(poster)])
            if poster.exists():
                clips[j], file = file, poster
            else:
                print(f"   video món {j} hỏng, bỏ qua")
                file = None
        # bỏ đuôi "| Shopee Việt Nam" và cụm quảng cáo đầu tên như "[FREE SHIP]"
        ten = ten or re.sub(r"^\s*(?:[\[(【][^\])】]*[\])】]\s*)+", "", (name or f"Món {j}").split(" | ")[0]).capitalize()[:40]
        print(f"   {j}. {ten}  ->  {'có VIDEO' if j in clips else 'có ảnh' if file else 'KHÔNG lấy được ảnh (bỏ ảnh vào anh/' + str(j) + '_tay.jpg rồi chạy lại)'}")
        items.append((ten, mota, gia or None))
        imgs.append(file)
    doc, n = T.build("SẢN PHẨM", cover, items, "Món nào bạn thích nhất? 👇", "Link ở giỏ hàng", imgs)
    if aff:
        (folder / "link_gio_hang.txt").write_text("\n".join(aff), encoding="utf-8")
    png = folder / "slide.png"
    T.render(doc, folder / "slide.pdf", png, n)
    mp4 = folder / "video.mp4"
    if nhac:  # nhạc Kevin MacLeod là CC-BY: phải ghi nguồn khi đăng -> để sẵn dòng copy
        print(f"   nhạc: {nhac.stem}")
        (folder / "ghi_nguon_nhac.txt").write_text(
            f'Music: "{nhac.stem}" by Kevin MacLeod (incompetech.com), CC BY 4.0', encoding="utf-8")
    make_video(png, n, mp4, nhac, clips)  # món j nằm ở trang j (trang 0 là bìa)
    print(f"   => {mp4}" if mp4.exists() else "   LỖI: không tạo được video")
    return mp4 if mp4.exists() else None


if __name__ == "__main__":
    src = HERE / "san_pham.txt"
    if not src.exists():
        sys.exit("Chưa có san_pham.txt (xem HUONG_DAN.txt).")
    nhacs = ds_nhac()
    if not (APP_ID and SECRET):
        print("Chưa có khóa Shopee API trong file .env -> dòng ghi tên món lấy ảnh minh họa từ Tiki, giá tự gõ.")
    for k, (cover, rows) in enumerate(parse(src), 1):
        print(f"\n[{k}] {cover}")
        tao(cover, rows, OUT / f"video_{k:02d}", random.choice(nhacs) if nhacs else None)
    print(f"\nXong. Video nằm trong: {OUT}")
