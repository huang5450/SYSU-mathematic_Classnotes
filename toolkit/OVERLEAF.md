# 推送到 SYSU Overleaf（overleaf_push.py）

**一句话**：笔记的 `.tex` 在本机改好后，不用手动拖拽，直接推到 SYSU Overleaf 的
「**数学分析笔记-2026级1班**」，并且**自动逐字节比对 + 让服务器编译验证**。

- 工具：`数学分析\overleaf_push.py`
- 凭据：`数学分析\overleaf.config.json`（同目录）
- 站点：`https://latex.sysu.edu.cn`（Overleaf CE 自托管版）

---

## 1. 常用命令

```bat
set PY=C:\Users\huang\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe

:: ★ 一条命令搞定（推荐）：推送 + 逐字节比对 + 服务器编译 + 取回 PDF + 渲染 PNG 预览
%PY% 数学分析\publish.py 本地.tex

%PY% 数学分析\overleaf_push.py status              :: 检查登录 + 列远端文件树
%PY% 数学分析\overleaf_push.py list                :: 只列文件树
%PY% 数学分析\overleaf_push.py push 本地.tex        :: 推送 + 自动比对
%PY% 数学分析\overleaf_push.py push 本地.tex --compile   :: 再加服务器端编译验证
%PY% 数学分析\overleaf_push.py push 本地.tex --as 远端名 :: 改远端文件名
%PY% 数学分析\overleaf_push.py verify 本地.tex      :: 只比对，不推送
%PY% 数学分析\overleaf_push.py pull 远端名 -o 本地路径  :: 从远端取回
%PY% 数学分析\overleaf_push.py rm 远端名            :: 删除
%PY% 数学分析\overleaf_push.py compile --root 远端名   :: 只编译
%PY% 数学分析\overleaf_push.py zip -o 整包.zip       :: 整包下载
```

### `publish.py` 干什么

```
[1/3] 推送到 Overleaf        上传 → 复查文件树（防重复项）→ 逐字节 sha256 比对
[2/3] 服务器端编译            rootDoc_id 取自 id 缓存，所以必须先推送
[3/3] 取回 PDF 并渲染预览      落在 tex 同目录：<名>_ol.pdf、<名>_ol_p1.png …
```

- 可选参数：`--as 远端名`、`--no-verify`、`--no-preview`、`--config 路径`
- **为什么预览走 Overleaf 而不是 texlive.net**：项目用 `ctexart`，Overleaf 里 ctex 齐全，
  出的 PDF 与你在项目里看到的完全一致；texlive.net 那条路（`render_tex.py`）得把导言区
  改写成 `article + Fandol`，只是个近似。旧路子仍可单独跑 `render_tex.py`。

**退出码**：`0` 成功；非 0 表示失败（登录失效、比对不一致、编译失败等），
`push` 的比对不一致会直接以非 0 退出，方便脚本串起来。

> 本机 **PowerShell / curl 出网会全 `000`**，只有 Python 的 TLS 栈能通 —— 所以这些
> 脚本必须用上面的 Python 跑，别用 `Invoke-WebRequest` 或 `curl`。

---

## 2. 配置文件

`数学分析\overleaf.config.json`：

```json
{
  "base":       "https://latex.sysu.edu.cn",
  "project_id": "6aba858e5dad2075d2a0473e",
  "folder_id":  "6aba858e5dad2075d2a0474b",
  "cookie":     "_qddaz=...; overleaf.sid=..."
}
```

| 字段 | 说明 | 会不会变 |
|---|---|---|
| `project_id` | 项目 id，就是 URL 里 `/project/` 后面那串 | 不改项目就不变 |
| `folder_id` | **项目的「根目录 id」**，⚠️ **不是** `project_id` | 一般不用换 |
| `cookie` | 整条 `Cookie:` 请求头 | **会过期**（本次约到 2026-10-16） |

### cookie 过期了怎么换

1. Edge 打开 `https://latex.sysu.edu.cn/project`
2. `F12` → **Network / 网络** → `F5` 刷新
3. 点任意一条发往 `latex.sysu.edu.cn` 的请求 → 右键 → **Copy → Copy as cURL (bash)**
4. 从里面把 `-b '...'`（或 `-H 'Cookie: ...'`）后面那串整条复制
5. 覆盖 `overleaf.config.json` 的 `cookie` 字段，跑一次 `status` 验证

### folder_id 怎么拿（新项目才需要）

它只存在于编辑器的实时连接里（这个实例的实时通道是**老式 socket.io 0.9**，
HTTP 端点全都不吐它），只能从浏览器抓：

1. Overleaf 项目页 → `F12` → **Network** → 勾 **Preserve log** → 清空列表
2. 在编辑器里点一次「**新建文件**」，或拖一个无关紧要的小文件进去
3. 找那条请求，在 **Payload（载荷）→ Form Data** 里读：
   ```
   folder_id: 6aba8xxxxxxxxxxxxxxxxxxxxxxx
   ```
   （点「新建文件」时字段名可能显示为 `parent_folder_id`，**值一样**）
4. 填进配置

---

## 3. 踩过的坑（都是血泪）

1. **`folder_id` 必须放在 query 里，文件名必须放在 multipart 表单字段里。**
   放反了会得到 `{"success":false,"error":"folder_not_found"}` 或
   `{"success":false,"error":"invalid_filename"}` —— 这两个报错**极具误导性**，
   其实跟文件名本身一点关系都没有。

2. **同名上传 = 覆盖，不产生重复项**（已实测：entity_id 不变，文件数不变）。
   但 Overleaf 里 `.tex` 是 "doc" 实体，理论上存在"并排生成"的风险，所以
   `push` 每次都会复查文件树、报「同名条目 1 -> 1」，一旦变成 2 会立刻警告。

3. **`/project/<id>/download/zip` 有速率限制**，连续拉会吃 `429`。
   脚本已内置指数退避；手动折腾时别猛刷。

4. **`rootDoc_id` 不能靠文件名推出来**，实体 id 只有上传的回包会给。
   脚本用 `数学分析\.overleaf_ids.json` 缓存「文件名 → entity_id」，
   `push` 会自动写入，所以 `compile --root <名>` 要在 `push` 之后用。

5. **`/project/<id>/entities` 不吐 id**，只有 `path` 和 `type`；
   `PUT/POST /entities/<path>` 一律 404 —— 别指望有 RESTful 的实体写接口。

---

## 4. 在笔记工作流里怎么用

```bat
:: 1. 在本机改好 tex（工作区内改，稳定后覆盖 D:\Desktop\数学分析\）
:: 2. 推送 + 比对 + 编译
%PY% 数学分析\overleaf_push.py push "D:\Desktop\数学分析\tex\ma-1008.tex" --compile
:: 3. 输出示例：
::     回包: {"success": true, "entity_id": "6ac8d7ac...", "entity_type": "doc"}
::     文件数 10 -> 10 ；同名条目 1 -> 1 （覆盖成功，无重复）
::     ✅ 完全一致
::     编译状态: success ；输出 9 个文件
```

**建议流程**：`push` 之后看两行 —— 「同名条目 1 -> 1」和「✅ 完全一致」，
再确认「编译状态: success」，这三条都过就可以放心关终端了。

---

## 5. 与其它会话的关系

本文件与工具位于 `D:\Desktop\DS工作区\数学分析\`，是**三个会话共享**的：

- **① 数学笔记反编译**（`session-abf74730`）—— 主要使用者，改完笔记直接推
- ② 数分作业 / ③ 几代作业 —— 需要时同样可用

`sync_sessions.py` 生成的 `三方会话动态.md` 末尾已挂上本工具的命令速查，
所以每个会话读那份动态时都会看到它。

---

<!-- 变更记录 -->
- **2026-10-11** 初版。打通：读取（entities / zip / updates）、写入（upload 覆盖）、
  删除（`DELETE /project/<id>/doc/<entity_id>`）、编译（`POST /compile`）。
  同日以本工具把修好的 `ma-1008.tex` 推入项目并验证通过。
