param(
    [ValidateNotNullOrEmpty()]
    [string]$Model = "llama3.2:3b",

    [ValidateNotNullOrEmpty()]
    [string]$ModelsPath = "D:\Ollama\Models"
)

$ErrorActionPreference = "Stop"

try {
    $ModelsPath = [System.IO.Path]::GetFullPath($ModelsPath)
    if (Test-Path $ModelsPath -PathType Container) {
        Write-Host "Model directory already exists: $ModelsPath"
    }
    else {
        New-Item -ItemType Directory -Force -Path $ModelsPath | Out-Null
        Write-Host "Created model directory: $ModelsPath"
    }

    [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $ModelsPath, "User")
    $env:OLLAMA_MODELS = $ModelsPath

    $ollama = Get-Command "ollama" -CommandType Application -ErrorAction SilentlyContinue
    $installedOllama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if ($ollama) {
        $ollamaPath = $ollama.Source
        Write-Host "Ollama is already installed. Skipping installation."
    }
    elseif (Test-Path $installedOllama -PathType Leaf) {
        $ollamaPath = $installedOllama
        Write-Host "Ollama is already installed. Skipping installation."
    }
    else {
        Write-Host "Installing Ollama..."
        $installerUrl = "https://ollama.com/install.ps1"
        $installerScript = Invoke-RestMethod -Uri $installerUrl
        Invoke-Expression $installerScript

        $ollama = Get-Command "ollama" -CommandType Application -ErrorAction SilentlyContinue
        if ($ollama) {
            $ollamaPath = $ollama.Source
        }
        elseif (Test-Path $installedOllama -PathType Leaf) {
            $ollamaPath = $installedOllama
        }
        else {
            throw "Ollama CLI was not found after installation. Restart PowerShell and run this script again."
        }
    }

    $installedModels = & $ollamaPath list 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not check installed Ollama models (exit code $LASTEXITCODE): $installedModels"
    }

    $modelIsInstalled = $false
    foreach ($line in $installedModels) {
        $columns = "$line".Trim() -split "\s+"
        if ($columns.Count -gt 0 -and $columns[0] -eq $Model) {
            $modelIsInstalled = $true
            break
        }
    }

    if ($modelIsInstalled) {
        Write-Host "Model '$Model' is already installed. Skipping download."
    }
    else {
        Write-Host "Downloading model '$Model'..."
        & $ollamaPath pull $Model
        if ($LASTEXITCODE -ne 0) {
            throw "Ollama failed to download model '$Model' (exit code $LASTEXITCODE)."
        }
    }

    Write-Host "Installed models:"
    & $ollamaPath list
    if ($LASTEXITCODE -ne 0) {
        throw "Ollama could not list installed models (exit code $LASTEXITCODE)."
    }

    Write-Host "Installation completed. Model files are stored in: $ModelsPath"
}
catch {
    Write-Error "Installation failed: $($_.Exception.Message)"
    exit 1
}
