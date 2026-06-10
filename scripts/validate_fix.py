# -*- coding: utf-8 -*-
"""Validate and fix poetry-cloud data files, then generate data.js."""
import json
import re
import sys
from collections import Counter, OrderedDict

DATA_DIR = "/Users/max/Documents/poetry-cloud/data"
CHARSET = DATA_DIR + "/charset.txt"
FAMOUS = DATA_DIR + "/famous.json"
DATAJS = "/Users/max/Documents/poetry-cloud/data.js"

fixes = []
HAN = lambda ch: '一' <= ch <= '鿿'

# ---------- Step 1: validate famous.json ----------
with open(FAMOUS, encoding="utf-8") as f:
    famous = json.load(f)
print(f"famous.json parsed: {len(famous)} poems")

problems = []
for i, p in enumerate(famous):
    ident = f"#{i} {p.get('title','?')}/{p.get('author','?')}"
    for k in ("title", "author", "dynasty", "note"):
        v = p.get(k)
        if not isinstance(v, str) or not v.strip():
            problems.append(f"{ident}: field {k} missing/empty -> {v!r}")
    lines = p.get("lines")
    if not isinstance(lines, list) or len(lines) != 4:
        problems.append(f"{ident}: lines count = {len(lines) if isinstance(lines,list) else 'N/A'}")
        continue
    for j, ln in enumerate(lines):
        if not isinstance(ln, str) or len(ln) != 5:
            problems.append(f"{ident}: line {j} length {len(ln) if isinstance(ln,str) else 'N/A'}: {ln!r}")
        else:
            bad = [c for c in ln if not HAN(c)]
            if bad:
                problems.append(f"{ident}: line {j} non-han chars {bad} in {ln!r}")

for pr in problems:
    print("PROBLEM:", pr)

# duplicate poem text (joined 4 lines)
seen_text = {}
dup_text_idx = []
for i, p in enumerate(famous):
    key = "".join(p.get("lines", []))
    if key in seen_text:
        dup_text_idx.append((i, seen_text[key], key))
    else:
        seen_text[key] = i
for i, first, key in dup_text_idx:
    print(f"DUP TEXT: #{i} {famous[i]['title']} duplicates #{first} {famous[first]['title']}")

# duplicate title+author
seen_ta = {}
dup_ta_idx = []
for i, p in enumerate(famous):
    key = (p.get("title"), p.get("author"))
    if key in seen_ta:
        dup_ta_idx.append((i, seen_ta[key], key))
    else:
        seen_ta[key] = i
for i, first, key in dup_ta_idx:
    print(f"DUP TITLE+AUTHOR: #{i} {key} duplicates #{first}")

# Remove duplicates (keep first occurrence)
remove = sorted({i for i, _, _ in dup_text_idx} | {i for i, _, _ in dup_ta_idx}, reverse=True)
for i in remove:
    p = famous.pop(i)
    fixes.append(f"删除重复诗 #{i}《{p['title']}》({p['author']})")

# ---------- Step 2: spot-check canonical texts + note length ----------
CANON = {
    "静夜思": ["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"],
    "登鹳雀楼": ["白日依山尽", "黄河入海流", "欲穷千里目", "更上一层楼"],
    "春晓": ["春眠不觉晓", "处处闻啼鸟", "夜来风雨声", "花落知多少"],
    "江雪": ["千山鸟飞绝", "万径人踪灭", "孤舟蓑笠翁", "独钓寒江雪"],
}
found_canon = set()
for p in famous:
    t = p.get("title")
    if t in CANON:
        found_canon.add(t)
        if p["lines"] != CANON[t]:
            print(f"CANON MISMATCH 《{t}》: {p['lines']} -> {CANON[t]}")
            p["lines"] = CANON[t]
            fixes.append(f"修正《{t}》文本为标准版本")
        else:
            print(f"CANON OK 《{t}》")
for t in CANON:
    if t not in found_canon:
        print(f"CANON MISSING 《{t}》 not found in famous.json")

# note length <= 25
for p in famous:
    n = p.get("note", "")
    if len(n) > 25:
        print(f"NOTE TOO LONG ({len(n)}) 《{p['title']}》: {n}")

# ---------- Step 3: validate charset.txt ----------
with open(CHARSET, encoding="utf-8") as f:
    raw = f.read()
content = raw.rstrip("\n")
if "\n" in content or "\r" in content:
    print("CHARSET: multiple lines detected, joining")
    content = content.replace("\r", "").replace("\n", "")
    fixes.append("charset.txt 多行合并为单行")
if raw != content:
    # trailing newline present; we'll rewrite without it (still single line semantics)
    pass

orig_len = len(content)
seen = set()
clean = []
dups = []
illegal = []
for ch in content:
    if not HAN(ch):
        illegal.append(ch)
        continue
    if ch in seen:
        dups.append(ch)
        continue
    seen.add(ch)
    clean.append(ch)
charset = "".join(clean)
print(f"charset: original {orig_len} chars, clean {len(charset)} chars, dups {len(dups)}, illegal {len(illegal)}")
if dups:
    print("DUP CHARS:", "".join(dups))
    fixes.append(f"charset.txt 去除重复字 {len(dups)} 个: {''.join(dups)}")
if illegal:
    print("ILLEGAL CHARS:", repr("".join(illegal)))
    fixes.append(f"charset.txt 去除非法字符 {len(illegal)} 个: {''.join(illegal)!r}")

# ---------- Step 4: coverage check, append missing ----------
counter = Counter()
for p in famous:
    for ln in p["lines"]:
        counter.update(ln)
missing = [(ch, c) for ch, c in counter.items() if ch not in seen]
missing.sort(key=lambda x: (-x[1], x[0]))
appended = "".join(ch for ch, _ in missing)
if appended:
    print(f"MISSING {len(appended)} chars appended: {appended}")
    charset = charset + appended
    fixes.append(f"charset 追加 famous 缺失字 {len(appended)} 个（按频率排序）")
else:
    print("No missing chars")

with open(CHARSET, "w", encoding="utf-8") as f:
    f.write(charset)

# rewrite famous.json if anything changed
with open(FAMOUS, "w", encoding="utf-8") as f:
    json.dump(famous, f, ensure_ascii=False, indent=2)
    f.write("\n")

# ---------- Step 5: generate data.js ----------
famous_min = [
    OrderedDict([("t", p["title"]), ("a", p["author"]), ("d", p["dynasty"]),
                 ("l", p["lines"]), ("n", p["note"])])
    for p in famous
]
payload = OrderedDict([("chars", charset), ("famous", famous_min)])
body_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
with open(DATAJS, "w", encoding="utf-8") as f:
    f.write("window.POETRY_DATA=" + body_js + ";")

# ---------- Step 6: final verification of data.js ----------
ok = True
with open(DATAJS, encoding="utf-8") as f:
    src = f.read()
prefix = "window.POETRY_DATA="
if not (src.startswith(prefix) and src.endswith(";")):
    ok = False
    print("DATAJS: bad wrapper")
else:
    body = src[len(prefix):-1]
    try:
        obj = json.loads(body)
    except Exception as e:
        ok = False
        print("DATAJS: json.loads failed:", e)
        obj = None
    if obj is not None:
        chars = obj["chars"]
        fam = obj["famous"]
        if len(set(chars)) != len(chars):
            ok = False; print("DATAJS: duplicate chars")
        cs = set(chars)
        for p in fam:
            if len(p["l"]) != 4 or any(len(ln) != 5 for ln in p["l"]):
                ok = False; print("DATAJS: bad shape", p["t"])
            for ln in p["l"]:
                for ch in ln:
                    if ch not in cs:
                        ok = False; print("DATAJS: char not in chars:", ch, p["t"])
        print(f"DATAJS verified: chars={len(chars)}, famous={len(fam)}")

print("RESULT_JSON:", json.dumps({
    "famousCount": len(famous),
    "charsetCount": len(charset),
    "appendedChars": appended,
    "fixes": fixes,
    "dataJsOk": ok,
}, ensure_ascii=False))
