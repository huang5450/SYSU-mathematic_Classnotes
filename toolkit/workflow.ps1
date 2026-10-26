<#
.SYNOPSIS
  数学笔记一条龙：本地 tex -> xelatex 编译 -> git 推送 -> Overleaf 推送/编译 -> 桌面 PDF

.EXAMPLE
  .\toolkit\workflow.ps1 -Tex "数学分析\tex\ma-1021.tex"

.EXAMPLE
  .\toolkit\workflow.ps1 -Md "数学分析\md\ma-1021.md" -Message "更新 1021 笔记"

.NOTES
  第 1 步（md -> tex）不在本脚本里：用模板（数学分析\tex\ma-1015.tex）转写，
  或在会话里让 AI 按模板反编译。本脚本负责转换之后的全部收尾工作。
#>
[CmdletBinding()]
param(
  [string]$Tex,
  [string]$Md,
  [string]$Message,
  [switch]$SkipGit,
  [switch]$SkipOverleaf,
  [switch]$KeepAux
)

$ErrorActionPreference = "Stop"
$toolkit = $PSScriptRoot
$repo = Split-Path $toolkit -Parent

function Info($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "!!  $m" -ForegroundColor Yellow }

# ---------- 0. 解析 tex ----------
if (-not $Tex -and $Md) {
  $Tex = ($Md -replace '(?i)[\\/]md[\\/]', '\tex\') -replace '(?i)\.md$', '.tex'
  Info "md 对应 tex: $Tex"
}
if (-not $Tex) { throw "请用 -Tex <tex> 或 -Md <md> 指定要发布的文件" }
if (-not (Test-Path -LiteralPath $Tex)) {
  throw "找不到 $Tex 。若刚写完 md，请先用模板把它转成 tex（见 toolkit\README.md 第 1 步）"
}
$TexPath = (Resolve-Path -LiteralPath $Tex).Path
$texDir = Split-Path $TexPath -Parent
$name = [IO.Path]::GetFileNameWithoutExtension($TexPath)
$olPdf = Join-Path $texDir (${name} + "_ol.pdf")
$olGlob = ${name} + "_ol_p*.png"

# ---------- 1. 本地编译 ----------
$xelatex = "C:\Users\huang\AppData\Local\Programs\MiKTeX\miktex\bin\x64\xelatex.exe"
if (-not (Test-Path -LiteralPath $xelatex)) {
  $c = Get-Command xelatex -ErrorAction SilentlyContinue
  if ($c) { $xelatex = $c.Source } else { throw "找不到 xelatex，请先安装 MiKTeX" }
}

Info "[1/4] 本地编译 $name.tex （xelatex 两遍）"
Push-Location $texDir
try {
  # 原生程序的 stderr 在 $ErrorActionPreference=Stop 下会变成终止错误，这里临时放宽
  $eap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $xelatex -synctex=1 -interaction=nonstopmode -file-line-error "$name.tex" 2>&1 | Out-Null
  $code1 = $LASTEXITCODE
  if ($code1 -ne 0) {
    $ErrorActionPreference = $eap
    Warn "编译失败，日志最后 20 行："
    if (Test-Path "$name.log") { Get-Content "$name.log" -Tail 20 -Encoding utf8 | ForEach-Object { Write-Host "    $_" } }
    throw "xelatex 第一遍失败"
  }
  & $xelatex -synctex=1 -interaction=nonstopmode -file-line-error "$name.tex" 2>&1 | Out-Null
  $code2 = $LASTEXITCODE
  $ErrorActionPreference = $eap
  if ($code2 -ne 0) { throw "xelatex 第二遍失败" }
  $localPdf = Join-Path $texDir "$name.pdf"
  if (-not (Test-Path -LiteralPath $localPdf)) { throw "没有生成 $name.pdf" }
  Info "本地 PDF: $localPdf"
}
finally { Pop-Location }

# ---------- 2. git ----------
if (-not $SkipGit) {
  Info "[2/4] git 提交并推送"
  git -C $repo add -A
  if (git -C $repo status --porcelain) {
    if (-not $Message) { $Message = "更新 $name" }
    git -C $repo -c user.name="Huang Ziheng" -c user.email="86883261+huang5450@users.noreply.github.com" commit -m "$Message" | Out-Null
    $pushed = $false
    for ($i = 1; $i -le 5; $i++) {
      git -C $repo push origin main 2>$null
      if ($LASTEXITCODE -eq 0) { $pushed = $true; break }
      Warn "push 第 $i 次失败，2 秒后重试"
      Start-Sleep -Seconds 2
    }
    if ($pushed) { Info "已推送：$Message" } else { Warn "git push 最终失败，稍后在 VS Code 里点 Sync Changes" }
  }
  else { Info "工作区没有改动，跳过提交" }
}
else { Info "[2/4] 已跳过 git" }

# ---------- 3. Overleaf ----------
if (-not $SkipOverleaf) {
  Info "[3/4] 推送 Overleaf 并触发服务器编译"
  $cfg = Join-Path $toolkit "overleaf.config.json"
  $py = "C:\Users\huang\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
  if (-not (Test-Path -LiteralPath $py)) {
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { $py = $c.Source }
  }
  if (-not (Test-Path -LiteralPath $cfg)) {
    Warn "缺少 toolkit\overleaf.config.json，跳过 Overleaf（配置方法见 toolkit\README.md）"
  }
  elseif (-not $py) {
    Warn "找不到 python，跳过 Overleaf"
  }
  else {
    if (Select-String -LiteralPath $TexPath -Pattern '\\includegraphics' -Quiet) {
      Warn "这篇含图片：Overleaf 端若没有对应图片，服务器编译会失败"
    }
    & $py (Join-Path $toolkit "publish.py") $TexPath
    if ($LASTEXITCODE -ne 0) { Warn "Overleaf 步骤失败（本地 PDF 不受影响）" }
  }
}
else { Info "[3/4] 已跳过 Overleaf" }

# ---------- 4. 桌面 PDF ----------
Info "[4/4] 把 PDF 放到桌面"
$pdfSrc = if (Test-Path -LiteralPath $olPdf) { $olPdf } else { $localPdf }
$desktop = [Environment]::GetFolderPath("Desktop")
$dest = Join-Path $desktop "$name.pdf"
Copy-Item -LiteralPath $pdfSrc -Destination $dest -Force
Info "桌面 PDF: $dest"

if (-not $KeepAux) {
  Remove-Item -LiteralPath $olPdf -ErrorAction SilentlyContinue
  Get-ChildItem -LiteralPath $texDir -Filter $olGlob -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

Info "全部完成。"
