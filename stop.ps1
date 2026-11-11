# 停止：网站 + 机器人桥接
$root = $PSScriptRoot
$stopped = 0
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | ForEach-Object {
    $cmd = $_.CommandLine
    if ($cmd -and (($cmd -like "*app*--port*8000*") -or ($cmd -like "*onebot_bridge.py*"))) {
        try { Stop-Process -Id $_.ProcessId -Force; $stopped++ } catch { }
    }
}
Write-Host ("已停止 " + $stopped + " 个进程") -ForegroundColor Yellow
Start-Sleep -Seconds 1
