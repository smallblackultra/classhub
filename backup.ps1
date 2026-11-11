# 班级截止日 · ClassHub —— 一键备份
#   · 数据库用 SQLite 在线备份（网站开着也能备，不会备份到半个文件）
#   · 再把程序文件 + 刚备好的数据库打成一个 zip，放到「备份」目录
# 用法：双击「备份网站.bat」
$ErrorActionPreference = "Stop"
$Root  = $PSScriptRoot
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Dest  = Join-Path $Root "备份"

Write-Host ""
Write-Host "== 班级截止日 · ClassHub ==" -ForegroundColor Cyan
Write-Host "网站目录: $Root"
Write-Host ""

# ---------- 1. 找 Python ----------
$Candidates = @(
    "D:\Program Files\Python313\python.exe",
    "C:\Program Files\Python313\python.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
)
$Python = $null
foreach ($c in $Candidates) { if (Test-Path $c) { $Python = $c; break } }
if (-not $Python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python) {
    Write-Host "[错误] 没找到 Python，请先确认网站能正常启动。" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
Write-Host "Python: $Python"

# ---------- 2. 在线备份数据库 ----------
$DbOut = Join-Path $Root "data\backup"
$BackupStart = (Get-Date).AddSeconds(-2)
Write-Host "[1/2] 正在备份数据库 ..."
Push-Location $Root
try {
    & $Python -X utf8 -m app --backup --backup-out $DbOut
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[警告] 数据库备份返回 $LASTEXITCODE，继续打包已有文件。" -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}

# ---------- 3. 打包 ----------
Write-Host "[2/2] 正在打包网站文件 ..."
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$Tmp = Join-Path $env:TEMP ("cdh-backup-" + $Stamp)
if (Test-Path $Tmp) { Remove-Item $Tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

# 程序文件（不含 data、备份、临时目录）
$null = robocopy $Root $Tmp /E /NFL /NDL /NJH /NJS /NP `
    /XD (Join-Path $Root "data") (Join-Path $Root "备份") (Join-Path $Root ".tmp") `
    /XF *.log
if ($LASTEXITCODE -ge 8) { Write-Host "[警告] 复制时有文件被占用，已跳过。" -ForegroundColor Yellow }

# 把本次备份的数据库放进包里（恢复时放回 data\classes\<班级>\classhub.db）
$DbDst = Join-Path $Tmp "data\backup"
New-Item -ItemType Directory -Force -Path $DbDst | Out-Null
if (Test-Path $DbOut) {
    Get-ChildItem $DbOut -Filter "*.db" -File |
        Where-Object { $_.LastWriteTime -ge $BackupStart } |
        ForEach-Object { Copy-Item $_.FullName $DbDst -Force }
}

# 密码加密密钥：换机恢复时不能丢，否则管理员「查看密码」不可用
$Secret = Join-Path $Root "data\.secret"
if (Test-Path $Secret) {
    $DataDst = Join-Path $Tmp "data"
    New-Item -ItemType Directory -Force -Path $DataDst | Out-Null
    Copy-Item $Secret (Join-Path $DataDst ".secret") -Force
}

$Zip = Join-Path $Dest ("ClassHub-" + $Stamp + ".zip")
Compress-Archive -Path (Join-Path $Tmp "*") -DestinationPath $Zip -CompressionLevel Optimal
Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue

# 只保留最近 10 个备份
Get-ChildItem $Dest -Filter "ClassHub-*.zip" -File |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 10 |
    Remove-Item -Force -ErrorAction SilentlyContinue

$Size = [math]::Round((Get-Item $Zip).Length / 1MB, 2)
Write-Host ""
Write-Host "[完成] 备份已生成：" -ForegroundColor Green
Write-Host "       $Zip  ($Size MB)"
Write-Host ""
Write-Host "恢复方法：解压后，把 data\backup 里的 .db 放回" -ForegroundColor DarkGray
Write-Host "          data\classes\<班级目录>\classhub.db（portal 为 data\portal.db）" -ForegroundColor DarkGray
Write-Host "          保留 data\.secret，否则管理员加密密码无法解密" -ForegroundColor DarkGray
Write-Host ""
if (-not $env:CDH_NO_PAUSE) { Read-Host "按回车关闭" }
