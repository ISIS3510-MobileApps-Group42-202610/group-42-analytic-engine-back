# Script de prueba para BQ4 - Sincronización Android
# Envía eventos de prueba para diferentes sellers

Write-Host "🧪 PROBANDO SINCRONIZACIÓN BQ4 - ANDROID → BACKEND" -ForegroundColor Cyan
Write-Host ""

$baseUrl = "http://127.0.0.1:8000/api/events"

# Seller 101 - Muy rápido (2 min)
Write-Host "📤 Enviando evento: Seller 101 (2 min - muy rápido)..." -ForegroundColor Yellow
$body1 = @{
    event_name = "seller_avg_response_time"
    user_id = 201
    properties = @{
        seller_id = "101"
        avg_minutes = "2.0"
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    }
} | ConvertTo-Json

try {
    $response1 = Invoke-RestMethod -Uri $baseUrl -Method Post -Body $body1 -ContentType "application/json"
    Write-Host "✅ Seller 101: $($response1.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}

Start-Sleep -Milliseconds 500

# Seller 102 - Rápido (5 min)
Write-Host "📤 Enviando evento: Seller 102 (5 min - rápido)..." -ForegroundColor Yellow
$body2 = @{
    event_name = "seller_avg_response_time"
    user_id = 202
    properties = @{
        seller_id = "102"
        avg_minutes = "5.0"
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    }
} | ConvertTo-Json

try {
    $response2 = Invoke-RestMethod -Uri $baseUrl -Method Post -Body $body2 -ContentType "application/json"
    Write-Host "✅ Seller 102: $($response2.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}

Start-Sleep -Milliseconds 500

# Seller 103 - Medio (15 min)
Write-Host "📤 Enviando evento: Seller 103 (15 min - medio)..." -ForegroundColor Yellow
$body3 = @{
    event_name = "seller_avg_response_time"
    user_id = 203
    properties = @{
        seller_id = "103"
        avg_minutes = "15.0"
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    }
} | ConvertTo-Json

try {
    $response3 = Invoke-RestMethod -Uri $baseUrl -Method Post -Body $body3 -ContentType "application/json"
    Write-Host "✅ Seller 103: $($response3.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}

Start-Sleep -Milliseconds 500

# Seller 104 - Lento (35 min)
Write-Host "📤 Enviando evento: Seller 104 (35 min - lento)..." -ForegroundColor Yellow
$body4 = @{
    event_name = "seller_avg_response_time"
    user_id = 204
    properties = @{
        seller_id = "104"
        avg_minutes = "35.0"
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    }
} | ConvertTo-Json

try {
    $response4 = Invoke-RestMethod -Uri $baseUrl -Method Post -Body $body4 -ContentType "application/json"
    Write-Host "✅ Seller 104: $($response4.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}

Start-Sleep -Milliseconds 500

# Seller 105 - Muy lento (60 min)
Write-Host "📤 Enviando evento: Seller 105 (60 min - muy lento)..." -ForegroundColor Yellow
$body5 = @{
    event_name = "seller_avg_response_time"
    user_id = 205
    properties = @{
        seller_id = "105"
        avg_minutes = "60.0"
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    }
} | ConvertTo-Json

try {
    $response5 = Invoke-RestMethod -Uri $baseUrl -Method Post -Body $body5 -ContentType "application/json"
    Write-Host "✅ Seller 105: $($response5.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}

Start-Sleep -Milliseconds 500

# Seller 101 - Segundo evento (3 min)
Write-Host "📤 Enviando segundo evento: Seller 101 (3 min)..." -ForegroundColor Yellow
$body6 = @{
    event_name = "seller_avg_response_time"
    user_id = 206
    properties = @{
        seller_id = "101"
        avg_minutes = "3.0"
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    }
} | ConvertTo-Json

try {
    $response6 = Invoke-RestMethod -Uri $baseUrl -Method Post -Body $body6 -ContentType "application/json"
    Write-Host "✅ Seller 101 (2do evento): $($response6.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}

Start-Sleep -Milliseconds 500

# Seller 102 - Segundo evento (7 min)
Write-Host "📤 Enviando segundo evento: Seller 102 (7 min)..." -ForegroundColor Yellow
$body7 = @{
    event_name = "seller_avg_response_time"
    user_id = 207
    properties = @{
        seller_id = "102"
        avg_minutes = "7.0"
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    }
} | ConvertTo-Json

try {
    $response7 = Invoke-RestMethod -Uri $baseUrl -Method Post -Body $body7 -ContentType "application/json"
    Write-Host "✅ Seller 102 (2do evento): $($response7.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "✅ PRUEBA COMPLETADA" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Eventos enviados:" -ForegroundColor Cyan
Write-Host "  - Seller 101: 2 eventos (promedio esperado: 2.5 min)" -ForegroundColor White
Write-Host "  - Seller 102: 2 eventos (promedio esperado: 6.0 min)" -ForegroundColor White
Write-Host "  - Seller 103: 1 evento (15 min)" -ForegroundColor White
Write-Host "  - Seller 104: 1 evento (35 min)" -ForegroundColor White
Write-Host "  - Seller 105: 1 evento (60 min)" -ForegroundColor White
Write-Host ""
Write-Host "🌐 Abre el dashboard para ver los resultados:" -ForegroundColor Cyan
Write-Host "   http://127.0.0.1:8000/api/dashboard/bq4" -ForegroundColor Yellow
Write-Host ""
Write-Host "📈 Deberías ver:" -ForegroundColor Cyan
Write-Host "  - Top fastest sellers: Seller 101 (2.5 min), Seller 102 (6 min)" -ForegroundColor White
Write-Host "  - Slowest sellers: Seller 105 (60 min), Seller 104 (35 min)" -ForegroundColor White
Write-Host "  - Distribution: 2 fast (<5 min), 2 medium (5-30 min), 2 slow (>30 min)" -ForegroundColor White
Write-Host ""
