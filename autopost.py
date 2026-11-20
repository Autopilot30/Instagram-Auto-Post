"""
69.co.in - Hinglish knowledge carousel auto-poster (Instagram Graph API), design v2.

Usage:
  python autopost.py generate   # AI writes a 5-slide post + slide images are created
  python autopost.py publish    # latest unpublished post goes to Instagram
Env vars: GEMINI_API_KEY (free) or ANTHROPIC_API_KEY, IG_USER_ID, IG_ACCESS_TOKEN,
          MAX_POSTS (default 30), GEMINI_MODEL, CLAUDE_MODEL, GRAPH_VERSION (optional)
"""
import os, sys, json, time, random, shutil, pathlib
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = pathlib.Path(__file__).parent
POSTS = ROOT / "posts"
FONT_DIR = ROOT / "fonts"
MAX_POSTS = int(os.getenv("MAX_POSTS", "30"))
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
GEMINI_MODELS = [m for m in [os.getenv("GEMINI_MODEL", ""), "gemini-3.8-flash",
                 "gemini-3.5-flash-lite", "gemini-flash-latest"] if m]
HANDLE = "@69.co.in"
GV = os.getenv("GRAPH_VERSION", "").strip()
GRAPH = "https://graph.facebook.com/" + (GV + "/" if GV else "")
W, H = 1080, 1350
TOTAL = 5  # cover + 3 points + closing

ACCENTS = {  # category -> accent colour
    "MONEY": (76, 217, 56), "MIND": (176, 108, 255), "BUSINESS": (255, 190, 40),
    "AI": (40, 210, 240), "CAREER": (255, 105, 130),
}
WHITE, GREY, BLACK = (245, 245, 245), (170, 170, 175), (8, 8, 8)

# ---------------- fonts ----------------
ANTON_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf"
ANTON_PATHS = [str(FONT_DIR / "Anton-Regular.ttf"),
               "/usr/share/fonts/truetype/google-fonts/ofl/anton/Anton-Regular.ttf"]
BODY_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]
_font_cache = {}

def _find(paths):
    return next((p for p in paths if os.path.exists(p)), None)

def head_font(size):
    key = ("h", size)
    if key not in _font_cache:
        p = _find(ANTON_PATHS)
        if not p:                                   # download once (GitHub runner has internet)
            try:
                FONT_DIR.mkdir(exist_ok=True)
                r = requests.get(ANTON_URL, timeout=60); r.raise_for_status()
                (FONT_DIR / "Anton-Regular.ttf").write_bytes(r.content)
                p = str(FONT_DIR / "Anton-Regular.ttf")
            except Exception as e:
                print("Anton download failed, using fallback font:", e)
                p = _find(BODY_PATHS)
        _font_cache[key] = ImageFont.truetype(p, size)
    return _font_cache[key]

def body_font(size):
    key = ("b", size)
    if key not in _font_cache:
        p = _find(BODY_PATHS)
        if not p:
            raise SystemExit("No body font found. Install fonts-dejavu-core.")
        _font_cache[key] = ImageFont.truetype(p, size)
    return _font_cache[key]

def history_topics():
    out = []
    for f in sorted(POSTS.glob("*/post.json")):
        out.append(json.loads(f.read_text(encoding="utf-8")).get("topic", ""))
    return out

# ---------------- content ----------------
SYSTEM = """You are the writer of the Instagram page 69.co.in (Indian audience). You write in HINGLISH:
natural Hindi written in ROMAN letters (like "Tumhari salary ka sabse bada chor kaun hai?").

VOICE: a calm, blunt mentor with 50 years of lived experience in business, hiring/HR, money,
psychology and technology. The insight must feel EARNED: specific, observational, a little
contrarian, something people feel but rarely hear said plainly. Short punchy sentences.
Every point needs a concrete observation or a small realistic scenario (use simple rupee numbers
and say "maan lo" / "example" when numbers are illustrative).
AVOID: cliches ("success ka mantra", "5 tips"), motivational fluff, "in today's fast world",
generic AI-listicle tone. Do NOT invent statistics, studies, quotes, names or fake credentials
(never write "mere 50 saal ke experience me"). No guaranteed-income claims, no specific
stock/crypto/investment advice.

Pick ONE category: MONEY, MIND, BUSINESS, AI or CAREER. The topic is a curiosity question or a
reframe that mixes knowledge, money, business, psychology or AI.

Return ONLY JSON with exactly this shape (all Hinglish, Roman letters; limits are strict):
{
 "topic": "short topic name",
 "category": "MONEY|MIND|BUSINESS|AI|CAREER",
 "cover": {
   "l1": ["1-2 lines, max 3 words each"],
   "bar": "2-3 words shown in a highlight bar",
   "big": "ONE huge word, max 9 letters",
   "tag": "max 4 words, a punchy twist",
   "sub": "1 short sentence, max 12 words",
   "sub_hl": "max 6 words, the sting of the sentence",
   "stamp": ["3 short lines, max 3 words each"],
   "strip": ["4 captions, max 4 words each"]
 },
 "points": [ {"head": "max 5 words", "hl": "max 3 words", "body": "max 38 words, 2-3 short sentences",
              "example": "max 22 words, a concrete mini scenario"} x3 ],
 "close": {"head": "max 5 words", "hl": "max 3 words", "body": "max 28 words",
           "question": "max 8 words, a question for the comments"},
 "caption": "2-3 short lines + 8 relevant hashtags"
}
Example of the cover style (do NOT reuse this topic):
"cover": {"l1": ["TUMHARI SALARY KA"], "bar": "SABSE BADA CHOR", "big": "LIFESTYLE",
 "tag": "NAUKRI NAHI.", "sub": "Kharcha tumhari income ke saath badhta hai,", "sub_hl": "tab tak bachat zero.",
 "stamp": ["TU KAMA LETA HAI,", "PAR BACHATA", "KYA HAI?"],
 "strip": ["Zyada kamate ho", "Paisa tikta kyu nahi?", "Income badhi, bachat?", "Mindset samjho"]}"""

ANGLES = [
    "something almost everyone gets wrong about money", "a hidden cost people never calculate",
    "how hiring/promotions really work behind closed doors", "a psychology trap that keeps people stuck",
    "a business lesson small shop owners learn too late", "how to use AI as an unfair advantage at work",
    "why smart people stay poor", "a boring habit that quietly builds wealth",
    "what negotiators know that employees don't", "a belief about success that is simply false",
]

def llm_json(system, user):
    """Uses Gemini (free tier) if GEMINI_API_KEY is set, else Claude."""
    if os.getenv("GEMINI_API_KEY"):
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json"}}
        txt = None
        for model in GEMINI_MODELS:           # try next model if one is slow/unavailable
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            for attempt in range(2):
                try:
                    r = requests.post(url, json=body, timeout=60,
                                      headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
                except requests.exceptions.RequestException as e:
                    print(f"[{model}] network/timeout: {type(e).__name__}"); continue
                if r.status_code in (429, 500, 503):
                    print(f"[{model}] busy {r.status_code}, waiting"); time.sleep(15); continue
                if not r.ok:
                    print(f"[{model}] error {r.status_code}: {r.text[:300]}"); break
                try:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    print(f"[{model}] empty answer: {r.text[:300]}"); continue
                print(f"[{model}] ok"); break
            if txt: break
        if not txt:
            raise SystemExit("All Gemini models failed. See messages above.")
    else:
        import anthropic
        r = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=1500, system=system,
                                   messages=[{"role": "user", "content": user}])
        txt = "".join(b.text for b in r.content if b.type == "text")
    txt = txt.strip().replace("```json", "").replace("```", "").strip()
    start = txt.find("{")
    if start < 0:
        raise ValueError("no JSON in model answer: " + txt[:200])
    obj, _ = json.JSONDecoder().raw_decode(txt[start:])  # ignores any extra text after the JSON
    return obj

def check_post(p):
    need = ["topic", "category", "cover", "points", "close", "caption"]
    for k in need:
        if not p.get(k):
            raise ValueError(f"missing {k}")
    p["category"] = str(p["category"]).upper()
    if p["category"] not in ACCENTS:
        p["category"] = "MONEY"
    c = p["cover"]
    for k in ["l1", "bar", "big", "tag", "sub", "stamp", "strip"]:
        if not c.get(k):
            raise ValueError(f"cover missing {k}")
    if isinstance(c["l1"], str): c["l1"] = [c["l1"]]
    if len(p["points"]) < 3:
        raise ValueError("need 3 points")
    p["points"] = p["points"][:3]
    for pt in p["points"]:
        for k in ["head", "body"]:
            if not pt.get(k): raise ValueError("point missing " + k)
    for k in ["head", "body", "question"]:
        if not p["close"].get(k): raise ValueError("close missing " + k)
    c["strip"] = (list(c["strip"]) + [""] * 4)[:4]
    return p

def make_post():
    done = history_topics()
    for attempt in range(5):
        try:
            angle = random.choice(ANGLES)
            post = check_post(llm_json(SYSTEM,
                f"Angle to explore (you may twist it): {angle}\n"
                f"Do NOT repeat these earlier topics: {done}"))
            review = llm_json(
                'You are a strict fact-checker and editor. Return ONLY JSON {"ok": bool, "reason": str}. '
                "ok=false if the text has false or doubtful facts, invented statistics or credentials, "
                "guaranteed-income promises, investment advice, or reads like generic motivational fluff.",
                json.dumps(post, ensure_ascii=False))
        except (ValueError, KeyError, TypeError) as e:   # odd model output -> retry
            print(f"Attempt {attempt + 1}: bad model output ({type(e).__name__}: {e})")
            continue
        if review.get("ok"):
            return post
        print("Rejected by reviewer:", review.get("reason"))
    raise SystemExit("Could not produce a good post after 5 tries.")

# ---------------- design v2 ----------------
def U(s):  # headline text is uppercase
    return " ".join(str(s).split()).upper()

def ink(d, text, font):
    b = d.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1], b[0], b[1]

def put(d, x, y, text, font, fill):
    """draw text so that the TOP of the ink sits at y; returns ink height"""
    w, h, ox, oy = ink(d, text, font)
    d.text((x - ox, y - oy), text, font=font, fill=fill)
    return h

def fit(d, text, getfont, max_w, max_size, min_size=24):
    for s in range(int(max_size), min_size - 1, -2):
        f = getfont(s)
        if ink(d, text, f)[0] <= max_w:
            return f
    return getfont(min_size)

def wrap(d, text, font, max_w):
    lines, cur = [], ""
    for word in str(text).split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=font) <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = word
    if cur: lines.append(cur)
    return lines

def glow(img, cx, cy, r, color, alpha):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(r / 2.2)))

def dots(d, x0, y0, cols, rows, gap, color):
    for i in range(cols):
        for j in range(rows):
            d.ellipse([x0 + i * gap, y0 + j * gap, x0 + i * gap + 4, y0 + j * gap + 4], fill=color)

def brush(d, x0, y0, x1, y1, color):
    n, pts = 16, []
    for i in range(n + 1):
        pts.append((x0 + (x1 - x0) * i / n + random.randint(-3, 3), y0 + random.randint(-6, 6)))
    pts.append((x1 + random.randint(0, 14), (y0 + y1) / 2))
    for i in range(n + 1):
        pts.append((x1 - (x1 - x0) * i / n + random.randint(-3, 3), y1 + random.randint(-6, 6)))
    pts.append((x0 - random.randint(0, 14), (y0 + y1) / 2))
    d.polygon(pts, fill=color)

def canvas(accent, variant):
    img = Image.new("RGBA", (W, H), (7, 8, 8, 255))
    gx = random.choice([W - 120, W - 220]); gy = random.choice([480, 620])
    glow(img, gx, gy, 330, accent, 70)
    glow(img, gx + 40, gy + 120, 200, accent, 45)
    d = ImageDraw.Draw(img)
    dots(d, 40, 330, 4, 8, 28, tuple(int(c * 0.35) for c in accent))
    dots(d, W - 160, 300, 5, 9, 28, tuple(int(c * 0.35) for c in accent))
    return img, d

def header(img, d, accent, category, show_swipe):
    cx, cy, r = 125, 125, 78
    glow(img, cx, cy, 90, accent, 60)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(10, 10, 10), outline=accent, width=5)
    f = head_font(84)
    w6 = ink(d, "6", f)[0]; w9 = ink(d, "9", f)[0]; tot = w6 + w9 + 6
    put(d, cx - tot / 2, cy - 52, "6", f, WHITE); put(d, cx - tot / 2 + w6 + 6, cy - 52, "9", f, accent)
    fs = body_font(20); t = ".CO.IN"
    d.text((cx - d.textlength(t, font=fs) / 2, cy + 36), t, font=fs, fill=WHITE)
    # series label
    label = f"{category} SERIES"; x = 245; fb = body_font(32)
    for ch in label:
        d.text((x, 92), ch, font=fb, fill=accent); x += d.textlength(ch, font=fb) + 4
    d.line([245, 145, 790, 145], fill=accent, width=2)
    for i, dx in enumerate([815, 845, 875]):
        d.ellipse([dx, 139, dx + 11, 150], fill=tuple(int(c * (1 - 0.25 * i)) for c in accent))
    if show_swipe:
        d.text((835, 105), "Swipe", font=body_font(34), fill=WHITE)
        sx, sy = 1005, 125
        d.ellipse([sx - 34, sy - 34, sx + 34, sy + 34], outline=accent, width=3)
        d.line([sx - 14, sy, sx + 14, sy], fill=WHITE, width=4)
        d.line([sx + 2, sy - 12, sx + 14, sy], fill=WHITE, width=4); d.line([sx + 2, sy + 12, sx + 14, sy], fill=WHITE, width=4)

def footer(d, accent, idx):
    f = body_font(34); y = 1272
    d.text((60, y), str(idx + 1), font=f, fill=accent)
    d.text((60 + d.textlength(str(idx + 1), font=f) + 8, y), f"/ {TOTAL}", font=f, fill=GREY)
    d.ellipse([200, y + 19, 210, y + 29], fill=accent)
    d.line([215, y + 24, 900, y + 24], fill=tuple(int(c * 0.6) for c in accent), width=2)
    x = W - 60 - d.textlength("69.CO.IN", font=f)
    d.text((x, y), "69", font=f, fill=accent)
    d.text((x + d.textlength("69", font=f), y), ".CO.IN", font=f, fill=WHITE)

def text_bar(d, x, y, text, max_w, max_size, fill_bar, fill_text, pad_x=34, pad_y=22, rough=True):
    f = fit(d, text, head_font, max_w - 2 * pad_x, max_size)
    w, h, _, _ = ink(d, text, f)
    if rough: brush(d, x, y, x + w + 2 * pad_x, y + h + 2 * pad_y, fill_bar)
    else: d.rectangle([x, y, x + w + 2 * pad_x, y + h + 2 * pad_y], fill=fill_bar)
    put(d, x + pad_x, y + pad_y, text, f, fill_text)
    return h + 2 * pad_y

def stamp(img, lines, accent, cx, cy, r, angle):
    layer = Image.new("RGBA", (2 * r + 40, 2 * r + 40), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
    c = r + 20
    ld.ellipse([c - r, c - r, c + r, c + r], fill=(8, 10, 8, 235), outline=accent, width=5)
    ld.ellipse([c - r + 12, c - r + 12, c + r - 12, c + r - 12], outline=accent, width=2)
    fs = [fit(ld, U(l), head_font, 2 * r - 70, 44, 20) for l in lines]
    hs = [ink(ld, U(l), f)[1] for l, f in zip(lines, fs)]
    y = c - (sum(hs) + 14 * (len(hs) - 1)) / 2
    for i, (l, f, h) in enumerate(zip(lines, fs, hs)):
        w = ink(ld, U(l), f)[0]
        put(ld, c - w / 2, y, U(l), f, WHITE if i == 0 else accent); y += h + 14
    layer = layer.rotate(angle, resample=Image.BICUBIC)
    img.alpha_composite(layer, (int(cx - c), int(cy - c)))

def strip(d, items, accent, y):
    colw = (W - 120) // 4
    for i, t in enumerate(items):
        x0 = 60 + i * colw
        if i: d.line([x0, y + 5, x0, y + 150], fill=(60, 62, 62), width=2)
        cx = x0 + colw // 2
        d.ellipse([cx - 27, y, cx + 27, y + 54], outline=accent, width=3)
        n = str(i + 1); fn = head_font(34); w = ink(d, n, fn)[0]
        put(d, cx - w / 2, y + 10, n, fn, accent)
        f = body_font(24)
        for k, ln in enumerate(wrap(d, t, f, colw - 24)[:3]):
            d.text((cx - d.textlength(ln, font=f) / 2, y + 70 + k * 30), ln, font=f, fill=WHITE)

def render_cover(post, accent):
    c = post["cover"]
    for scale in [1.0, 0.92, 0.85, 0.78, 0.7]:
        random.seed(hash(post["topic"]) % 10000)
        img, d = canvas(accent, 0)
        header(img, d, accent, post["category"], True); d = ImageDraw.Draw(img)
        y = 255
        for line in c["l1"][:2]:
            f = fit(d, U(line), head_font, 940, 124 * scale, 40)
            y += put(d, 60, y, U(line), f, WHITE) + 22
        y += 6 + text_bar(d, 30, y, U(c["bar"]), 960, 124 * scale, accent, BLACK) + 20
        f = fit(d, U(c["big"]), head_font, 940, 330 * scale, 100)
        y += put(d, 60, y, U(c["big"]), f, accent) + 36
        y += text_bar(d, 30, y, U(c["tag"]), 960, 96 * scale, WHITE, BLACK, pad_y=16) + 34
        fsub = body_font(int(38 * scale)); rule_top = y
        lines = wrap(d, c["sub"], fsub, 640)
        for ln in lines:
            d.text((90, y), ln, font=fsub, fill=WHITE); y += int(52 * scale)
        if c.get("sub_hl"):
            for ln in wrap(d, c["sub_hl"], fsub, 640):
                d.text((90, y), ln, font=fsub, fill=accent); y += int(52 * scale)
        d.rectangle([62, rule_top, 68, y], fill=accent)
        if y <= 1085: break
    stamp(img, c["stamp"][:3], accent, 880, 985, 128, 12)
    d = ImageDraw.Draw(img)
    strip(d, c["strip"], accent, 1105); footer(d, accent, 0)
    return img

def render_point(post, i, accent):
    pt = post["points"][i]
    random.seed(hash(post["topic"] + str(i)) % 10000)
    img, d = canvas(accent, 1)
    header(img, d, accent, post["category"], True); d = ImageDraw.Draw(img)
    ghost = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(ghost)
    gf = head_font(560); gt = f"0{i + 1}"; gw = ink(gd, gt, gf)[0]
    put(gd, W - gw - 30, 215, gt, gf, accent + (38,)); img.alpha_composite(ghost); d = ImageDraw.Draw(img)
    d.text((70, 262), f"POINT {i + 1} / 3", font=body_font(30), fill=accent)
    d.line([70, 305, 330, 305], fill=accent, width=3)
    y = 345
    lines = wrap(d, U(pt["head"]), head_font(112), 940)[:3]
    for ln in lines:
        f = fit(d, ln, head_font, 940, 112, 50)
        y += put(d, 70, y, ln, f, WHITE) + 22
    if pt.get("hl"):
        y += 4 + text_bar(d, 40, y, U(pt["hl"]), 940, 104, accent, BLACK) + 30
    fb = body_font(42); top = y
    for ln in wrap(d, pt["body"], fb, 880):
        d.text((100, y), ln, font=fb, fill=(232, 232, 235)); y += 62
    d.rectangle([70, top, 76, y - 8], fill=accent)
    if pt.get("example") and y < 1040:
        y += 26; fe = body_font(33); el = wrap(d, pt["example"], fe, 820)[:4]
        bh = 78 + len(el) * 46
        d.rounded_rectangle([70, y, W - 70, y + bh], radius=22, outline=accent, width=3, fill=(14, 18, 14))
        d.text((105, y + 20), "EXAMPLE", font=body_font(24), fill=accent)
        for k, ln in enumerate(el):
            d.text((105, y + 62 + k * 46), ln, font=fe, fill=WHITE)
    footer(d, accent, i + 1)
    return img

def render_close(post, accent):
    cl = post["close"]
    random.seed(hash(post["topic"] + "c") % 10000)
    img, d = canvas(accent, 2)
    header(img, d, accent, post["category"], False); d = ImageDraw.Draw(img)
    d.text((70, 262), "AAKHRI BAAT", font=body_font(30), fill=accent)
    d.line([70, 305, 330, 305], fill=accent, width=3)
    y = 350
    for ln in wrap(d, U(cl["head"]), head_font(120), 940)[:3]:
        f = fit(d, ln, head_font, 940, 120, 50); y += put(d, 70, y, ln, f, WHITE) + 24
    if cl.get("hl"):
        y += 4 + text_bar(d, 40, y, U(cl["hl"]), 940, 112, accent, BLACK) + 34
    fb = body_font(42); top = y
    for ln in wrap(d, cl["body"], fb, 880):
        d.text((100, y), ln, font=fb, fill=(232, 232, 235)); y += 62
    d.rectangle([70, top, 76, y - 8], fill=accent)
    y += 40
    y += text_bar(d, 40, y, U(cl["question"]), 960, 70, WHITE, BLACK, pad_y=22) + 40
    fbtn = body_font(38); t = f"FOLLOW  {HANDLE.upper()}"
    bw = int(d.textlength(t, font=fbtn)) + 90
    d.rounded_rectangle([70, y, 70 + bw, y + 92], radius=46, fill=accent)
    d.text((70 + 45, y + 24), t, font=fbtn, fill=BLACK)
    footer(d, accent, 4)
    return img

def render_all(post, folder):
    accent = ACCENTS[post["category"]]
    imgs = [render_cover(post, accent)] + [render_point(post, i, accent) for i in range(3)] + [render_close(post, accent)]
    names = []
    for i, im in enumerate(imgs):
        n = f"slide_{i + 1}.jpg"; im.convert("RGB").save(folder / n, "JPEG", quality=93); names.append(n)
    return names

def cmd_generate():
    POSTS.mkdir(exist_ok=True)
    existing = sorted(p for p in POSTS.iterdir() if p.is_dir())
    if existing and not json.loads((existing[-1] / "post.json").read_text(encoding="utf-8"))["published"]:
        shutil.rmtree(existing[-1]); existing = existing[:-1]   # unpublished leftover (e.g. dry run) -> redo
    if len(existing) >= MAX_POSTS:
        print(f"{MAX_POSTS} posts done. Nothing to do."); return
    post = make_post()
    n = len(existing) + 1
    folder = POSTS / f"{n:03d}"; folder.mkdir()
    names = render_all(post, folder)
    meta = {"topic": post["topic"], "category": post["category"],
            "caption": post["caption"] + f"\n\n{HANDLE}", "images": names, "published": False}
    (folder / "post.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Generated", folder)

# ---------- Instagram ----------
def api(method, path, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    r = requests.request(method, GRAPH + path, params=params if method == "GET" else None,
                         data=params if method == "POST" else None, timeout=60)
    if not r.ok:
        raise SystemExit(f"Instagram API error {r.status_code}: {r.text}")
    return r.json()

def wait_ready(cid):
    for _ in range(30):
        s = api("GET", cid, fields="status_code").get("status_code")
        if s == "FINISHED": return
        if s in ("ERROR", "EXPIRED"): raise SystemExit(f"Container {cid} status {s}")
        time.sleep(4)
    raise SystemExit("Timed out waiting for container")

def cmd_publish():
    pending = [p for p in sorted(POSTS.glob("*/post.json"))
               if not json.loads(p.read_text(encoding="utf-8"))["published"]]
    if not pending:
        print("Nothing to publish."); return
    pj = pending[0]; meta = json.loads(pj.read_text(encoding="utf-8"))
    repo, branch = os.environ["GITHUB_REPOSITORY"], os.getenv("GITHUB_REF_NAME", "main")
    uid = os.environ["IG_USER_ID"]
    kids = []
    for name in meta["images"]:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/posts/{pj.parent.name}/{name}"
        c = api("POST", f"{uid}/media", image_url=url, is_carousel_item="true")["id"]
        kids.append(c)
    for c in kids: wait_ready(c)
    car = api("POST", f"{uid}/media", media_type="CAROUSEL",
              children=",".join(kids), caption=meta["caption"])["id"]
    wait_ready(car)
    media = api("POST", f"{uid}/media_publish", creation_id=car)["id"]
    meta["published"] = True; meta["media_id"] = media
    pj.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Published", media)

if __name__ == "__main__":
    {"generate": cmd_generate, "publish": cmd_publish}[sys.argv[1]]()
