# -*- coding: utf-8 -*-
"""补丁：把遗漏的定理类段首（含“命题”独占一行后面紧跟公式）转成环境，并在 \section 后补空行。"""
import io, os, re, sys

REPO = r"D:\Desktop\SYSU-mathematic_Classnotes"
ENV = {"定理": "thm", "引理": "lem", "命题": "prop", "推论": "cor",
       "定义": "defn", "例": "exa", "注": "rem"}
NAMES = "|".join(ENV)
HEAD_INLINE = re.compile(r"^(?:\\textbf\{)?(?P<name>" + NAMES + r")\s*[0-9一二三四五六七八九十]*\s*[：:]\s*(?:\})?\s*(?:\\quad\s*)?")
HEAD_BARE = re.compile(r"^(?:\\textbf\{)?(?P<name>" + NAMES + r")\s*[0-9一二三四五六七八九十]*\s*(?:\})?$")

def process(body):
    # 1) \section 后补空行
    lines, out = body.split("\n"), []
    for i, ln in enumerate(lines):
        out.append(ln)
        if re.fullmatch(r"\\section\{[^{}]*\}", ln.strip()):
            if i + 1 < len(lines) and lines[i + 1].strip() != "":
                out.append("")
    body = "\n".join(out)

    # 2) 段首定理类
    n = 0
    paras = body.split("\n\n")
    res = []
    for p in paras:
        pl = p.split("\n")
        first = pl[0].strip()
        rest = pl[1:]
        if re.search(r"\\begin\{|\\end\{|\\item", first):
            res.append(p); continue
        mi = HEAD_INLINE.match(first)
        mb = HEAD_BARE.match(first) if not mi else None
        if mi:
            inner = first[mi.end():].strip()
            if not inner and not rest:
                res.append(p); continue
            env = ENV[mi.group("name")]
            inner_lines = ([inner] if inner else []) + rest
            res.append("\\begin{%s}\n%s\n\\end{%s}" % (env, "\n".join(inner_lines).strip(), env))
            n += 1
        elif mb:
            if not rest:
                res.append(p); continue
            env = ENV[mb.group("name")]
            res.append("\\begin{%s}\n%s\n\\end{%s}" % (env, "\n".join(rest).strip(), env))
            n += 1
        else:
            res.append(p)
    return "\n\n".join(res), n

def main():
    dry = "--dry-run" in sys.argv
    total = 0
    for d in ("数学分析", "几何与代数"):
        p = os.path.join(REPO, d, "tex")
        for f in sorted(os.listdir(p)):
            if not f.endswith(".tex"):
                continue
            path = os.path.join(p, f)
            text = io.open(path, encoding="utf-8").read().replace("\r\n", "\n")
            i = text.find(r"\begin{document}")
            pre, body = text[:i], text[i + len(r"\begin{document}"):]
            newbody, n = process(body)
            if newbody != body:
                total += n
                print("%-17s 新增环境 %d" % (f, n))
                if not dry:
                    io.open(path, "w", encoding="utf-8", newline="\n").write(pre + r"\begin{document}" + newbody)
    print("合计新增：%d" % total)

main()
