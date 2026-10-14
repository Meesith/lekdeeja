"""
เลขทะเบียนมงคล — ค้นหาเลขทะเบียนรถที่เหมาะกับเจ้าของ ด้วยศาสตร์ตัวเลข
Single-file Flask app (Tailwind via CDN)

รัน:   pip install flask && python app.py   แล้วเปิด http://127.0.0.1:5000

หลักการคำนวณ (เพื่อความบันเทิง/เป็นแนวทางประกอบการตัดสินใจ):
  1) ทักษา 8 ทิศ  – นับจากวันเกิดเป็น บริวาร, อายุ, เดช, ศรี, มูละ, อุตสาหะ, มนตรี, กาลกิณี
     แล้วแปลงเป็น "เลขดาว" 1-8 (อาทิตย์=1 ... เสาร์=7, ราหู=8)  เลข 9 = ก้าวหน้า, 0 = กลาง
  2) เลขประจำตัว  – รวม (เลขวัน + เดือน + ผลรวมเลขปีพ.ศ.) จนเหลือหลักเดียว
  3) ให้คะแนนเลขทะเบียนจาก  ค่าเฉลี่ยเลขแต่ละตัว + ผลรวมของเลขทะเบียน + คู่เลขที่ติดกัน
"""
import heapq

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# ---------------------------------------------------------------- ข้อมูลพื้นฐาน
# (เลขดาว, ชื่อวัน, emoji)
DAYS = [
    (1, "อาทิตย์", "☀️"),
    (2, "จันทร์", "🌙"),
    (3, "อังคาร", "🔥"),
    (4, "พุธ (กลางวัน)", "🌿"),
    (5, "พฤหัสบดี", "📜"),
    (6, "ศุกร์", "💎"),
    (7, "เสาร์", "🪐"),
    (8, "พุธ (กลางคืน)", "🌑"),
]
DAY_NAME = {n: name for n, name, _ in DAYS}
PLANET = {1: "อาทิตย์", 2: "จันทร์", 3: "อังคาร", 4: "พุธ",
          5: "พฤหัสบดี", 6: "ศุกร์", 7: "เสาร์", 8: "ราหู"}
MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
          "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

# ลำดับวงจรทักษา: อาทิตย์ จันทร์ อังคาร พุธ พฤหัส เสาร์ ราหู ศุกร์
TAKSA_CYCLE = [1, 2, 3, 4, 5, 7, 8, 6]
# (ชื่อ, น้ำหนัก, ความหมาย)
TAKSA_ROLES = [
    ("บริวาร", 1, "ลูกน้อง เพื่อนฝูง ผู้ช่วยเหลือ"),
    ("อายุ", 2, "สุขภาพ ความยืนยาว ความปลอดภัย"),
    ("เดช", 3, "อำนาจ บารมี การยอมรับ"),
    ("ศรี", 3, "โชคลาภ เสน่ห์ ความเป็นสิริมงคล"),
    ("มูละ", 3, "ทรัพย์สิน รากฐานมั่นคง"),
    ("อุตสาหะ", 1, "ความขยัน ความพยายาม"),
    ("มนตรี", 2, "ผู้ใหญ่อุปถัมภ์ ผู้มีพระคุณ"),
    ("กาลกิณี", -5, "อุปสรรค ความเสื่อม ควรหลีกเลี่ยง"),
]
SPECIAL = {
    9: ("ก้าวหน้า", 2, "เลขเก้า ความก้าวหน้า เลื่อนขั้น"),
    0: ("กลาง", 0, "เลขกลาง ไม่เสริมไม่ลด"),
}

GOOD_PAIRS = {int(x) for x in (
    "14 15 16 19 23 24 26 29 35 36 39 41 42 45 46 49 51 53 54 56 59 "
    "61 62 63 64 65 69 91 92 93 94 95 96 99").split()}
BAD_PAIRS = {int(x) for x in (
    "13 17 18 27 31 37 38 47 48 57 58 71 72 73 74 75 78 81 83 84 85 87").split()}

W_MIN, W_MAX = -5.0, 4.5  # ช่วงน้ำหนักเลขหนึ่งตัว (รวมโบนัสเลขประจำตัว)
LIFE_BONUS = 1.5


def reduce9(n: int) -> int:
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n


def chip_class(w: float) -> str:
    if w >= 3:
        return "bg-emerald-500/20 text-emerald-300 border-emerald-400/50"
    if w >= 2:
        return "bg-sky-500/20 text-sky-300 border-sky-400/50"
    if w >= 1:
        return "bg-amber-500/15 text-amber-200 border-amber-400/40"
    if w < 0:
        return "bg-rose-500/20 text-rose-300 border-rose-400/60"
    return "bg-slate-500/20 text-slate-300 border-slate-400/40"


# ---------------------------------------------------------------- โปรไฟล์เจ้าของ
def build_profile(day: int, month: int, year_be: int) -> dict:
    start = TAKSA_CYCLE.index(day)
    roles = {}
    for i, (name, w, desc) in enumerate(TAKSA_ROLES):
        roles[TAKSA_CYCLE[(start + i) % 8]] = (name, w, desc)
    for d, (name, w, desc) in SPECIAL.items():
        roles[d] = (name, w, desc)

    life = reduce9(day + month + sum(int(c) for c in str(year_be)))
    year_no = reduce9(sum(int(c) for c in str(year_be)))

    weight = {}
    for d in range(10):
        w = roles[d][1]
        if d == life:
            w += LIFE_BONUS
        weight[d] = w

    bad = [d for d, r in roles.items() if r[1] < 0]
    lucky = sorted((d for d in range(1, 9) if weight[d] >= 3), key=lambda d: -weight[d])
    return {
        "day": day, "month": month, "year": year_be,
        "roles": roles, "weight": weight,
        "life": life, "year_no": year_no,
        "bad": bad, "lucky": lucky,
    }


def _scale(x: float) -> float:
    return max(0.0, min(100.0, (x - W_MIN) / (W_MAX - W_MIN) * 100))


def grade_of(score: int):
    if score >= 80:
        return "มงคลยิ่ง", "bg-emerald-400 text-emerald-950"
    if score >= 65:
        return "ดี", "bg-sky-400 text-sky-950"
    if score >= 50:
        return "พอใช้", "bg-amber-300 text-amber-950"
    return "ควรเลี่ยง", "bg-rose-400 text-rose-950"


def score_number(num: str, p: dict) -> int:
    """คะแนนแบบเร็ว (ใช้ตอนค้นหา)"""
    w = p["weight"]
    digits = [int(c) for c in num]
    dc = _scale(sum(w[d] for d in digits) / len(digits))
    total = reduce9(sum(digits))
    sc = _scale(w[total])
    pairs = [int(num[i:i + 2]) for i in range(len(num) - 1)]
    if pairs:
        g = sum(1 for x in pairs if x in GOOD_PAIRS)
        b = sum(1 for x in pairs if x in BAD_PAIRS)
        pc = max(0.0, min(100.0, 50 + 50 * (g - b) / len(pairs)))
    else:
        pc = 50.0
    kcount = sum(1 for d in digits if d in p["bad"])
    raw = 0.40 * dc + 0.35 * sc + 0.25 * pc - 12 * kcount
    return int(round(max(0.0, min(100.0, raw))))


def analyze(num: str, p: dict) -> dict:
    digits = [int(c) for c in num]
    score = score_number(num, p)
    label, gcls = grade_of(score)
    chips = []
    for d in digits:
        name, _, desc = p["roles"][d]
        chips.append({"d": d, "role": name, "desc": desc, "cls": chip_class(p["weight"][d])})
    total_raw = sum(digits)
    total = reduce9(total_raw)
    t_name, _, t_desc = p["roles"][total]
    pairs = []
    for i in range(len(num) - 1):
        v = int(num[i:i + 2])
        kind = "good" if v in GOOD_PAIRS else "bad" if v in BAD_PAIRS else "neutral"
        pairs.append({"p": num[i:i + 2], "kind": kind})

    notes = []
    k = [d for d in digits if d in p["bad"]]
    if k:
        notes.append(("bad", f"มีเลขกาลกิณี ({p['bad'][0]}) {len(k)} ตัว ซึ่งขัดกับดวงวัน{DAY_NAME[p['day']]}"))
    else:
        notes.append(("good", f"ไม่มีเลขกาลกิณี ({p['bad'][0]}) ปลอดจากเลขที่ขัดดวง"))
    if p["life"] in digits:
        notes.append(("good", f"มีเลขประจำตัว {p['life']} ช่วยเสริมพลังส่วนบุคคล"))
    top = [c for c in chips if c["role"] in ("เดช", "ศรี", "มูละ")]
    if top:
        names = "/".join(sorted({c["role"] for c in top}))
        notes.append(("good", f"มีเลขกลุ่มพลังเด่น ({names}) {len(top)} ตัว"))
    pg = sum(1 for x in pairs if x["kind"] == "good")
    pb = sum(1 for x in pairs if x["kind"] == "bad")
    if pg:
        notes.append(("good", f"คู่เลขมงคล {pg} คู่"))
    if pb:
        notes.append(("bad", f"คู่เลขที่ควรระวัง {pb} คู่"))
    notes.append(("good" if p["weight"][total] >= 2 else "bad" if p["weight"][total] < 0 else "neutral",
                  f"ผลรวม {total_raw} → {total} ({t_name}: {t_desc})"))

    return {
        "num": num, "score": score, "label": label, "gcls": gcls,
        "chips": chips, "total_raw": total_raw, "total": total,
        "total_role": t_name, "total_cls": chip_class(p["weight"][total]),
        "pairs": pairs, "notes": notes,
    }


# ---------------------------------------------------------------- ค้นหา
def only_digits(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def search(p: dict, length: int, limit: int, starts="", ends="", must="", avoid="",
           skip_bad=True) -> list:
    lo = 1 if length == 1 else 10 ** (length - 1)
    hi = 10 ** length
    avoid_set = set(avoid)
    if skip_bad:
        avoid_set |= {str(d) for d in p["bad"]}
    must_set = set(must)

    def candidates():
        for n in range(lo, hi):
            s = str(n)
            if starts and not s.startswith(starts):
                continue
            if ends and not s.endswith(ends):
                continue
            if avoid_set and avoid_set & set(s):
                continue
            if must_set and not must_set <= set(s):
                continue
            yield s

    best = heapq.nlargest(limit, ((score_number(s, p), -int(s), s) for s in candidates()))
    return [analyze(s, p) for _, _, s in best]


def parse_request(args):
    """อ่านค่าจากฟอร์ม คืน (values, errors)"""
    v = {
        "day": args.get("day", ""), "month": args.get("month", ""), "year": args.get("year", ""),
        "length": args.get("length", "4"), "letters": (args.get("letters", "") or "").strip()[:4],
        "starts": only_digits(args.get("starts"))[:3], "ends": only_digits(args.get("ends"))[:3],
        "must": only_digits(args.get("must"))[:4], "avoid": only_digits(args.get("avoid"))[:6],
        "check": only_digits(args.get("check"))[:4], "limit": args.get("limit", "20"),
        "skip_bad": args.get("skip_bad", "1" if not args else "") == "1",
    }
    errors = []
    submitted = bool(args.get("day") or args.get("month") or args.get("year"))
    if not submitted:
        return v, errors, False
    try:
        day = int(v["day"])
        assert day in DAY_NAME
    except (ValueError, AssertionError):
        errors.append("กรุณาเลือกวันเกิด")
        day = None
    try:
        month = int(v["month"])
        assert 1 <= month <= 12
    except (ValueError, AssertionError):
        errors.append("กรุณาเลือกเดือนเกิด")
        month = None
    try:
        year = int(v["year"])
        if year < 2400:  # ผู้ใช้อาจกรอก ค.ศ.
            year += 543
        assert 2400 <= year <= 2600
    except (ValueError, AssertionError):
        errors.append("ปีเกิดไม่ถูกต้อง (กรอก พ.ศ. เช่น 2540)")
        year = None
    try:
        length = int(v["length"])
        assert 1 <= length <= 4
    except (ValueError, AssertionError):
        length = 4
    try:
        limit = max(5, min(50, int(v["limit"])))
    except ValueError:
        limit = 20
    v.update(day_n=day, month_n=month, year_n=year, length_n=length, limit_n=limit)
    return v, errors, True


# ---------------------------------------------------------------- เทมเพลต
PAGE = r"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>เลขทะเบียนมงคล — ศาสตร์ตัวเลขเฉพาะบุคคล</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script>
  tailwind.config = { theme: { extend: { fontFamily: { sans: ['Prompt', 'sans-serif'] } } } }
</script>
<style>
  body { background: radial-gradient(1200px 600px at 80% -10%, #3b2a6b55, transparent),
                     radial-gradient(900px 500px at -10% 10%, #b4830955, transparent), #0b1020; }
  .plate { font-family: 'Prompt', sans-serif; letter-spacing: .04em; }
</style>
</head>
<body class="min-h-screen font-sans text-slate-200 antialiased">
{% macro card(r, big, rank=None) %}
<article class="rounded-2xl border border-white/10 bg-white/5 p-4 sm:p-5 {{ 'sm:col-span-2' if big }}">
  <div class="flex items-center justify-between gap-3">
    <div class="plate flex items-center gap-2 rounded-lg border-[3px] border-slate-800 bg-white px-4 py-1.5 text-slate-900 shadow">
      {% if v.letters %}<span class="text-xl font-semibold">{{ v.letters }}</span>{% endif %}
      <span class="text-3xl font-bold">{{ r.num }}</span>
    </div>
    <div class="text-right">
      <div class="text-3xl font-bold leading-none">{{ r.score }}<span class="text-sm text-slate-400 font-normal">/100</span></div>
      <span class="mt-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold {{ r.gcls }}">{{ r.label }}</span>
    </div>
  </div>
  <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
    <div class="h-full rounded-full bg-gradient-to-r from-amber-300 to-emerald-400" style="width: {{ r.score }}%"></div>
  </div>
  <div class="mt-3 flex flex-wrap items-center gap-1.5">
    {% for c in r.chips %}
    <span title="{{ c.desc }}" class="rounded-lg border px-2 py-1 text-xs {{ c.cls }}"><b class="text-sm">{{ c.d }}</b> {{ c.role }}</span>
    {% endfor %}
    <span class="ml-1 text-slate-500">→</span>
    <span class="rounded-lg border px-2 py-1 text-xs {{ r.total_cls }}">ผลรวม {{ r.total_raw }}={{ r.total }} {{ r.total_role }}</span>
  </div>
  {% if big or r.pairs|length > 0 %}
  <div class="mt-2 flex flex-wrap gap-1 text-xs">
    {% for pr in r.pairs %}
    <span class="rounded px-1.5 py-0.5 {{ 'bg-emerald-500/20 text-emerald-300' if pr.kind == 'good' else 'bg-rose-500/20 text-rose-300' if pr.kind == 'bad' else 'bg-white/5 text-slate-400' }}">{{ pr.p }}</span>
    {% endfor %}
  </div>
  {% endif %}
  {% if big %}
  <ul class="mt-3 space-y-1 text-sm">
    {% for kind, text in r.notes %}
    <li class="{{ 'text-emerald-300' if kind == 'good' else 'text-rose-300' if kind == 'bad' else 'text-slate-300' }}">
      {{ '✓' if kind == 'good' else '✗' if kind == 'bad' else '•' }} {{ text }}</li>
    {% endfor %}
  </ul>
  {% endif %}
</article>
{% endmacro %}
<div class="mx-auto max-w-5xl px-4 py-8 sm:py-12">

  <header class="text-center mb-8">
    <p class="text-amber-300/80 text-sm tracking-widest">ศาสตร์ตัวเลข · ทักษา · เลขประจำตัว</p>
    <h1 class="mt-2 text-3xl sm:text-5xl font-bold bg-gradient-to-r from-amber-200 via-amber-400 to-orange-300 bg-clip-text text-transparent">
      ค้นหาเลขทะเบียนรถมงคล
    </h1>
    <p class="mt-3 text-slate-400">ใส่วัน เดือน ปีเกิด แล้วให้ตัวเลขเลือกทะเบียนที่เหมาะกับคุณ</p>
  </header>

  <form method="get" action="/" class="rounded-2xl border border-white/10 bg-white/5 backdrop-blur p-5 sm:p-7 space-y-6">

    <fieldset>
      <legend class="text-sm font-medium text-amber-200 mb-2">1. วันที่เกิด</legend>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {% for n, name, icon in days %}
        <label class="cursor-pointer">
          <input type="radio" name="day" value="{{ n }}" class="peer sr-only" {{ 'checked' if v.day|string == n|string }}>
          <span class="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm transition
                       hover:bg-white/10 peer-checked:bg-amber-400 peer-checked:text-slate-900 peer-checked:font-semibold peer-focus-visible:ring-2 peer-focus-visible:ring-amber-300">
            <span>{{ icon }}</span>{{ name }}
          </span>
        </label>
        {% endfor %}
      </div>
    </fieldset>

    <div class="grid sm:grid-cols-2 gap-4">
      <label class="block">
        <span class="text-sm font-medium text-amber-200">2. เดือนเกิด</span>
        <select name="month" class="mt-2 w-full rounded-xl bg-slate-900 border border-white/10 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-amber-300">
          <option value="">— เลือกเดือน —</option>
          {% for m in months %}
          <option value="{{ loop.index }}" {{ 'selected' if v.month|string == loop.index|string }}>{{ m }}</option>
          {% endfor %}
        </select>
      </label>
      <label class="block">
        <span class="text-sm font-medium text-amber-200">3. ปีเกิด (พ.ศ.)</span>
        <input type="number" name="year" value="{{ v.year }}" placeholder="เช่น 2540" min="1900" max="2600"
               class="mt-2 w-full rounded-xl bg-slate-900 border border-white/10 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-amber-300">
      </label>
    </div>

    <details class="group rounded-xl border border-white/10 bg-black/20 p-4" {{ 'open' if adv_open }}>
      <summary class="cursor-pointer text-sm font-medium text-amber-200 select-none">ตัวเลือกเพิ่มเติม (ไม่บังคับ)</summary>
      <div class="mt-4 grid sm:grid-cols-3 gap-4 text-sm">
        <label class="block">จำนวนหลักตัวเลข
          <select name="length" class="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2">
            {% for k in (4, 3, 2, 1) %}<option value="{{ k }}" {{ 'selected' if v.length|string == k|string }}>{{ k }} หลัก</option>{% endfor %}
          </select>
        </label>
        <label class="block">จำนวนผลลัพธ์
          <select name="limit" class="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2">
            {% for k in (10, 20, 30, 50) %}<option value="{{ k }}" {{ 'selected' if v.limit|string == k|string }}>{{ k }} เลข</option>{% endfor %}
          </select>
        </label>
        <label class="block">อักษรนำ (แสดงบนป้าย)
          <input name="letters" value="{{ v.letters }}" maxlength="4" placeholder="เช่น กข"
                 class="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2">
        </label>
        <label class="block">ขึ้นต้นด้วย
          <input name="starts" value="{{ v.starts }}" inputmode="numeric" placeholder="เช่น 9"
                 class="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2">
        </label>
        <label class="block">ลงท้ายด้วย
          <input name="ends" value="{{ v.ends }}" inputmode="numeric" placeholder="เช่น 99"
                 class="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2">
        </label>
        <label class="block">ต้องมีเลข (ทุกตัวที่ใส่)
          <input name="must" value="{{ v.must }}" inputmode="numeric" placeholder="เช่น 59"
                 class="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2">
        </label>
        <label class="block">ไม่เอาเลข
          <input name="avoid" value="{{ v.avoid }}" inputmode="numeric" placeholder="เช่น 4"
                 class="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2">
        </label>
        <label class="block sm:col-span-2">ตรวจเลขทะเบียนที่มีอยู่ (เช่น ทะเบียนปัจจุบัน)
          <input name="check" value="{{ v.check }}" inputmode="numeric" maxlength="4" placeholder="เช่น 1234"
                 class="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2">
        </label>
        <label class="flex items-center gap-2 sm:col-span-3">
          <input type="checkbox" name="skip_bad" value="1" {{ 'checked' if v.skip_bad }} class="h-4 w-4 accent-amber-400">
          ตัดเลขกาลกิณีของคุณออกจากผลค้นหาอัตโนมัติ
        </label>
      </div>
    </details>

    {% if errors %}
    <ul class="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-rose-200 text-sm list-disc list-inside">
      {% for e in errors %}<li>{{ e }}</li>{% endfor %}
    </ul>
    {% endif %}

    <button class="w-full rounded-xl bg-gradient-to-r from-amber-300 to-orange-400 py-3 text-lg font-semibold text-slate-900 shadow-lg shadow-amber-500/20 hover:brightness-110 active:scale-[.99] transition">
      ✨ ค้นหาเลขมงคลของฉัน
    </button>
  </form>

  {% if profile %}
  <section class="mt-8 grid md:grid-cols-3 gap-4">
    <div class="md:col-span-1 rounded-2xl border border-white/10 bg-white/5 p-5">
      <h2 class="font-semibold text-amber-200">ดวงตัวเลขของคุณ</h2>
      <p class="mt-1 text-sm text-slate-400">เกิดวัน{{ day_name }} เดือน{{ month_name }} พ.ศ. {{ profile.year }}</p>
      <dl class="mt-4 space-y-3 text-sm">
        <div class="flex justify-between"><dt class="text-slate-400">เลขประจำตัว</dt>
          <dd class="text-2xl font-bold text-amber-300">{{ profile.life }}</dd></div>
        <div class="flex justify-between"><dt class="text-slate-400">เลขปีเกิด</dt>
          <dd class="text-xl font-semibold">{{ profile.year_no }}</dd></div>
        <div class="flex justify-between items-center"><dt class="text-slate-400">เลขเสริมดวง</dt>
          <dd class="flex gap-1.5">
            {% for d in profile.lucky %}<span class="grid h-8 w-8 place-items-center rounded-lg border {{ chip(d) }} font-semibold">{{ d }}</span>{% endfor %}
            <span class="grid h-8 w-8 place-items-center rounded-lg border {{ chip(9) }} font-semibold">9</span>
          </dd></div>
        <div class="flex justify-between items-center"><dt class="text-slate-400">เลขกาลกิณี (เลี่ยง)</dt>
          <dd>{% for d in profile.bad %}<span class="grid h-8 w-8 place-items-center rounded-lg border {{ chip(d) }} font-semibold">{{ d }}</span>{% endfor %}</dd></div>
      </dl>
    </div>

    <div class="md:col-span-2 rounded-2xl border border-white/10 bg-white/5 p-5">
      <h2 class="font-semibold text-amber-200">ความหมายเลขแต่ละตัวสำหรับคุณ</h2>
      <div class="mt-3 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {% for d in range(1, 10) %}
        <div class="flex items-start gap-2">
          <span class="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md border {{ chip(d) }} text-xs font-semibold">{{ d }}</span>
          <span><b class="font-medium">{{ profile.roles[d][0] }}</b>
            <span class="text-slate-400"> — {{ profile.roles[d][2] }}</span></span>
        </div>
        {% endfor %}
      </div>
    </div>
  </section>

  {% if checked %}
  <section class="mt-8">
    <h2 class="text-xl font-semibold text-amber-200 mb-3">ผลตรวจเลขทะเบียน {{ checked.num }}</h2>
    {{ card(checked, True) }}
  </section>
  {% endif %}

  <section class="mt-8">
    <h2 class="text-xl font-semibold text-amber-200 mb-1">เลขทะเบียนที่เหมาะกับคุณ</h2>
    <p class="text-sm text-slate-400 mb-4">เรียงจากคะแนนสูงสุด · {{ results|length }} อันดับ ({{ v.length_n }} หลัก)</p>
    {% if results %}
    <div class="grid sm:grid-cols-2 gap-4">
      {% for r in results %}{{ card(r, False, loop.index) }}{% endfor %}
    </div>
    {% else %}
    <p class="rounded-xl border border-white/10 bg-white/5 p-6 text-center text-slate-400">ไม่พบเลขที่ตรงเงื่อนไข ลองลดตัวกรองลง</p>
    {% endif %}
  </section>
  {% endif %}

  <footer class="mt-12 text-center text-xs text-slate-500 leading-relaxed">
    ผลวิเคราะห์เป็นความเชื่อทางโหราศาสตร์/ศาสตร์ตัวเลข เพื่อความบันเทิงและเป็นแนวทางประกอบเท่านั้น<br>
    การประมูลหรือจองทะเบียนจริงต้องตรวจสอบเลขที่ว่างกับกรมการขนส่งทางบกอีกครั้ง
  </footer>
</div>

</body>
</html>"""


@app.route("/")
def index():
    v, errors, submitted = parse_request(request.args)
    ctx = dict(days=DAYS, months=MONTHS, v=v, errors=errors, profile=None,
               results=[], checked=None, chip=lambda d: "", day_name="", month_name="",
               adv_open=any(v[k] for k in ("starts", "ends", "must", "avoid", "check", "letters"))
               or v["length"] != "4")
    if submitted and not errors:
        p = build_profile(v["day_n"], v["month_n"], v["year_n"])
        ctx.update(
            profile=p,
            chip=lambda d: chip_class(p["weight"][d]),
            day_name=DAY_NAME[p["day"]], month_name=MONTHS[p["month"] - 1],
            results=search(p, v["length_n"], v["limit_n"], v["starts"], v["ends"],
                           v["must"], v["avoid"], v["skip_bad"]),
            checked=analyze(v["check"], p) if v["check"] and v["check"][0] != "0" else None,
        )
        v["year"] = p["year"]
    return render_template_string(PAGE, **ctx)


@app.route("/api/search")
def api_search():
    v, errors, submitted = parse_request(request.args)
    if not submitted or errors:
        return jsonify(error=errors or ["ต้องระบุ day, month, year"]), 400
    p = build_profile(v["day_n"], v["month_n"], v["year_n"])
    results = search(p, v["length_n"], v["limit_n"], v["starts"], v["ends"], v["must"],
                     v["avoid"], v["skip_bad"])
    return jsonify(
        profile={"day": DAY_NAME[p["day"]], "month": p["month"], "year": p["year"],
                 "life_number": p["life"], "lucky": p["lucky"] + [9], "avoid": p["bad"]},
        results=[{"number": r["num"], "score": r["score"], "grade": r["label"],
                  "sum": r["total"]} for r in results],
    )


if __name__ == "__main__":
    app.run(debug=True)
