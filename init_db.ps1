# Wait for the Postgres server to become available.
Write-Host "Waiting for postgres..."

while (-not (Test-NetConnection -ComputerName $env:DB_HOST -Port $env:DB_PORT).TcpTestSucceeded) {
    Write-Host "$(Get-Date) - waiting for database to start"
    Start-Sleep -Seconds 2
}

# Run the SQL script to create the `scripts` table.
$sqlScript = @"
CREATE TABLE IF NOT EXISTS scripts (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255),
    data BYTEA,
    mimetype VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"@

$psqlCommand = @"
psql -v ON_ERROR_STOP=1 --username "$env:DB_USER" --dbname "$env:DB_NAME" --host "$env:DB_HOST"
"@

$sqlScript | & $psqlCommand
Write-Host "Database initialized successfully."


# Hand start the python app by making sure the venv is activated and using `flask run --host=0.0.0.0 --port=9988`

Write-Host "Starting Python app..."
$pythonCommand = "flask run --host=0.0.0.0 --port=9988"
Invoke-Expression $pythonCommand
Write-Host "Python app started successfully."
