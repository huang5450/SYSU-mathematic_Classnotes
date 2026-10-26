# -*- coding: utf-8 -*-
"""把本地改好的 .tex 推送到 SYSU Overleaf（latex.sysu.edu.cn）的项目里。

用法：
  python overleaf_push.py status                      # 检查配置/登录，列文件树
  python overleaf_push.py list                        # 只列远端文件树
  python overleaf_push.py pull <远端名> [-o 本地路径]   # 从远端取回一个文件
  python overleaf_push.py push <本地文件> [--as 远端名] [--no-verify] [--compile]
  python overleaf_push.py verify <本地文件> [--as 远端名]
  python overleaf_push.py rm <远端名> [<远端名> ...]
  python overleaf_push.py compile [--root 远端名]
  python overleaf_push.py zip [-o 输出.zip]

配置：同目录下的 overleaf.config.json
  {
    "base":       "https://latex.sysu.edu.cn",
    "project_id": "6aba858e5dad2075d2a0473e",
    "folder_id":  "6aba858e5dad2075d2a0474b",   <- 项目的“根目录 id”，不是 project_id
    "cookie":     "_qddaz=...; overleaf.sid=..."
  }

要点（都是踩过的坑）：
  * folder_id 必须放在 query 里，文件名必须放在 multipart 表单字段里；
    放反了会得到 folder_not_found / invalid_filename 这两个极具误导性的报错。
  * 同名上传是【覆盖】，不会生成重复项（已实测）。
  * 这个实例的实时通道是老式 socket.io 0.9，文件树只走那条通道，
    所以 folder_id 抓不到就抓不到，只能从浏览器 DevTools 里捞。
  * /download/zip 有速率限制，429 会自动退避重试。
"""
import io
import json
import os
import re
import sys
import time
import uuid
import zipfile
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "overleaf.config.json")
# 脚本被复制到别处（例如 D:\Desktop\数学分析\）时的兜底：回到工作区的权威配置，
# 这样一个 cookie 只维护一份。
CONFIG_FALLBACK = r"D:\Desktop\DS工作区\数学分析\overleaf.config.json"
IDCACHE = os.path.join(HERE, ".overleaf_ids.json")
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36 Edg/155.0.0.0")}


# ---------------------------------------------------------------- 基础设施

def load_config(path=None):
    for cand in [p for p in (path, CONFIG, CONFIG_FALLBACK) if p]:
        if not os.path.isfile(cand):
            continue
        with io.open(cand, encoding="utf-8") as fh:
            cfg = json.load(fh)
        missing = [k for k in ("base", "project_id", "folder_id", "cookie") if not cfg.get(k)]
        if missing:
            sys.exit("[config] %s 缺少字段：%s" % (cand, ", ".join(missing)))
        cfg["base"] = cfg["base"].rstrip("/")
        cfg["_config_path"] = cand
        return cfg
    sys.exit("找不到 overleaf.config.json。已查：\n  %s\n"
             "请照 overleaf_push.py 顶部的说明建一个（cookie 从浏览器 DevTools 拿，\n"
             "folder_id 抓一次“新建文件/上传”请求里的 folder_id 或 parent_folder_id）。"
             % "\n  ".join(p for p in (CONFIG, CONFIG_FALLBACK) if p))


def request(cfg, path, accept="*/*", method="GET", data=None, extra=None, timeout=90):
    headers = {"Cookie": cfg["cookie"], "Accept": accept,
               "Accept-Language": "zh-CN,zh;q=0.9",
               "Referer": "%s/project/%s" % (cfg["base"], cfg["project_id"])}
    headers.update(UA)
    if extra:
        headers.update(extra)
    req = urllib.request.Request(cfg["base"] + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read(), resp.url
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read(), cfg["base"] + path
    except Exception as exc:                                     # noqa: BLE001
        return None, {}, ("ERR %s: %s" % (type(exc).__name__, exc)).encode(), cfg["base"] + path


def csrf(cfg):
    """每次运行现取 csrf（每加载一次页面就轮换一次）。"""
    st, _, body, url = request(cfg, "/project/" + cfg["project_id"], accept="text/html")
    if st is None or url.rstrip("/").endswith("/login"):
        sys.exit("登录已失效（被重定向到 /login）。请重新从浏览器复制 cookie 填进配置。")
    m = re.search(r'name="ol-csrfToken" content="([^"]+)"', body.decode("utf-8", "replace"))
    if not m:
        sys.exit("页面里找不到 ol-csrfToken，站点结构可能变了。")
    return m.group(1)


def tree(cfg):
    st, _, body, _ = request(cfg, "/project/%s/entities" % cfg["project_id"],
                             accept="application/json")
    if st != 200:
        sys.exit("取文件树失败：HTTP %s %s" % (st, body[:200].decode("utf-8", "replace")))
    return [e["path"] for e in json.loads(body.decode("utf-8"))["entities"]]


def zip_map(cfg, tries=5):
    """整包下载（唯一能拿到文件内容的只读端点，有速率限制）。"""
    for i in range(tries):
        st, hdr, body, _ = request(cfg, "/project/%s/download/zip" % cfg["project_id"])
        if body[:2] == b"PK":
            zf = zipfile.ZipFile(io.BytesIO(body))
            return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
        wait = 8 * (i + 1)
        print("   [zip] HTTP %s，%d 秒后重试…" % (st, wait))
        time.sleep(wait)
    sys.exit("整包下载屡次失败（疑似限流），稍后再试。")


def upload(cfg, name, content, token=None, retries=3):
    """关键：folder_id 在 query，name 在 multipart 表单字段。"""
    token = token or csrf(cfg)
    for _ in range(retries):
        bnd = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]
        body = ('--%s\r\nContent-Disposition: form-data; name="name"\r\n\r\n%s\r\n'
                % (bnd, name)).encode("utf-8")
        body += ('--%s\r\nContent-Disposition: form-data; name="qqfile"; filename="%s"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n' % (bnd, name)).encode("utf-8")
        body += content + b"\r\n" + ("--%s--\r\n" % bnd).encode("utf-8")
        st, _, raw, _ = request(
            cfg, "/project/%s/upload?folder_id=%s" % (cfg["project_id"],
                                                      urllib.parse.quote(cfg["folder_id"])),
            method="POST", data=body, accept="application/json",
            extra={"Content-Type": "multipart/form-data; boundary=%s" % bnd,
                   "x-csrf-token": token})
        txt = raw.decode("utf-8", "replace")
        if st == 200 and '"success":true' in txt.replace(" ", ""):
            return json.loads(txt)
        if st == 429:
            print("   [upload] 限流，等 10 秒…")
            time.sleep(10)
            token = csrf(cfg)
            continue
        sys.exit("上传失败：HTTP %s %s" % (st, txt[:300]))
    sys.exit("上传屡次被限流，稍后再试。")


def delete(cfg, entity_id, token=None):
    token = token or csrf(cfg)
    st, _, body, _ = request(cfg, "/project/%s/doc/%s" % (cfg["project_id"], entity_id),
                             method="DELETE", accept="application/json",
                             extra={"x-csrf-token": token})
    if st not in (200, 204):
        sys.exit("删除 %s 失败：HTTP %s %s" % (entity_id, st,
                                              body[:200].decode("utf-8", "replace")))


def id_cache(update=None):
    data = {}
    if os.path.isfile(IDCACHE):
        try:
            with io.open(IDCACHE, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:                                        # noqa: BLE001
            data = {}
    if update is not None:
        data.update(update)
        with io.open(IDCACHE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    return data


def remote_name_of(path, override=None):
    return override or os.path.basename(path)


def pull_one(cfg, name, out=None):
    files = zip_map(cfg)
    if name not in files:
        sys.exit("远端没有 %s。现有：%s" % (name, ", ".join(sorted(files))))
    out = out or os.path.join(HERE, name)
    with open(out, "wb") as fh:
        fh.write(files[name])
    print("已取回 %s -> %s (%d 字节)" % (name, out, len(files[name])))
    return files[name]


# ---------------------------------------------------------------- 子命令

def cmd_status(cfg):
    print("项目     : %s" % cfg["project_id"])
    print("根目录   : %s" % cfg["folder_id"])
    print("配置来源 : %s" % cfg.get("_config_path", CONFIG))
    csrf(cfg)                                    # 会 sys.exit 若登录失效
    paths = tree(cfg)
    print("登录     : OK")
    print("远端文件 (%d):" % len(paths))
    for p in paths:
        print("   " + p)


def cmd_list(cfg):
    for p in tree(cfg):
        print(p)


def cmd_pull(cfg, name, out):
    pull_one(cfg, name, out)


def cmd_push(cfg, local, as_name, do_verify=True, do_compile=False):
    if not os.path.isfile(local):
        sys.exit("本地文件不存在：%s" % local)
    name = remote_name_of(local, as_name)
    content = open(local, "rb").read()
    token = csrf(cfg)
    before = tree(cfg)
    n_before = sum(1 for p in before if p.endswith("/" + name))

    print("推送 %s -> 远端 %s (%d 字节)" % (local, name, len(content)))
    res = upload(cfg, name, content, token)
    print("   回包:", json.dumps(res, ensure_ascii=False))
    if res.get("entity_id"):
        id_cache({name: res["entity_id"]})

    time.sleep(2)
    after = tree(cfg)
    n_after = sum(1 for p in after if p.endswith("/" + name))
    print("   文件数 %d -> %d ；同名条目 %d -> %d %s"
          % (len(before), len(after), n_before, n_after,
             "（覆盖成功，无重复）" if n_after == 1 else "！！！出现重复项，请检查 ！！！"))

    if do_verify:
        cmd_verify(cfg, local, as_name)
    if do_compile:
        cmd_compile(cfg, name)


def cmd_verify(cfg, local, as_name):
    import hashlib
    name = remote_name_of(local, as_name)
    local_bytes = open(local, "rb").read()
    files = zip_map(cfg)
    if name not in files:
        sys.exit("远端没有 %s，无法比对。" % name)
    remote = files[name]
    a = hashlib.sha256(local_bytes).hexdigest()
    b = hashlib.sha256(remote).hexdigest()
    print("   比对 %s：本地 %d 字节 / 远端 %d 字节" % (name, len(local_bytes), len(remote)))
    print("   sha256 本地 %s / 远端 %s" % (a[:16], b[:16]))
    if a == b:
        print("   ✅ 完全一致")
    else:
        sys.exit("   ❌ 不一致！")


def cmd_rm(cfg, names):
    token = csrf(cfg)
    cached = id_cache()
    for name in names:
        eid = cached.get(name)
        if not eid:
            # 先空覆盖一次，把 entity_id 逼出来（同名上传=覆盖，回包带 id）
            res = upload(cfg, name, b"", token)
            eid = res.get("entity_id")
        if not eid:
            print("   跳过 %s：拿不到 entity_id" % name)
            continue
        delete(cfg, eid, token)
        time.sleep(1.5)
        print("   已删除 %s (%s)" % (name, eid))
        cached.pop(name, None)
    id_cache(cached)
    print("   删除后:", tree(cfg))


def compile_project(cfg, root_name=None, token=None):
    """触发服务器端编译，返回完整响应 dict（调用方自己判断 status）。"""
    token = token or csrf(cfg)
    eid = None
    if root_name:
        eid = id_cache().get(root_name)
        if not eid:
            sys.exit("没有 %s 的 entity_id 缓存。先跑一次 `push %s`。"
                     % (root_name, root_name))
    payload = {"draft": False}
    if eid:
        payload["rootDoc_id"] = eid
    st, _, body, _ = request(cfg, "/project/%s/compile" % cfg["project_id"], method="POST",
                             data=json.dumps(payload).encode("utf-8"),
                             accept="application/json",
                             extra={"Content-Type": "application/json", "x-csrf-token": token})
    txt = body.decode("utf-8", "replace")
    if st != 200:
        sys.exit("编译请求失败：HTTP %s %s" % (st, txt[:300]))
    try:
        return json.loads(txt)
    except Exception:                                            # noqa: BLE001
        sys.exit("编译响应不是 JSON：%s" % txt[:300])


def fetch_output(cfg, res, want="pdf"):
    """从编译响应里挑出指定类型的产物并下载，返回 (文件名, bytes)；没有则 (None, None)。"""
    for f in res.get("outputFiles", []):
        path = f.get("path", "")
        if f.get("type") == want or path.lower().endswith("." + want):
            url = f.get("url", "")
            st, _, body, _ = request(cfg, url, timeout=180)
            if st == 200 and body:
                return os.path.basename(path) or ("output." + want), body
    return None, None


def cmd_compile(cfg, root_name):
    res = compile_project(cfg, root_name)
    status = res.get("status")
    print("编译状态: %s ；输出 %d 个文件" % (status, len(res.get("outputFiles", []))))
    logs = res.get("logs") or {}
    if isinstance(logs, dict):
        for k, v in logs.items():
            print("  %-12s %s" % (k, str(v)[:200]))
    if status != "success":
        sys.exit("编译未成功。")


def cmd_zip(cfg, out):
    out = out or os.path.join(HERE, "overleaf_project.zip")
    st, _, body, _ = request(cfg, "/project/%s/download/zip" % cfg["project_id"])
    if body[:2] != b"PK":
        st, _, body, _ = request(cfg, "/project/%s/download/zip" % cfg["project_id"])
    if body[:2] != b"PK":
        sys.exit("整包下载失败：HTTP %s" % st)
    with open(out, "wb") as fh:
        fh.write(body)
    print("已保存 %s (%d 字节)" % (out, len(body)))


# ---------------------------------------------------------------- 入口

def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]

    def opt(flag, default=None):
        if flag in rest:
            i = rest.index(flag)
            return rest[i + 1] if i + 1 < len(rest) else default
        return default

    cfg = load_config(opt("--config"))

    if cmd == "status":
        cmd_status(cfg)
    elif cmd == "list":
        cmd_list(cfg)
    elif cmd == "pull":
        pos = [a for a in rest if not a.startswith("-")]
        cmd_pull(cfg, pos[0], opt("-o") or opt("--out"))
    elif cmd == "push":
        pos = [a for a in rest if not a.startswith("-")]
        cmd_push(cfg, pos[0], opt("--as"),
                 do_verify="--no-verify" not in rest,
                 do_compile="--compile" in rest)
    elif cmd == "verify":
        pos = [a for a in rest if not a.startswith("-")]
        cmd_verify(cfg, pos[0], opt("--as"))
    elif cmd == "rm":
        pos = [a for a in rest if not a.startswith("-")]
        cmd_rm(cfg, pos)
    elif cmd == "compile":
        cmd_compile(cfg, opt("--root"))
    elif cmd == "zip":
        cmd_zip(cfg, opt("-o") or opt("--out"))
    else:
        sys.exit("未知子命令：%s（用 --help 看用法）" % cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
