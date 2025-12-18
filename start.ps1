# LLM Council - Start script (PowerShell)

Write-Host "Starting LLM Council..." -ForegroundColor Cyan
Write-Host ""

# Start backend
Write-Host "Starting backend on http://localhost:8001..." -ForegroundColor Yellow
$backend = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    uv run python -m backend.main
}

# Wait for backend to start
Start-Sleep -Seconds 2

# Start frontend
Write-Host "Starting frontend on http://localhost:5177..." -ForegroundColor Yellow
$frontend = Start-Job -ScriptBlock {
    Set-Location "$using:PWD\frontend"
    npm run dev
}

Write-Host ""
Write-Host "LLM Council is running!" -ForegroundColor Green
Write-Host "  Backend:  http://localhost:8001"
Write-Host "  Frontend: http://localhost:5177"
Write-Host ""
Write-Host "Press Ctrl+C to stop both servers" -ForegroundColor Gray

try {
    while ($true) {
        # Show output from jobs
        Receive-Job -Job $backend, $frontend
        Start-Sleep -Milliseconds 500
    }
}
finally {
    Write-Host "`nStopping servers..." -ForegroundColor Yellow
    Stop-Job -Job $backend, $frontend
    Remove-Job -Job $backend, $frontend
}
