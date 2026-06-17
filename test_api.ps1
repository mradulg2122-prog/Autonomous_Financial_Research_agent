$body = @{
    query = "Analyze Apple Inc and provide a financial report"
    company_ticker = "AAPL"
    company_name = "Apple Inc."
} | ConvertTo-Json

Write-Host "Testing POST /api/v1/research ..."
try {
    $r = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/research" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -ErrorVariable restErr
    Write-Host "SUCCESS (HTTP 202):"
    $r | ConvertTo-Json
    $sessionId = $r.session_id
    Write-Host ""
    Write-Host "Session ID: $sessionId"
    Write-Host "Waiting 5 seconds then checking status..."
    Start-Sleep -Seconds 5
    $status = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/research/$sessionId" -Method GET
    Write-Host "Session Status:"
    $status | ConvertTo-Json
} catch {
    Write-Host "FAILED:"
    Write-Host $_.Exception.Message
    if ($_.ErrorDetails) {
        Write-Host "Response body:"
        Write-Host $_.ErrorDetails.Message
    }
}
