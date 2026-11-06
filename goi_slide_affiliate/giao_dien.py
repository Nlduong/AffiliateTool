"""Giao diện làm video từng bước: 1) chọn sản phẩm từ file CSV "Lấy link hàng loạt"  2) sửa chữ + gắn ảnh
3) chọn nhạc, tạo video.  Tab Cài đặt: khóa Shopee API.   Chạy: python giao_dien.py (hoặc Giao_dien.bat)"""
import csv, glob, json, os, queue, random, re, shutil, sqlite3, subprocess, sys, tempfile, threading, time, webbrowser
import urllib.error, urllib.request
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import tao_slide as T
import tao_video as V

HERE = Path(__file__).parent
EXCEL = HERE / "excel"


def so(s):
    """'1k+' -> 1000, '156,0k' -> 156000, '₫18.720' -> 18720"""
    s = str(s).replace("₫", "").replace("+", "").replace(".", "").replace(",", ".").strip().lower()
    try:
        return float(s.rstrip("k") or 0) * (1000 if s.endswith("k") else 1)
    except ValueError:
        return 0


def doc_csv(files):
    """Gộp các file CSV (trùng mã thì lấy dòng file sau), xếp theo lượt bán x hoa hồng/đơn."""
    rows = {}
    for f in files:
        with open(f, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                rows[r["Mã sản phẩm"]] = r
    for r in rows.values():
        r["_ban"], r["_gia"], r["_hh"] = so(r["Doanh thu"]), so(r["Giá"]), so(r["Hoa hồng"])
    return sorted(rows.values(), key=lambda r: r["_ban"] * r["_hh"], reverse=True)


DUOI_ANH = (".jpg", ".jpeg", ".jfif", ".png", ".webp", ".avif")
GEMINI_MAC_DINH = "gemini-flash-latest"  # Google đổi tên model thì sửa ở tab Cài đặt, không cần sửa code
GEMINI_DU_PHONG = "gemini-flash-lite-latest"  # tên "latest" Google tự trỏ sang bản mới, ít khi bị ngừng
_LS_CACHE = {}  # file History -> (lần sửa cuối, danh sách file đã tải)


def file_vua_tai(tu_luc):
    """File (đường dẫn thật) đã tải xong sau mốc tu_luc, dù người dùng lưu ở thư mục nào.
    Đọc lịch sử tải của mọi trình duyệt nhân Chrome: Chrome (mọi profile), Cốc Cốc, Edge, Brave... (Firefox không có)."""
    moc = int((tu_luc + 11644473600) * 1e6)  # giờ Unix -> giờ Chrome (micro giây tính từ năm 1601)
    ra = []
    for h in glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\*\*\User Data\*\History")):
        try:
            sua = os.path.getmtime(h)
            if _LS_CACHE.get(h, (None,))[0] != sua:  # chỉ đọc lại khi trình duyệt vừa ghi lịch sử
                tam = Path(tempfile.gettempdir()) / f"_ls_tai_{abs(hash(h))}.db"
                shutil.copy2(h, tam)  # trình duyệt đang mở thì khóa file gốc -> đọc bản sao
                db = sqlite3.connect(tam)
                try:
                    rows = db.execute("SELECT target_path, end_time FROM downloads WHERE state=1").fetchall()
                finally:
                    db.close()  # phải đóng hẳn thì Windows mới cho xóa bản sao
                tam.unlink(missing_ok=True)
                _LS_CACHE[h] = (sua, rows)
            ra += [Path(p) for p, t in _LS_CACHE[h][1] if t > moc and p]
        except (OSError, sqlite3.Error):
            pass
    return ra


def thu_muc_tai():
    """Thư mục Downloads + thư mục tải mặc định đang đặt trong Chrome/Edge (nếu đã đổi sang chỗ khác)."""
    ds = {Path.home() / "Downloads"}
    for app in (r"Google\Chrome", r"Microsoft\Edge"):
        pref = Path(os.path.expandvars(rf"%LOCALAPPDATA%\{app}\User Data\Default\Preferences"))
        try:
            ds.add(Path(json.loads(pref.read_text(encoding="utf-8"))["download"]["default_directory"]))
        except (OSError, KeyError, ValueError, TypeError):
            pass
    return [d for d in ds if d.is_dir()]


def goi_gemini(prompt):
    """Gọi Gemini (Google AI Studio), trả về chữ. Key + tên model nằm trong .env (tab Cài đặt)."""
    key = V.ENV.get("GEMINI_API_KEY", "").strip()
    chinh = V.ENV.get("GEMINI_MODEL", "").strip() or GEMINI_MAC_DINH
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 1.0}}).encode()
    goi_y = {400: "Key sai hoặc yêu cầu không hợp lệ.", 403: "Key không có quyền / chưa bật Gemini API.",
             404: f"Không có model '{chinh}': sửa tên model ở tab Cài đặt.", 429: "Hết lượt miễn phí, đợi 1 phút rồi thử lại."}
    loi = ""
    # model chính quá tải / quá chậm -> thử lại 1 lần, rồi chuyển sang bản lite (nhanh, ít khi quá tải)
    for model in dict.fromkeys([chinh, GEMINI_DU_PHONG]):
        for lan in range(2):
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                         body, {"Content-Type": "application/json", "x-goog-api-key": key})  # key trong header
            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    data = json.load(r)
                txt = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return txt.replace("**", "")  # AI hay tự in đậm kiểu markdown, Facebook hiện nguyên dấu **
            except urllib.error.HTTPError as e:
                if e.code not in (500, 502, 503, 504):
                    try:
                        msg = json.loads(e.read()).get("error", {}).get("message", "")
                    except ValueError:
                        msg = ""
                    raise RuntimeError(f"{goi_y.get(e.code, f'Lỗi {e.code}.')}\n\n{msg[:300]}") from None
                loi = f"Google quá tải ({e.code})"
            except (TimeoutError, OSError) as e:  # gồm cả mất mạng (URLError là OSError)
                if isinstance(e, urllib.error.URLError) and not isinstance(e.reason, TimeoutError):
                    raise RuntimeError(f"Không kết nối được Gemini (mạng?): {e.reason}") from None
                loi = "AI trả lời quá lâu"
            except (KeyError, IndexError):
                raise RuntimeError(f"AI không trả lời (có thể bị chặn nội dung): {str(data)[:300]}") from None
            time.sleep(3)
    raise RuntimeError(f"{loi}. Thử lại sau ít phút, hoặc đổi Model ở tab Cài đặt.")


def so_mon(tieu_de, n):
    """'... *5 món* ...' -> '... *4 món* ...' theo số món thật. Chỉ đổi con số đứng ngay trước chữ 'món'."""
    return re.sub(r"\d+(?=\s*món)", str(n), tieu_de, count=1, flags=re.I)


def ten_ngan(s):
    s = re.sub(r"^\s*(?:[\[(【][^\])】]*[\])】]\s*)+", "", s)  # bỏ "[FREE SHIP]" đầu tên
    return re.split(r"[,/|\-]", s)[0].strip().capitalize()[:35]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tạo video Shopee Affiliate")
        self.geometry("1100x700")
        self.data, self.mon, self.log_q = [], [], queue.Queue()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.buoc1(), self.buoc2(), self.buoc3(), self.y_tuong(), self.cai_dat()
        self.after(100, self.xa_log)
        self.protocol("WM_DELETE_WINDOW", lambda: (self.player and self.player.kill(), self.destroy()))
        # mở từ .bat bằng pythonw: Windows hay để cửa sổ chìm sau Explorer -> trông như app tự tắt. Kéo lên trên cùng 1 lần.
        self.lift()
        self.attributes("-topmost", True)
        self.after(800, lambda: (self.attributes("-topmost", False), self.focus_force()))
        moi = sorted(EXCEL.glob("*.csv"))
        if moi:
            self.nap(moi)

    # ---------- Bước 1: chọn sản phẩm ----------
    def buoc1(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="1. Chọn sản phẩm")
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Button(top, text="Mở file CSV...", command=lambda: self.nap(filedialog.askopenfilenames(
            initialdir=EXCEL, filetypes=[("CSV", "*.csv")]))).pack(side="left")
        self.an0 = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Ẩn món chưa bán được", variable=self.an0, command=self.ve_bang).pack(side="left", padx=10)
        self.lb1 = ttk.Label(top, text="")
        self.lb1.pack(side="left", padx=10)
        ttk.Button(top, text="Tiếp → Bước 2", command=self.sang2).pack(side="right")
        cols = ("ban", "gia", "tl", "hh", "shop", "ten")
        self.tv = ttk.Treeview(f, columns=cols, show="headings", selectmode="extended")
        for c, t, w in zip(cols, ("Đã bán", "Giá", "% HH", "HH/đơn", "Shop", "Tên sản phẩm"), (70, 80, 60, 80, 160, 600)):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor="w" if c in ("shop", "ten") else "e")
        sb = ttk.Scrollbar(f, command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=6)
        self.tv.pack(fill="both", expand=True, pady=6)
        ttk.Label(f, text="Xếp sẵn theo khả năng bán (lượt bán × hoa hồng/đơn). Giữ Ctrl để chọn nhiều món (nên 5 món).").pack(anchor="w")

    def nap(self, files):
        if not files:
            return
        self.data = doc_csv(files)
        self.ve_bang()

    def ve_bang(self):
        self.tv.delete(*self.tv.get_children())
        hien = [r for r in self.data if r["_ban"] or not self.an0.get()]
        for i, r in enumerate(self.data):
            if r in hien:
                self.tv.insert("", "end", iid=str(i), values=(r["Doanh thu"], f"{r['_gia']:,.0f}", r["Tỉ lệ hoa hồng"],
                                                             f"{r['_hh']:,.0f}", r["Tên cửa hàng"], r["Tên sản phẩm"]))
        self.lb1.config(text=f"{len(hien)}/{len(self.data)} món")

    def sang2(self):
        chon = [self.data[int(i)] for i in self.tv.selection()]
        if not chon:
            return messagebox.showinfo("Chưa chọn", "Chọn ít nhất 1 món (giữ Ctrl để chọn nhiều).")
        for w in self.khung2.winfo_children():
            w.destroy()
        self.mon, self.dang_mo = [], 0
        self.out = HERE / "video" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        (self.out / "anh").mkdir(parents=True)
        self.duong_dan.set(str(self.out / "anh"))
        self.bat_dau, self.da_lay = time.time(), set()  # chỉ lấy file tải về SAU lúc này; da_lay: file gốc đã chép
        for j, r in enumerate(chon, 1):
            self.dong_mon(j, r)
        self.tieu_de.set(so_mon(self.tieu_de.get(), len(self.mon)))
        self.nb.select(1)

    def quet_anh(self):
        """Mỗi giây xem thư mục ảnh: ảnh mới lưu vào -> gắn cho món vừa bấm 'Mở link' (món đó có ảnh rồi thì món đầu tiên còn thiếu)."""
        if self.mon:
            if any(not m["anh"] for m in self.mon):
                # file vừa tải, lưu ở BẤT KỲ đâu (lịch sử tải của trình duyệt) + file mới trong Downloads (cho Firefox)
                # -> chép (không xóa bản gốc) về thư mục ảnh
                nguon = file_vua_tai(self.bat_dau)
                for d in thu_muc_tai():
                    for f in d.iterdir():
                        try:
                            if max(f.stat().st_mtime, f.stat().st_ctime) > self.bat_dau:
                                nguon.append(f)
                        except OSError:
                            pass
                anh = (self.out / "anh").resolve()
                for f in nguon:
                    try:
                        f = f.resolve()
                        if (f in self.da_lay or f.parent == anh or f.suffix.lower() not in DUOI_ANH + V.DUOI_VIDEO
                                or not f.is_file()):
                            continue
                        dich = anh / f.name
                        if dich.exists():
                            dich = dich.with_stem(f"{f.stem}_{int(time.time())}")
                        shutil.copy2(f, dich)
                        self.da_lay.add(f)
                    except OSError:  # file đang được ghi dở -> lần quét sau
                        pass
            da = {m["anh"] for m in self.mon}
            moi = sorted((f for f in (self.out / "anh").iterdir() if f not in da
                          and f.suffix.lower() in DUOI_ANH + V.DUOI_VIDEO
                          and not f.stem.endswith(("_tay", "_poster"))),
                         key=lambda f: f.stat().st_mtime)
            for f in moi:
                thieu = [m for m in self.mon if not m["anh"]]
                if not thieu:
                    break
                m = self.mon[self.dang_mo] if not self.mon[self.dang_mo]["anh"] else thieu[0]
                m["anh"] = f
                m["lb"].config(text=("🎬 " if f.suffix.lower() in V.DUOI_VIDEO else "") + f.name[:28], foreground="green")
        self.after(1000, self.quet_anh)

    def mo_link(self, j, r):
        self.dang_mo = j - 1
        self.clipboard_clear()
        self.clipboard_append(self.duong_dan.get())  # trong hộp "Lưu ảnh" bấm Ctrl+V vào ô đường dẫn là đúng thư mục
        webbrowser.open(r["Link sản phẩm"])

    # ---------- Bước 2: nội dung + ảnh ----------
    def buoc2(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="2. Nội dung & ảnh")
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Tiêu đề bìa (bọc *chữ* để tô cam):").pack(side="left")
        self.tieu_de = tk.StringVar(value="Nhà gọn, sáng, tiện: 5 món *bán chạy* nhất")
        ttk.Combobox(top, textvariable=self.tieu_de, width=60,  # gõ tự do hoặc chọn tiêu đề từ 10 ý tưởng
                     values=[p[2] for p in T.POSTS]).pack(side="left", padx=6)
        ttk.Button(top, text="Tiếp → Bước 3", command=lambda: self.nb.select(2)).pack(side="right")
        hd = ttk.Frame(f)
        hd.pack(fill="x", pady=(10, 0))
        for t, w in (("#", 3), ("Tên ngắn", 28), ("Mô tả", 36), ("Giá", 8), ("Ảnh", 30)):
            ttk.Label(hd, text=t, width=w, font=("", 9, "bold")).pack(side="left", padx=2)
        self.khung2 = ttk.Frame(f)
        self.khung2.pack(fill="both", expand=True)
        tm = ttk.Frame(f)
        tm.pack(fill="x", pady=4)
        ttk.Label(tm, text="Thư mục lưu ảnh:").pack(side="left")
        self.duong_dan = tk.StringVar(value="(chọn món ở Bước 1 trước)")
        ttk.Entry(tm, textvariable=self.duong_dan, width=70, state="readonly").pack(side="left", padx=6)
        ttk.Button(tm, text="Copy", command=lambda: (self.clipboard_clear(), self.clipboard_append(self.duong_dan.get()))).pack(side="left")
        ttk.Button(tm, text="Mở thư mục", command=lambda: self.mon and os.startfile(self.out / "anh")).pack(side="left", padx=4)
        ttk.Label(f, text="Bấm 'Mở link' → chuột phải ảnh → 'Lưu hình ảnh thành...' → lưu Ở ĐÂU CŨNG ĐƯỢC: ảnh tự chép về "
                          "thư mục trên và gắn vào món vừa mở link (Chrome, Cốc Cốc, Edge; Firefox thì lưu vào Downloads).\n"
                          "Có video sản phẩm? Chuột phải video → 'Lưu video thành...' tương tự → "
                          "video phát 5 giây trong khung ảnh (🎬), tắt tiếng gốc.").pack(anchor="w")
        self.after(1000, self.quet_anh)

    def dong_mon(self, j, r):
        d = ttk.Frame(self.khung2)
        d.pack(fill="x", pady=3)
        m = {"r": r, "ten": tk.StringVar(value=ten_ngan(r["Tên sản phẩm"])), "mota": tk.StringVar(),
             "gia": tk.StringVar(value=V.gia_k(r["_gia"])), "anh": None}
        ttk.Label(d, text=str(j), width=3).pack(side="left", padx=2)
        ttk.Entry(d, textvariable=m["ten"], width=30).pack(side="left", padx=2)
        ttk.Entry(d, textvariable=m["mota"], width=38).pack(side="left", padx=2)
        ttk.Entry(d, textvariable=m["gia"], width=8).pack(side="left", padx=2)
        lb = m["lb"] = ttk.Label(d, text="(chưa có ảnh)", width=30, foreground="red")

        def chon_anh():
            p = filedialog.askopenfilename(initialdir=self.out / "anh",
                                           filetypes=[("Ảnh / video", "*.jpg *.jpeg *.png *.webp *.mp4 *.webm *.mov")])
            if p:
                m["anh"] = Path(p)
                lb.config(text=m["anh"].name[:30], foreground="green")

        ttk.Button(d, text="Mở link", command=lambda: self.mo_link(j, r)).pack(side="left", padx=2)
        ttk.Button(d, text="Chọn ảnh", command=chon_anh).pack(side="left", padx=2)
        lb.pack(side="left", padx=2)
        self.mon.append(m)

    # ---------- Bước 3: nhạc + tạo video ----------
    def buoc3(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="3. Nhạc & tạo video")
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Nhạc nền:").pack(side="left")
        self.nhacs = V.ds_nhac()
        self.nhac = tk.StringVar(value="Ngẫu nhiên")
        ttk.Combobox(top, textvariable=self.nhac, state="readonly", width=35,
                     values=["Ngẫu nhiên", "Không nhạc"] + [n.stem for n in self.nhacs]).pack(side="left", padx=6)
        self.nut_nghe = ttk.Button(top, text="▶ Nghe thử", command=self.nghe)
        self.nut_nghe.pack(side="left")
        self.player = None
        # Nhạc thịnh hành TikTok có bản quyền, không tải về ghép được -> xem danh sách, xuất video "Không nhạc", chọn nhạc trong app lúc đăng
        ttk.Button(top, text="🔥 Nhạc hot TikTok", command=self.nhac_tiktok).pack(side="left", padx=6)
        self.nut = ttk.Button(top, text="TẠO VIDEO", command=self.tao)
        self.nut.pack(side="left", padx=20)
        self.nut_mo = ttk.Button(top, text="Mở thư mục video", state="disabled", command=lambda: os.startfile(self.out))
        self.nut_mo.pack(side="left")
        td = ttk.Frame(f)
        td.pack(fill="x", pady=(8, 0))
        self.td = tk.DoubleVar()
        ttk.Progressbar(td, variable=self.td, maximum=100).pack(side="left", fill="x", expand=True)
        self.td_chu = ttk.Label(td, text="", width=28)
        self.td_chu.pack(side="left", padx=6)
        self.log = tk.Text(f, height=8, font=("Consolas", 9))
        self.log.pack(fill="x", pady=6)
        fb = ttk.LabelFrame(f, text="Gợi ý đăng Facebook Reels: video không bấm link được → để link ở BÌNH LUẬN rồi ghim "
                                    "(link trong nội dung bài Facebook hay giảm lượt xem)", padding=6)
        fb.pack(fill="both", expand=True)
        self.fb = {}
        for c, (k, t) in enumerate((("cap", "① Nội dung bài (dán vào ô mô tả Reels)"), ("cmt", "② Bình luận đầu tiên → bấm Ghim"))):
            ttk.Label(fb, text=t).grid(row=0, column=c, sticky="w")
            self.fb[k] = tk.Text(fb, height=12, width=60, font=("", 10), wrap="word")
            self.fb[k].grid(row=1, column=c, sticky="nsew", padx=3)
            ttk.Button(fb, text="Copy", command=lambda k=k: (self.clipboard_clear(), self.clipboard_append(
                self.fb[k].get("1.0", "end").strip()))).grid(row=2, column=c, sticky="w", padx=3, pady=3)
            fb.columnconfigure(c, weight=1)
        fb.rowconfigure(1, weight=1)
        self.nut_ai = ttk.Button(fb, text="✨ AI viết caption (bấm lại = bản khác)", command=self.ai_caption)
        self.nut_ai.grid(row=2, column=0, sticky="e", padx=3)
        self.nhac_da_chon = None

    def ai_caption(self):
        """Nhờ Gemini viết nội dung bài Reels thu hút hơn từ danh sách món (link vẫn để ở bình luận ghim)."""
        if not self.mon:
            return messagebox.showinfo("Chưa có món", "Làm Bước 1 trước.")
        self.tieu_de.set(so_mon(self.tieu_de.get(), len(self.mon)))
        if not V.ENV.get("GEMINI_API_KEY", "").strip():
            self.nb.select(4)
            return messagebox.showinfo("Thiếu key AI", "Dán Gemini API key ở tab Cài đặt (lấy miễn phí ở aistudio.google.com/apikey).")
        mon = "\n".join(f"{j}. {m['ten'].get()} | giá {m['gia'].get() or '?'} | đã bán {m['r']['Doanh thu']} | "
                        f"{m['mota'].get() or m['r']['Tên sản phẩm'][:80]}" for j, m in enumerate(self.mon, 1))
        prompt = f"""Bạn là người làm nội dung Facebook Reels bán đồ gia dụng affiliate ở Việt Nam, giọng gần gũi, vui.
Viết NỘI DUNG BÀI (caption) cho 1 video giới thiệu các món dưới đây. Chủ đề video: {self.tieu_de.get().replace('*', '')}

Các món (theo thứ tự trong video):
{mon}

Yêu cầu:
- Dòng đầu là câu móc kéo dưới 90 ký tự, gây tò mò hoặc chạm nỗi khổ hằng ngày (đừng mở bằng "Chào mọi người").
- 1-2 câu ngắn kể lợi ích thực tế, không bịa thông số, không hứa hẹn quá đà.
- Liệt kê từng món theo số 1️⃣ 2️⃣ 3️⃣..., mỗi dòng: tên + lợi ích chính 3-7 chữ + giá (nếu có).
- Một câu kêu gọi bình luận dễ trả lời (ví dụ comment số món thích nhất), và nhắc "link mua ở bình luận đầu tiên".
- Cuối cùng 6-8 hashtag tiếng Việt không dấu, liên quan, có #reels.
- Emoji vừa phải. Tổng dưới 900 ký tự. KHÔNG chèn link, KHÔNG dùng markdown (**, #tiêu đề).
Chỉ trả về đúng nội dung caption."""
        self.nut_ai.config(state="disabled", text="✨ AI đang viết...")

        def chay():
            try:
                txt = goi_gemini(prompt)
                if self.nhac_da_chon:
                    txt += f'\n\nMusic: "{self.nhac_da_chon.stem}" by Kevin MacLeod (incompetech.com), CC BY 4.0'
                self.log_q.put(lambda: self.dat_caption(txt))
            except Exception as e:
                self.log_q.put(lambda e=e: messagebox.showerror("AI lỗi", str(e)))
            finally:
                self.log_q.put(lambda: self.nut_ai.config(state="normal", text="✨ AI viết caption (bấm lại = bản khác)"))

        threading.Thread(target=chay, daemon=True).start()

    def dat_caption(self, txt):
        self.fb["cap"].delete("1.0", "end")
        self.fb["cap"].insert("1.0", txt)
        if self.out.exists():
            (self.out / "facebook_noi_dung.txt").write_text(txt, encoding="utf-8")

    def bai(self):
        v = self.nhac.get()
        if v == "Không nhạc" or not self.nhacs:
            return None
        return random.choice(self.nhacs) if v == "Ngẫu nhiên" else next(n for n in self.nhacs if n.stem == v)

    def nghe(self):
        """Bấm lần 1 phát (ffplay, không mở cửa sổ), bấm lần 2 dừng. Đang 'Ngẫu nhiên' thì bốc 1 bài và chọn luôn bài đó."""
        if self.player and self.player.poll() is None:
            self.player.kill()
            self.nut_nghe.config(text="▶ Nghe thử")
            return
        n = self.bai()
        if not n:
            return messagebox.showinfo("Không có nhạc", "Chọn một bài nhạc (hoặc bỏ file .mp3 vào thư mục nhac).")
        self.nhac.set(n.stem)
        try:
            self.player = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(n)],
                                           creationflags=subprocess.CREATE_NO_WINDOW)
        except FileNotFoundError:
            return messagebox.showerror("Thiếu ffmpeg", V.THIEU_FFMPEG or "Không tìm thấy ffplay.exe (đi kèm ffmpeg).")
        self.nut_nghe.config(text="■ Dừng")

    def nhac_tiktok(self):
        webbrowser.open("https://ads.tiktok.com/business/creativecenter/inspiration/popular/music/pc/vi?region=VN")
        if messagebox.askyesno("Nhạc thịnh hành TikTok",
                               "Đã mở bảng xếp hạng nhạc hot TikTok Việt Nam (TikTok Creative Center).\n\n"
                               "Nhạc này có bản quyền nên không ghép sẵn vào video được: chọn bài ngay trong app TikTok "
                               "lúc đăng (bấm 'Thêm âm thanh', tìm tên bài).\n\n"
                               "Chuyển nhạc nền sang 'Không nhạc' để video không bị chồng 2 bài?"):
            self.nhac.set("Không nhạc")

    def tao(self):
        if not self.mon:
            return messagebox.showinfo("Chưa có món", "Làm Bước 1 trước.")
        thieu = [str(j) for j, m in enumerate(self.mon, 1) if not m["anh"]]
        if thieu and not messagebox.askyesno("Thiếu ảnh", f"Món {', '.join(thieu)} chưa có ảnh (bot sẽ thử tự lấy, "
                                                         "thường bị Shopee chặn). Vẫn tạo?"):
            return
        rows = []
        for f in (self.out / "anh").glob("*_tay.*"):  # tạo lại lần 2 sau khi đổi ảnh -> bỏ bản cũ
            f.unlink()
        for j, m in enumerate(self.mon, 1):
            if m["anh"]:
                shutil.copy(m["anh"], self.out / "anh" / f"{j}_tay{m['anh'].suffix}")
            rows.append([m["r"]["Link ưu đãi"], m["ten"].get().strip(), m["mota"].get().strip(), m["gia"].get().strip()])
        (self.out / "link_gio_hang.txt").write_text(
            "\n".join(f"{j}. {m['ten'].get()}\n   {m['r']['Link ưu đãi']}" for j, m in enumerate(self.mon, 1)), encoding="utf-8")
        # tiêu đề chọn từ ý tưởng/gõ tay hay ghi "5 món" trong khi chỉ chọn 4 -> sửa theo số món thật
        self.tieu_de.set(so_mon(self.tieu_de.get(), len(self.mon)))
        nhac = self.bai()
        self.goi_y_fb(nhac)
        self.nut.config(state="disabled")
        self.log.delete("1.0", "end")
        self.dat_td(2, "Bắt đầu...")
        threading.Thread(target=self.chay, args=(self.tieu_de.get(), rows, nhac), daemon=True).start()

    def goi_y_fb(self, nhac):
        self.nhac_da_chon = nhac
        """Soạn sẵn nội dung bài + bình luận chứa link affiliate, lưu luôn ra file trong thư mục video."""
        so_icon = "1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣ 8️⃣ 9️⃣ 🔟".split()
        ic = lambda j: so_icon[j] if j < len(so_icon) else f"{j + 1}."
        mon = [(m["ten"].get().strip(), m["gia"].get().strip(), m["r"]["Link ưu đãi"]) for m in self.mon]
        mo_dau = random.choice(["Lưu lại ngay kẻo trôi nha 📌", "Món nào cũng rẻ mà xài sướng 😍",
                                "Mua về mới thấy sao không mua sớm hơn 😭", "Nhà gọn hẳn chỉ với vài món nhỏ ✨"])
        cap = [self.tieu_de.get().replace("*", ""), mo_dau, ""]
        cap += [f"{ic(j)} {t}" + (f" – chỉ {g}" if g else "") for j, (t, g, _) in enumerate(mon)]
        cap += ["", "👉 Link mua từng món mình để ở BÌNH LUẬN ĐẦU TIÊN nha!",
                "Bạn thích món số mấy? Comment số cho mình biết 👇", "",
                "#shopee #giadungtienich #dogiadung #muasamthongminh #reviewdogiadung #meovat #xuhuong #reels"]
        if nhac:
            cap += ["", f'Music: "{nhac.stem}" by Kevin MacLeod (incompetech.com), CC BY 4.0']
        cmt = ["🛒 Link mua các món trong video (Shopee):", ""]
        cmt += [f"{ic(j)} {t}: {l}" for j, (t, _, l) in enumerate(mon)]
        cmt += ["", "Giá có thể đổi theo khuyến mãi, bấm link xem giá mới nhất nha 💕"]
        for k, txt in (("cap", cap), ("cmt", cmt)):
            self.fb[k].delete("1.0", "end")
            self.fb[k].insert("1.0", "\n".join(txt))
        (self.out / "facebook_noi_dung.txt").write_text("\n".join(cap), encoding="utf-8")
        (self.out / "facebook_binh_luan.txt").write_text("\n".join(cmt), encoding="utf-8")

    def dat_td(self, pt, chu):
        self.td.set(pt)
        self.td_chu.config(text=chu)

    def chay(self, cover, rows, nhac):
        cu, sys.stdout = sys.stdout, self  # print() trong tao_video -> khung log
        V.TIEN_DO = lambda x: self.log_q.put(lambda: self.dat_td(60 + 40 * x, f"Xuất video {x:.0%}"))
        try:
            mp4 = V.tao(cover, rows, self.out, nhac)
            print("\nXONG! Đang mở video..." if mp4 else "\nLỖI: không tạo được video")
            if mp4:
                os.startfile(mp4)
        except Exception as e:
            print(f"\nLỖI: {e}")
        finally:
            sys.stdout = cu
            self.log_q.put(None)

    def write(self, s):  # nhận print() từ luồng tạo video; dòng "   3. Tên -> có ảnh" = xong món 3
        self.log_q.put(s)
        m, n = re.match(r"\s+(\d+)\. ", s), len(self.mon)
        if m:
            j = int(m.group(1))
            self.log_q.put(lambda: self.dat_td(5 + 45 * j / n, f"Xong món {j}/{n}" if j < n else "Đang vẽ slide..."))

    def flush(self):
        pass

    def xa_log(self):
        while not self.log_q.empty():
            s = self.log_q.get()
            if callable(s):
                s()
            elif s is None:
                ok = (self.out / "video.mp4").exists()
                self.dat_td(100 if ok else 0, "Xong ✔" if ok else "Lỗi ✘")
                self.nut.config(state="normal")
                self.nut_mo.config(state="normal")
            else:
                self.log.insert("end", s)
                self.log.see("end")
        self.after(100, self.xa_log)

    # ---------- Slide ý tưởng (10 bài trong tao_slide.py) ----------
    def y_tuong(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="📝 Slide ý tưởng")
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Ý tưởng:").pack(side="left")
        self.ds_y = [f"{k}. {p[1]}  {p[2].replace('*', '')}" for k, p in enumerate(T.POSTS, 1)]
        self.y = ttk.Combobox(top, state="readonly", width=70, values=self.ds_y)
        self.y.pack(side="left", padx=6)
        self.y.bind("<<ComboboxSelected>>", lambda e: self.nap_y(self.y.current()))
        ttk.Button(top, text="🎲 Gợi ý ngẫu nhiên", command=lambda: self.nap_y(random.randrange(len(T.POSTS)))).pack(side="left")
        g = ttk.Frame(f)
        g.pack(fill="both", expand=True, pady=8)
        self.yv = {k: tk.StringVar() for k in ("tag", "cover", "cta", "sub")}
        for i, (k, t) in enumerate((("tag", "Nhãn góc"), ("cover", "Tiêu đề bìa (*chữ cam*)"),
                                    ("cta", "Câu chốt"), ("sub", "Dòng phụ"))):
            ttk.Label(g, text=t).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(g, textvariable=self.yv[k], width=80).grid(row=i, column=1, sticky="w", pady=3)
        ttk.Label(g, text="Các món\n(mỗi dòng:\ntên | mô tả | giá)").grid(row=4, column=0, sticky="nw", pady=3)
        self.y_mon = tk.Text(g, height=10, width=80, font=("", 10))
        self.y_mon.grid(row=4, column=1, sticky="w", pady=3)
        nut = ttk.Frame(f)
        nut.pack(fill="x")
        self.nut_slide = ttk.Button(nut, text="TẠO SLIDE (PDF + ảnh)", command=self.tao_slide)
        self.nut_slide.pack(side="left")
        ttk.Button(nut, text="Dùng tiêu đề này cho video →", command=lambda: (
            self.tieu_de.set(self.yv["cover"].get()), self.nb.select(1))).pack(side="left", padx=10)
        ttk.Button(nut, text="Mở thư mục slide", command=lambda: (T.OUT.mkdir(exist_ok=True), os.startfile(T.OUT))).pack(side="left")
        self.y_kq = ttk.Label(f, text="Slide PDF tải lên canva.com để thay ảnh; ảnh PNG đăng TikTok chế độ Ảnh.")
        self.y_kq.pack(anchor="w", pady=6)
        self.nap_y(0)

    def nap_y(self, k):
        _, tag, cover, items, cta, sub = T.POSTS[k]
        self.y.current(k)
        for key, v in zip(("tag", "cover", "cta", "sub"), (tag, cover, cta, sub)):
            self.yv[key].set(v)
        self.y_mon.delete("1.0", "end")
        self.y_mon.insert("1.0", "\n".join(f"{t} | {m} | {g or ''}" for t, m, g in items))

    def tao_slide(self):
        items = [([*(x.strip() for x in l.split("|")), "", ""][:3]) for l in self.y_mon.get("1.0", "end").splitlines() if l.strip()]
        if not items:
            return messagebox.showinfo("Chưa có món", "Gõ ít nhất 1 món.")
        items = [(t, m, g or None) for t, m, g in items]
        v = {k: x.get() for k, x in self.yv.items()}
        ten = T.OUT / f"slide_{datetime.now():%Y-%m-%d_%H%M%S}"
        self.nut_slide.config(state="disabled")
        self.y_kq.config(text="Đang tạo slide...")

        def chay():
            T.OUT.mkdir(exist_ok=True)
            doc, n = T.build(v["tag"], v["cover"], items, v["cta"], v["sub"])
            T.render(doc, ten.with_suffix(".pdf"), ten.with_suffix(".png"), n)
            self.log_q.put(lambda: xong(n))  # tkinter chỉ được đụng từ luồng chính -> nhờ xa_log gọi

        def xong(n):
            self.nut_slide.config(state="normal")
            if ten.with_suffix(".png").exists():
                self.y_kq.config(text=f"Xong {n} trang: {ten.with_suffix('.pdf')}")
                os.startfile(ten.with_suffix(".png"))
            else:
                self.y_kq.config(text="LỖI: không tạo được slide (kiểm tra Chrome/Edge và mạng)")

        threading.Thread(target=chay, daemon=True).start()

    # ---------- Cài đặt ----------
    def cai_dat(self):
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text="⚙ Cài đặt")
        ttk.Label(f, text="Khóa Shopee Affiliate Open API (lấy ở affiliate.shopee.vn → Open API). "
                          "Có khóa thì bot tự lấy ảnh, giá, link.").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.app_id, self.secret = tk.StringVar(value=V.APP_ID), tk.StringVar(value=V.SECRET)
        for i, (t, v, an) in enumerate((("App ID", self.app_id, ""), ("Secret", self.secret, "•")), 1):
            ttk.Label(f, text=t).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=v, width=60, show=an).grid(row=i, column=1, sticky="w", pady=4)
        ttk.Label(f, text="AI viết caption: Gemini API key (miễn phí, lấy ở aistudio.google.com/apikey)").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(16, 4))
        ttk.Button(f, text="Mở trang lấy key", command=lambda: webbrowser.open("https://aistudio.google.com/apikey")).grid(
            row=3, column=1, sticky="e")
        self.gm_key = tk.StringVar(value=V.ENV.get("GEMINI_API_KEY", "").strip())
        self.gm_model = tk.StringVar(value=V.ENV.get("GEMINI_MODEL", "").strip() or GEMINI_MAC_DINH)
        for i, (t, v, an) in enumerate((("Gemini key", self.gm_key, "•"), ("Model", self.gm_model, "")), 4):
            ttk.Label(f, text=t).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=v, width=60, show=an).grid(row=i, column=1, sticky="w", pady=4)
        ttk.Button(f, text="Lưu", command=self.luu).grid(row=6, column=1, sticky="w", pady=10)
        ttk.Label(f, text="⚠ Các key lưu trong file .env cạnh tool: khi gửi tool cho người khác thì XÓA file .env đi.").grid(
            row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="Nhạc: bỏ thêm file .mp3 vào thư mục 'nhac' rồi mở lại giao diện.").grid(row=8, column=0, columnspan=2, sticky="w", pady=(20, 0))
        ttk.Button(f, text="Mở thư mục nhac", command=lambda: os.startfile(HERE / "nhac")).grid(row=9, column=0, sticky="w", pady=4)

    def luu(self):
        v = {"SHOPEE_APP_ID": self.app_id.get().strip(), "SHOPEE_SECRET": self.secret.get().strip(),
             "GEMINI_API_KEY": self.gm_key.get().strip(), "GEMINI_MODEL": self.gm_model.get().strip()}
        (HERE / ".env").write_text("# Shopee: affiliate.shopee.vn -> Open API.  Gemini: aistudio.google.com/apikey\n"
                                   + "".join(f"{k}={x}\n" for k, x in v.items()), encoding="utf-8")
        V.ENV.update(v)
        V.APP_ID, V.SECRET = v["SHOPEE_APP_ID"], v["SHOPEE_SECRET"]
        messagebox.showinfo("Đã lưu", "Đã lưu các khóa API.")


if __name__ == "__main__":
    if sys.stderr is None:  # mở bằng pythonw (không cửa sổ đen): lỗi ghi ra loi.txt để còn xem
        sys.stderr = open(HERE / "loi.txt", "a", encoding="utf-8")
    assert so("1k+") == 1000 and so("156,0k") == 156000 and so("₫18.720") == 18720 and so("896") == 896
    App().mainloop()
