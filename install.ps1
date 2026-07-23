# Instalador de la Fábrica de Carruseles (Windows / PowerShell).
# Copia la skill a ~\.claude\skills\carrusel\, prepara su entorno de Python,
# y (al actualizar) conserva tus llaves, tu marca y tus carruseles.

$ErrorActionPreference = "Stop"

$SkillName = "carrusel"
$RepoUrl   = "https://github.com/luiscordova-dev/fabrica-carruseles.git"
$Target    = Join-Path $HOME ".claude\skills\$SkillName"
$Backup    = $null

function Remove-Robust($path) {
  if (Test-Path $path) {
    attrib -r "$path\*" /s /d 2>$null
    Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
    if (Test-Path $path) { cmd /c "rmdir /s /q `"$path`"" | Out-Null }
  }
}

Write-Host ""
Write-Host "  Instalando Fabrica de Carruseles..."
Write-Host ""

# 1) Verificar Claude Code (~/.claude)
if (-not (Test-Path (Join-Path $HOME ".claude"))) {
  Write-Host "  X  No encuentro la carpeta ~/.claude. Instala Claude Code primero: https://claude.com/claude-code"
  exit 1
}

# 2) Verificar git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "  X  Necesitas git instalado."
  exit 1
}

New-Item -ItemType Directory -Force -Path (Join-Path $HOME ".claude\skills") | Out-Null

# 3) Si ya existe, preguntar y respaldar datos del usuario (sin borrar todavía)
if (Test-Path $Target) {
  $resp = Read-Host "  Ya tienes la skill instalada. Actualizar? (s/n)"
  if ($resp -notmatch '^[Ss]') { Write-Host "  Ok, no toco nada."; exit 0 }
  $Backup = Join-Path $env:TEMP ("carrusel_bkp_" + [System.Guid]::NewGuid().ToString())
  New-Item -ItemType Directory -Force -Path $Backup | Out-Null
  if (Test-Path "$Target\.env")               { Copy-Item "$Target\.env" "$Backup\.env" -Force }
  if (Test-Path "$Target\config\marca.json")  { Copy-Item "$Target\config\marca.json" "$Backup\marca.json" -Force }
  if (Test-Path "$Target\outputs")            { Copy-Item "$Target\outputs" "$Backup\outputs" -Recurse -Force }
}

# 4) Clonar a un TEMPORAL primero; solo si sale bien reemplazamos la instalación
$Tmp = Join-Path $env:TEMP ("carrusel_" + [System.Guid]::NewGuid().ToString())
git clone --depth 1 --quiet $RepoUrl $Tmp
if ($LASTEXITCODE -ne 0) {
  Write-Host "  X  No pude descargar la skill (sin internet o el repo no es público). No toqué tu instalación."
  Remove-Robust $Tmp
  if ($Backup) { Remove-Robust $Backup }
  exit 1
}
Remove-Robust (Join-Path $Tmp ".git")
Remove-Robust $Target
Move-Item $Tmp $Target

# 5) Restaurar datos del usuario
if ($Backup) {
  if (Test-Path "$Backup\.env")        { Copy-Item "$Backup\.env" "$Target\.env" -Force }
  if (Test-Path "$Backup\marca.json")  { Copy-Item "$Backup\marca.json" "$Target\config\marca.json" -Force }
  if (Test-Path "$Backup\outputs")     { Copy-Item "$Backup\outputs\*" "$Target\outputs\" -Recurse -Force -ErrorAction SilentlyContinue }
  Remove-Robust $Backup
  Write-Host "  Conserve tus llaves, tu marca y tus carruseles."
}

# 6) Preparar entorno de Python (venv)
$Py = $null
foreach ($cand in @("python","py","python3")) {
  if (Get-Command $cand -ErrorAction SilentlyContinue) { $Py = $cand; break }
}
if ($Py) {
  Write-Host "  Preparando entorno de Python..."
  try {
    & $Py -m venv "$Target\venv"
    & "$Target\venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    & "$Target\venv\Scripts\python.exe" -m pip install --quiet -r "$Target\requirements.txt"
    Write-Host "  Entorno listo."
  } catch {
    Write-Host "  Aviso: corre luego  `"$Target\venv\Scripts\python.exe`" -m pip install -r `"$Target\requirements.txt`""
  }
} else {
  Write-Host "  Aviso: no encontre Python. Instalalo (python.org, marca 'Add to PATH')."
}

Write-Host ""
Write-Host "  Listo! La skill quedo en: $Target"
Write-Host "  Abre Claude Code y escribe:  /carrusel"
Write-Host ""
