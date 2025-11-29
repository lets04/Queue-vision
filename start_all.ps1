param(
	[string]$cameraUrl
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Iniciando backend, detector y frontend desde: $scriptDir"

# Backend
Start-Process -FilePath "powershell" -ArgumentList "-NoExit","-Command","cd '$scriptDir'; python backend.py"
Start-Sleep -Milliseconds 500

# Vision detector 
$vdCmd = "cd '$scriptDir'; python vision_detector.py"
if ($cameraUrl) { $vdCmd += " --camera-url '$cameraUrl'" }
Start-Process -FilePath "powershell" -ArgumentList "-NoExit","-Command",$vdCmd
Start-Sleep -Milliseconds 500

# Frontend (Vite)
$frontendDir = Join-Path $scriptDir "dashboard-filas"
Start-Process -FilePath "powershell" -ArgumentList "-NoExit","-Command","cd '$frontendDir'; npm run dev"

Write-Host "Se lanzaron los procesos. Revisa las ventanas abiertas para ver logs."