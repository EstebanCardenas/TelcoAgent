#Requires -Version 5.1
<#
.SYNOPSIS
    Construye y publica la imagen multi-arquitectura del Asesor de Retención (Agente 2).

.DESCRIPTION
    1. docker login (credenciales interactivas de Docker Hub)
    2. buildx: linux/amd64 (Ryzen / Intel) y linux/arm64 (Mac ARM)
    3. push a Docker Hub: estebancardenas/telco-agente2:2026-20

    Usa Dockerfile.agente2. El proceso publicado es el servidor HTTP del
    puerto 8090, no el CLI del Agente 1.

    Un `docker build` + `docker push` clásico solo publica la arquitectura del
    host. Para que la misma etiqueta sirva en Ryzen y en Mac ARM hay que usar
    buildx y enviar el manifiesto al registro en el mismo paso (--push).

.EXAMPLE
    .\scripts\publicar-imagen-agente2.ps1
#>
# Docker escribe progreso en stderr. Con Stop, PowerShell aborta aunque el
# comando haya salido 0 (o 1 en un inspect esperado). Se valida $LASTEXITCODE.
$ErrorActionPreference = "Continue"

$Image = "estebancardenas/telco-agente2:2026-20"
$Dockerfile = "Dockerfile.agente2"
$Platforms = "linux/amd64,linux/arm64"
$Builder = "telco-multiarch"
$Root = Split-Path -Parent $PSScriptRoot

function Assert-Docker {
    param([string]$Accion)
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Fallo: $Accion (codigo $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
}

Set-Location $Root

Write-Host "==> 1. Build: preparar builder buildx ($Platforms)"
docker buildx inspect $Builder 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    docker buildx create --name $Builder --driver docker-container --bootstrap
    Assert-Docker "docker buildx create $Builder"
}
docker buildx use $Builder
Assert-Docker "docker buildx use $Builder"

Write-Host "==> 2. Docker login"
docker login
Assert-Docker "docker login"

Write-Host "==> 3. Docker push: buildx build -f $Dockerfile --platform $Platforms -t $Image --push"
# --push sube el manifiesto multi-arch. --load solo admite una plataforma.
docker buildx build -f (Join-Path $Root $Dockerfile) --platform $Platforms -t $Image --push $Root
Assert-Docker "docker buildx build --push"

Write-Host "Listo: $Image ($Platforms)"
