# toolkit —— 笔记发布工具链

一条命令把「本地笔记」变成「GitHub 上的源码 + Overleaf 上的项目 + 桌面上的 PDF」。

```
写 md  ──①──▶  tex  ──②──▶  git push  ──③──▶  Overleaf 推送+编译  ──④──▶  桌面 PDF
```

## 快速开始

```bat
:: 在仓库根目录执行（D:\Desktop\SYSU-mathematic_Classnotes）
toolkit\workflow.cmd -Tex "数学分析\tex\ma-1021.tex" -Message "更新 1021"
```

几何与代数（另一门课）用另一份配置：

```bat
toolkit\workflow.cmd -Tex "几何与代数\tex\ga-1012.tex" -Config toolkit\overleaf.config.geometry.json -Message "更新 ga-1012"
```

也可以只给 md，让它自动找同名 tex：

```bat
toolkit\workflow.cmd -Md "数学分析\md\ma-1021.md"
```

跑完你会得到：

1. 本地 `xelatex` 编译通过的 `.pdf`（同目录）；
2. 一条 git 提交并推到 GitHub（没有改动则跳过）；
3. Overleaf 上同名 `.tex` 被覆盖、服务器编译、`<名>_ol.pdf` 取回；
4. 桌面出现 `<名>.pdf`（优先用 Overleaf 编译产物，否则用本地 PDF）。

## 四个阶段

### ① md → tex（脚本不管，人工/AI 完成）

用模板 `数学分析\tex\ma-1015.tex` 的写法：`ctexart` + `amsmath/amssymb` + `geometry`，
`\section`/`\subsection`，行间公式用 `\[ \]`，引用块用 `quote`。

> 这一步需要判断力（公式是否写错、段落怎么切），所以留在会话里让 AI 按模板反编译，
> 或者自己改。脚本从「已经有一个能编译的 tex」开始接手。

### ② 本地编译（workflow.cmd 自动）

`xelatex -synctex=1 -interaction=nonstopmode -file-line-error` 跑两遍（ctex 需要第二遍），
失败会打印日志最后 20 行并中止。

### ③ git 推送（workflow.cmd 自动）

`git add -A` → 有改动才 commit → `push origin main`，失败自动重试 5 次
（跨境链路偶尔 `Connection reset`，重试一般就好）。

### ④ Overleaf 推送 + 编译 + 取回 PDF（workflow.cmd 自动）

调用 `publish.py`：

1. 把 tex 上传到项目「数学分析笔记-2026级1班」，复查文件树（同名条目 1→1 才算覆盖成功）；
2. 逐字节 sha256 比对；
3. 触发服务器编译，状态非 `success` 就报错；
4. 取回 PDF 存为 `<名>_ol.pdf`（脚本再复制到桌面并清理临时文件）。

## 一次性配置（Overleaf）

1. 浏览器打开 `https://latex.sysu.edu.cn/project`，F12 → Network → F5；
2. 点任意一条发往该站点的请求 → 右键 **Copy → Copy as cURL (bash)**；
3. 从 `-b '...'` 或 `Cookie: ...` 里取出整条 cookie；
4. 复制 `overleaf.config.example.json` 为 `overleaf.config.json`，填 `project_id`、
   `folder_id`、`cookie`；
5. 自检：

```bat
python toolkit\overleaf_push.py status
```

目前有两份配置，cookie 相同、项目不同：

| 文件 | 项目 |
|---|---|
| `overleaf.config.json` | 数学分析笔记-2026级1班 |
| `overleaf.config.geometry.json` | 几何与代数笔记-2026级1班（root folder `6ac8585a8f92fa166d095d0f`） |

> 两份配置都含登录态，**已在 .gitignore 里**，不会被提交。
> cookie 会过期（几周），失效时重做第 1–3 步。

### 依赖

| 依赖 | 用途 | 检查 |
|---|---|---|
| MiKTeX（含 xelatex） | 本地编译 | `xelatex --version` |
| Python 3.12 | 跑 `publish.py` | `python --version` |
| pypdfium2 | PDF 渲染 PNG 预览 | `python -c "import pypdfium2"` |

## 常用参数

| 参数 | 作用 |
|---|---|
| `-Tex <路径>` | 要发布的 tex（与 `-Md` 二选一） |
| `-Md <路径>` | 由 md 推出同名 tex |
| `-Message "..."` | git 提交信息（默认「更新 <文件名>」） |
| `-Config <路径>` | 用哪份 Overleaf 配置（默认 `toolkit\overleaf.config.json`，数学分析） |
| `-SkipGit` | 不提交、不推送（只编译 + 桌面 PDF） |
| `-SkipOverleaf` | 不推 Overleaf（cookie 没配好时用） |
| `-KeepAux` | 保留 `<名>_ol.pdf` 和 `<名>_ol_p*.png` |

## 常见问题

- **"无法加载文件 workflow.ps1，因为在此系统上禁止运行脚本"**
  用 `workflow.cmd`（内部已带 `-ExecutionPolicy Bypass`），不要直接右键运行 .ps1。
- **Overleaf 报「登录已失效」** —— cookie 过期，按上面第 1–3 步重新抓。
- **含图片的文档**（`ga-1010`、`ga-1012`）—— 工具一次只传一个文件，远端没有
  `pic/...` 图片时服务器编译会失败；这类文档建议加 `-SkipOverleaf`，或先把图片传上去。
- **远端出现重复条目** —— `publish.py` 会打印 同名条目 1 -> 2 警告，去 Overleaf 里删掉多余的那份。

## 文件说明

| 文件 | 说明 |
|---|---|
| `workflow.ps1` / `workflow.cmd` | 四步流水线（.cmd 只是绕过执行策略的壳） |
| `publish.py` | 推送 → 比对 → 服务器编译 → 取回 PDF → 渲染预览 |
| `overleaf_push.py` | 底层 Overleaf 客户端（status/list/push/pull/rm/compile/zip） |
| `OVERLEAF.md` | 原工具的详细文档（坑位、接口、配置字段） |
| `overleaf.config.example.json` | 配置模板 |

> `sessions.json` / `sync_sessions.py` 与发布无关（是本机会话互通用的），没有放进仓库。
