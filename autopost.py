"""
69.co.in - Hindi knowledge carousel auto-poster (Instagram Graph API).

Usage:
  python autopost.py generate   # Claude writes a post + slide images are created
  python autopost.py publish    # latest unpublished post goes to Instagram
Env vars: GEMINI_API_KEY (free) or ANTHROPIC_API_KEY, IG_USER_ID, IG_ACCESS_TOKEN (secrets);
          MAX_POSTS (default 30), CLAUDE_MODEL, GRAPH_VERSION (optional)
"""
import os, sys, json, time, random, pathlib
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).parent
POSTS = ROOT / "posts"
MAX_POSTS = int(os.getenv("MAX_POSTS", "30"))
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
HANDLE = "@69.co.in"
GV = os.getenv("GRAPH_VERSION", "").strip()
GRAPH = "https://graph.facebook.com/" + (GV + "/" if GV else "")
W, H = 1080, 1350

FONTS_BOLD = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
PALETTES = [  # (top color, bottom color, accent)
    ((15, 23, 42), (30, 41, 59), (250, 204, 21)),
    ((24, 24, 27), (63, 63, 70), (52, 211, 153)),
    ((30, 27, 75), (49, 46, 129), (251, 146, 60)),
    ((12, 74, 110), (7, 89, 133), (253, 224, 71)),
]
SEEDS = [
    "log garib kyu rah jate hain", "amir log naukri pe depend kyu nahi rehte",
    "AI se paisa bachane ke tareeke", "dimaag paisa jodne se kaise rokta hai",
    "phone se shuru hone wale business", "paisa kamana vs paisa rakhna",
    "log business shuru karne se kyu darte hain", "habits jo amir banati hain",
]

def load_font(size):
    for p in FONTS_BOLD:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise SystemExit("No Devanagari font found. Install fonts-noto-core.")

def history_topics():
    out = []
    for f in sorted(POSTS.glob("*/post.json")):
        out.append(json.loads(f.read_text(encoding="utf-8")).get("topic", ""))
    return out

# ---------- Claude ----------
SYSTEM = """You write Instagram carousel posts in simple, natural HINDI (Devanagari script)
for the page 69.co.in. Topics: money, psychology, business, AI - mixed as curiosity questions.
Rules:
- Exactly 7 slides: slide 1 = a curiosity hook question, slides 2-6 = one clear idea each,
  slide 7 = short call to action (follow + a question for comments).
- Each slide max 28 words. Simple everyday Hindi, short sentences.
- No guaranteed-income claims, no specific stock/crypto/investment advice, no invented
  statistics, no fake studies or quotes. Stay general and honest.
- Caption: 2-3 lines in Hindi + 8 relevant hashtags.
Return ONLY JSON: {"topic": str, "slides": [str x7], "caption": str}"""

def llm_json(system, user):
    """Uses Gemini (free tier) if GEMINI_API_KEY is set, else Claude."""
    if os.getenv("GEMINI_API_KEY"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json"}}
        for attempt in range(4):  # free tier can rate-limit; retry
            r = requests.post(url, json=body, timeout=120,
                              headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
            if r.status_code in (429, 503):
                time.sleep(20 * (attempt + 1)); continue
            if not r.ok:
                raise SystemExit(f"Gemini API error {r.status_code}: {r.text}")
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            break
        else:
            raise SystemExit("Gemini API busy/rate-limited, try again later.")
    else:
        import anthropic
        r = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=1500, system=system,
                                   messages=[{"role": "user", "content": user}])
        txt = "".join(b.text for b in r.content if b.type == "text")
    txt = txt.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(txt)

def make_post():
    done = history_topics()
    for attempt in range(4):
        seed = random.choice(SEEDS)
        post = llm_json(SYSTEM,
            f"Inspiration (you may choose a different angle): {seed}\n"
            f"Do NOT repeat these earlier topics: {done}")
        assert len(post["slides"]) == 7, "need 7 slides"
        review = llm_json(
            'You are a strict fact-checker. Return ONLY JSON {"ok": bool, "reason": str}. '
            "ok=false if the text has false or doubtful facts, guaranteed-income promises, "
            "investment advice, or is not understandable Hindi.",
            json.dumps(post, ensure_ascii=False))
        if review.get("ok"):
            return post
        print("Rejected by reviewer:", review.get("reason"))
    raise SystemExit("Could not produce a safe post after 4 tries.")

# ---------- Images ----------
def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = word
    if cur: lines.append(cur)
    return lines

def render_slide(text, idx, total, palette, path):
    top, bot, accent = palette
    img = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    margin = 90
    max_w, max_h = W - 2 * margin, H - 480
    size = 96 if idx == 0 else 76
    while size > 36:
        font = load_font(size)
        lines = wrap(d, text, font, max_w)
        lh = int(size * 1.6)
        if len(lines) * lh <= max_h:
            break
        size -= 4
    block = len(lines) * lh
    y = (H - block) // 2
    for ln in lines:
        d.text((margin, y), ln, font=font, fill=(255, 255, 255))
        y += lh
    d.rectangle([margin, 150, margin + 120, 162], fill=accent)
    small = load_font(38)
    d.text((margin, H - 140), HANDLE, font=small, fill=accent)
    d.text((W - margin - 110, H - 140), f"{idx + 1}/{total}", font=small, fill=(200, 200, 200))
    img.save(path, "JPEG", quality=92)

def cmd_generate():
    POSTS.mkdir(exist_ok=True)
    existing = sorted(p for p in POSTS.iterdir() if p.is_dir())
    if len(existing) >= MAX_POSTS:
        print(f"{MAX_POSTS} posts done. Nothing to do."); return
    if existing and not json.loads((existing[-1] / "post.json").read_text())["published"]:
        print("Previous post is still unpublished; skipping generate."); return
    post = make_post()
    n = len(existing) + 1
    folder = POSTS / f"{n:03d}"; folder.mkdir()
    palette = random.choice(PALETTES)
    names = []
    for i, s in enumerate(post["slides"]):
        name = f"slide_{i + 1}.jpg"
        render_slide(s, i, len(post["slides"]), palette, folder / name)
        names.append(name)
    meta = {"topic": post["topic"], "caption": post["caption"] + f"\n\n{HANDLE}",
            "images": names, "published": False}
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
  
