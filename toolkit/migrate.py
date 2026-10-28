# -*- coding: utf-8 -*-
"""把 toolkit/style/preamble.tex 的版式推广到所有 tex（幂等，可重复运行）。"""
import io, os, re, sys

REPO = r"D:\Desktop\SYSU-mathematic_Classnotes"
STYLE = os.path.join(REPO, "toolkit", "style", "preamble.tex")
BEGIN, END = "% ==STYLE-BEGIN==", "% ==STYLE-END=="

ENV = {"定理": "thm", "引理": "lem", "命题": "prop", "推论": "cor",
       "定义": "defn", "例": "exa", "注": "rem"}
HEAD_NAMES = "|".join(ENV)
COURSE_OF = {"ma": "数学分析", "aa": "高等代数", "ga": "解析几何", "practice": "解析几何"}

HEAD_INLINE = re.compile(
    r"^(?:\\textbf\{)?(?P<name>" + HEAD_NAMES + r")\s*[0-9一二三四五六七八九十]*\s*[：:]\s*(?:\})?\s*(?:\\quad\s*)?")
HEAD_BARE = re.compile(
    r"^(?:\\textbf\{)?(?P<name>" + HEAD_NAMES + r")\s*[0-9一二三四五六七八九十]*\s*(?:\})?$")

def strip_num(s):
    s = s.strip()
    s = re.sub(r"^§\s*[0-9]*\s*(?:\\quad\s*)?", "", s)
    s = re.sub(r"^(?:第\s*)?[0-9]+(?:\.[0-9]+)*\s*(?:[.、．)）]|\\quad)\s*", "", s)
    s = re.sub(r"^第\s*[0-9]+\s*讲\s*[.、．]?\s*", "", s)
    return s.strip()

def migrate(path, dry=False):
    text = io.open(path, encoding="utf-8").read().replace("\r\n", "\n")
    if BEGIN in text:
        return ("skip", 0, 0, 0, "已有标记")
    i = text.find(r"\begin{document}")
    if i < 0:
        return ("fail", 0, 0, 0, "没有 begin{document}")
    pre, body = text[:i], text[i + len(r"\begin{document}"):]

    # ---- 标题与课程名 ----
    base = os.path.basename(path)
    m = re.match(r"([a-z]+)-", base)
    prefix = m.group(1) if m else "ma"
    course = COURSE_OF.get(prefix, "数学分析")
    num = re.search(r"-([0-9]{4})", base)
    num = num.group(1) if num else ""

    t = re.search(r"\\title\s*\{(.+?)\}", pre)
    title = t.group(1).strip() if t else ""
    if (not title) or ("?" in title) or not re.search(r"[0-9]{4}", title):
        alt = re.search(r"\\section\*?\s*\{\s*(数学分析|高等代数|几何与代数|解析几何)\s*([0-9]{4})", body)
        if alt:
            title = "%s %s" % (alt.group(1), alt.group(2))
            course = alt.group(1)
            num = alt.group(2)
    if not title:
        title = ("%s %s" % (course, num)).strip()
    coursename = ("%s\\,·\\,%s" % (course, num)) if num else course

    # ---- 保留必要的自定义导言行 ----
    extras = []
    for line in pre.split("\n"):
        s = line.strip()
        if not s or s.startswith("%"):
            continue
        if re.search(r"\\(documentclass|title|author|date|maketitle|pagestyle|fancyhead|fancyhf|geometry)\b", s):
            continue
        mm = re.match(r"\\usepackage\s*(\[[^\]]*\])?\s*\{([^}]*)\}", s)
        if mm:
            pkgs = [x.strip() for x in mm.group(2).split(",") if x.strip()]
            if all(x in ("amsmath", "amssymb", "amsthm", "geometry", "fancyhdr", "enumitem", "hyperref", "ctex", "xeCJK") for x in pkgs):
                continue
        if "\\linespread" in s or "\\setlength{\\parindent}" in s:
            continue
        if s not in extras:
            extras.append(s)

    # ---- 正文 ----
    lines = body.split("\n")
    k = 0
    while k < len(lines):
        s = lines[k].strip()
        if s == "" or s == "\\maketitle":
            k += 1; continue
        if re.match(r"\\section\*?\{\s*(数学分析|高等代数|几何与代数|解析几何)\s*[0-9]{4}", s):
            k += 1
            while k < len(lines) and lines[k].strip() == "":
                k += 1
            continue
        break
    lines = lines[k:]

    n_sec_all = len(re.findall(r"\\section\{", "\n".join(lines)))
    flat = n_sec_all <= 1
    n_sec = 0
    out = []
    for line in lines:
        s = line.strip()
        m = re.fullmatch(r"\\(section|subsection)(\*?)\{([^{}]*)\}", s)
        if m:
            kind, title2 = m.group(1), strip_num(m.group(3))
            if title2:
                if kind == "subsection" and not flat:
                    out.append("\\subsection{%s}" % title2); n_sec += 1; continue
                out.append("\\section{%s}" % title2); n_sec += 1; continue
        out.append(line)
    body = "\n".join(out)

    # ---- 定理类 ----
    n_head = 0
    paras = body.split("\n\n")
    res = []
    idx = 0
    while idx < len(paras):
        p = paras[idx]
        st = p.lstrip()
        bad = re.search(r"\\begin\{|\\end\{|\\item", st)
        mi = HEAD_INLINE.match(st)
        mb = None if mi else HEAD_BARE.match(st)
        if mi and not bad and len(st) > 8:
            env = ENV[mi.group("name")]
            rest = st[mi.end():].lstrip()
            res.append("\\begin{%s}\n%s\n\\end{%s}" % (env, rest, env)); n_head += 1; idx += 1; continue
        if mb and not bad and idx + 1 < len(paras):
            nxt = paras[idx + 1].lstrip()
            if not re.search(r"\\begin\{|\\end\{|\\item", nxt):
                env = ENV[mb.group("name")]
                res.append("\\begin{%s}\n%s\n\\end{%s}" % (env, nxt.rstrip(), env)); n_head += 1
                idx += 2; continue
        res.append(p); idx += 1
    body = "\n\n".join(res)

    # ---- 行内 \limits ----
    n_lim = 0
    def rep(m):
        nonlocal n_lim
        n_lim += 1
        return "\\%s\\limits_" % m.group(1)
    out2, inD = [], False
    for line in body.split("\n"):
        s = line.strip()
        if s == "\\[":
            inD = True; out2.append(line); continue
        if s == "\\]":
            inD = False; out2.append(line); continue
        if not inD:
            line = re.sub(r"\\(lim|sum|prod|bigcup|bigcap|sup|inf|max|min)(?!limits)_", rep, line)
        out2.append(line)
    body = "\n".join(out2)

    style = io.open(STYLE, encoding="utf-8").read().strip("\n")
    new = (BEGIN + "\n" + style + "\n" + END + "\n"
           + "\\renewcommand{\\coursename}{%s}\n" % coursename
           + "\\title{%s}\n" % title
           + "".join(e + "\n" for e in extras)
           + "\\date{}\n\\begin{document}\n\\maketitle\n\n"
           + body.strip() + "\n\n\\end{document}\n")
    if not dry:
        io.open(path, "w", encoding="utf-8", newline="\n").write(new)
    return ("ok", n_sec, n_head, n_lim, title)

def main():
    dry = "--dry-run" in sys.argv
    targets = []
    for d in ("数学分析", "几何与代数"):
        p = os.path.join(REPO, d, "tex")
        for f in sorted(os.listdir(p)):
            if f.endswith(".tex"):
                targets.append(os.path.join(p, f))
    tot = [0, 0, 0]
    for t in targets:
        st, a, b, c, info = migrate(t, dry)
        if st == "ok":
            tot[0] += a; tot[1] += b; tot[2] += c
            print("OK   %-17s 小节 %2d  定理类 %d  limits %2d   %s" % (os.path.basename(t), a, b, c, info))
        else:
            print("%-5s %-17s %s" % (st.upper(), os.path.basename(t), info))
    print("\n合计：小节 %d，定理类 %d，limits %d" % tuple(tot))

main()
