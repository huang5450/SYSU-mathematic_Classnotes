# -*- coding: utf-8 -*-
"""一条命令走完：推送 → 比对 → 服务器编译 → 取回 PDF → 渲染分页 PNG 预览。

用法：
  python publish.py <本地.tex> [--as 远端名] [--no-verify] [--no-preview] [--config 路径]

流程与产物：
  1) 推送 tex 到 SYSU Overleaf（项目「数学分析笔记-2026级1班」），复查文件树、逐字节比对
  2) 触发服务器端编译（rootDoc_id 从 overleaf_push 的 id 缓存里取，所以必须先推送）
  3) 把编译好的 PDF 取回，落在 tex 同目录：<名>_ol.pdf
  4) 渲染成分页 PNG：<名>_ol_p1.png、<名>_ol_p2.png …

为什么预览用 Overleaf 而不是 texlive.net：
  项目用的是 ctexart，Overleaf 里 ctex 齐全，编译结果与项目里看到的完全一致；
  texlive.net 那条路（render_tex.py）得把导言区改写成 article+Fandol，属于「近似」。
  需要旧路子时仍可单独跑 render_tex.py。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 脚本被复制到别处（例如 D:\Desktop\数学分析\）时，仍回到工作区取依赖与配置，
# 保证「一份真源」。
WS_MATH = r"D:\Desktop\DS工作区\数学分析"
for _p in (HERE, WS_MATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import overleaf_push as op        # noqa: E402

try:
    import render_tex             # noqa: E402  （PDF→PNG 用，缺失时自动降级）
except ImportError:
    render_tex = None


def render_png(pdf_path, prefix, scale=2.2):
    if render_tex is not None:
        render_tex.ensure_pypdfium2()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_path)
    outs = []
    for i in range(len(doc)):
        img = doc[i].render(scale=scale).to_pil()
        p = os.path.join(os.path.dirname(pdf_path), "%s_p%d.png" % (prefix, i + 1))
        img.save(p)
        outs.append((p, img.size))
    return outs


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    def opt(flag, default=None):
        if flag in argv:
            i = argv.index(flag)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    pos = [a for a in argv if not a.startswith("-")]
    if not pos:
        sys.exit("用法：python publish.py <本地.tex> [--as 远端名] [--no-verify] [--no-preview]")
    tex = pos[0]
    if not os.path.isfile(tex):
        sys.exit("本地文件不存在：%s" % tex)

    as_name = opt("--as")
    do_verify = "--no-verify" not in argv
    do_preview = "--no-preview" not in argv
    cfg = op.load_config(opt("--config"))

    # 1) 推送 + 比对
    print("=" * 66)
    print("[1/3] 推送到 Overleaf")
    print("=" * 66)
    op.cmd_push(cfg, tex, as_name, do_verify=do_verify, do_compile=False)
    name = op.remote_name_of(tex, as_name)

    # 2) 服务器编译
    print("=" * 66)
    print("[2/3] 服务器端编译")
    print("=" * 66)
    res = op.compile_project(cfg, name)
    status = res.get("status")
    print("编译状态: %s ；输出 %d 个文件" % (status, len(res.get("outputFiles", []))))
    logs = res.get("logs") or {}
    if isinstance(logs, dict):
        for k, v in logs.items():
            print("  %-12s %s" % (k, str(v)[:200]))
    if status != "success":
        sys.exit("编译未成功，请到 Overleaf 里看日志。")

    # 3) 取回 PDF + 渲染
    print("=" * 66)
    print("[3/3] 取回 PDF 并渲染预览")
    print("=" * 66)
    pdf_name, pdf = op.fetch_output(cfg, res, "pdf")
    if not pdf:
        print("未在编译产物里找到 PDF，跳过预览。")
        return 0
    stem = os.path.splitext(os.path.basename(tex))[0]
    out_pdf = os.path.join(os.path.dirname(os.path.abspath(tex)), stem + "_ol.pdf")
    with open(out_pdf, "wb") as fh:
        fh.write(pdf)
    print("PDF: %s (%d 字节，来自 %s)" % (out_pdf, len(pdf), pdf_name))

    if not do_preview:
        return 0
    try:
        outs = render_png(out_pdf, stem + "_ol")
    except Exception as exc:                                     # noqa: BLE001
        print("渲染预览失败（不影响推送结果）：%s: %s" % (type(exc).__name__, exc))
        return 0
    for p, size in outs:
        print("PNG: %s %s" % (p, size))

    print("=" * 66)
    print("完成：远端 %s 已更新并编译通过，预览 %d 页。" % (name, len(outs)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
