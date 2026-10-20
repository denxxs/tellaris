# Start the API and the web app together. Ctrl+C stops both.
$root = $PSScriptRoot
$api = Start-Process -PassThru -NoNewWindow -FilePath python -ArgumentList "-m", "oracle", "--port", "8000" -WorkingDirectory "$root\backend"
try {
    Set-Location "$root\frontend"
    npm run dev -- --port 3000
}
finally {
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
