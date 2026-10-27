<#
.SYNOPSIS
  把 toolkit\style\preamble.tex 的版式块同步进各个 tex 文件（% ==STYLE-BEGIN/END== 之间的部分）。

.DESCRIPTION
  每个 tex 仍然自包含（Overleaf 是平铺结构，不能用 \input 引子目录），
  但导言区由本脚本统一维护：改样式只改 preamble.tex，再跑一遍本脚本。

.PARAMETER Files
  要处理的 tex。不给则处理两门课 tex\ 下所有 .tex。

.PARAMETER Check
  只报告哪些文件与标准版式不一致，不写回。

.EXAMPLE
  .\toolkit\restyle.ps1 -Check
  .\toolkit\restyle.ps1 -Files "数学分析\tex\ma-1019.tex"
#>
[CmdletBinding()]
param(
  [string[]]$Files,
  [switch]$Check
)

$ErrorActionPreference = "Stop"
$toolkit = $PSScriptRoot
$repo = Split-Path $toolkit -Parent
$prePath = Join-Path $toolkit "style\preamble.tex"
if (-not (Test-Path $prePath)) { throw "找不到 $prePath" }

$nl = [string][char]10   # 统一用 LF，避免与仓库里的行尾混用
$preamble = (Get-Content $prePath -Raw -Encoding utf8) -replace "\r\n", $nl
$preamble = $preamble.TrimEnd([char[]]@(10, 13, 32, 9))

if (-not $Files) {
  $Files = Get-ChildItem -Path (Join-Path $repo "数学分析\tex"), (Join-Path $repo "几何与代数\tex") -Filter *.tex -ErrorAction SilentlyContinue |
    ForEach-Object { $_.FullName }
}

$begin = "% ==STYLE-BEGIN=="
$end   = "% ==STYLE-END=="
$changed = 0; $same = 0; $skipped = 0

foreach ($f in $Files) {
  $path = (Resolve-Path -LiteralPath $f).Path
  $text = (Get-Content $path -Raw -Encoding utf8) -replace "\r\n", $nl
  $i = $text.IndexOf($begin); $j = $text.IndexOf($end)
  if ($i -lt 0 -or $j -lt 0 -or $j -lt $i) {
    Write-Host "SKIP  $([IO.Path]::GetFileName($path))  （没有 STYLE 标记）" -ForegroundColor DarkGray
    $skipped++; continue
  }
  $newBlock = $begin + $nl + $preamble + $nl + $end
  $newText = $text.Substring(0, $i) + $newBlock + $text.Substring($j + $end.Length)
  if ($newText -eq $text) { $same++; continue }
  if (-not $Check) { [IO.File]::WriteAllText($path, $newText, (New-Object Text.UTF8Encoding($false))) }
  Write-Host "DIFF  $([IO.Path]::GetFileName($path))" -ForegroundColor Yellow
  $changed++
}

Write-Host ""
Write-Host "共 $($Files.Count) 个文件：改动 $changed，已是最新 $same，无标记跳过 $skipped" -ForegroundColor Cyan
if ($Check -and $changed -gt 0) { Write-Host "（-Check 模式，未写入）" -ForegroundColor DarkGray }
