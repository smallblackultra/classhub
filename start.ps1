# 一键启动：网站 + QQ 机器人桥接（集电26-1班 · ClassHub）
# 用法：双击同目录的「启动网站.bat」；或 powershell -File start.ps1
param([switch]$NoOpen)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = "D:\Program Files\Python313\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

function Test-Port([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

Write-Host "== 班级截止日 · ClassHub ==" -ForegroundColor Cyan
Write-Host ("目录: " + $root)

# 1) 网站
if (Test-Port 8000) {
    Write-Host "[1/2] 网站已在运行 (8000)" -ForegroundColor Green
} else {
    Write-Host "[1/2] 正在启动网站 ..."
    $logDir = Join-Path $root "data"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Start-Process -FilePath $python `
        -ArgumentList "-X", "utf8", "-m", "app", "--port", "8000" `
        -WorkingDirectory $root -WindowStyle Minimized `
        -RedirectStandardOutput (Join-Path $logDir "server.out.log") `
        -RedirectStandardError  (Join-Path $logDir "server.err.log")
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $r = Invoke-WebRequest "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
    }
    if ($ok) { Write-Host "      网站就绪 http://127.0.0.1:8000" -ForegroundColor Green }
    else { Write-Host "      启动超时，请看 data\server.err.log" -ForegroundColor Red }
}

# 2) 机器人桥接（读 deploy\bot.env.json）
if (Test-Port 8790) {
    Write-Host "[2/2] 机器人桥接已在运行 (8790)" -ForegroundColor Green
} else {
    $envFile = Join-Path $root "deploy\bot.env.json"
    if (Test-Path $envFile) {
        Write-Host "[2/2] 正在启动机器人桥接 ..."
        $cfg = Get-Content $envFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.classhub_token) { $env:CLASSHUB_TOKEN = $cfg.classhub_token }
        if ($cfg.onebot_url) { $env:ONEBOT_URL = $cfg.onebot_url }
        if ($cfg.bot_secret) { $env:BOT_WEBHOOK_SECRET = $cfg.bot_secret }
        if ($cfg.self_id) { $env:ONEBOT_SELF_ID = [string]$cfg.self_id }
        if ($cfg.group_names) { $env:GROUP_NAMES = ($cfg.group_names | ConvertTo-Json -Compress) }
        $env:CLASSHUB_URL = if ($cfg.classhub_url) { $cfg.classhub_url } else { "http://127.0.0.1:8000/daliy" }
        Start-Process -FilePath $python `
            -ArgumentList "-X", "utf8", "bot\onebot_bridge.py" `
            -WorkingDirectory $root -WindowStyle Minimized `
            -RedirectStandardOutput (Join-Path $root "data\bridge.out.log") `
            -RedirectStandardError  (Join-Path $root "data\bridge.err.log")
        Start-Sleep -Seconds 2
    } else {
        Write-Host "[2/2] 未找到 deploy\bot.env.json，跳过机器人" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "本机门户: http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host "本机 DDL: http://127.0.0.1:8000/daliy/" -ForegroundColor Cyan
Write-Host "公网门户: https://2026hfutintegratedcircuit1.com/" -ForegroundColor Cyan
Write-Host "公网 DDL: https://2026hfutintegratedcircuit1.com/daliy/" -ForegroundColor Cyan
Write-Host "管理员: 2026000000"
Write-Host "关闭窗口不会停止服务；停止请运行「停止网站.bat」"
if (-not $NoOpen) { Start-Sleep -Seconds 1; Start-Process "http://127.0.0.1:8000/" }
