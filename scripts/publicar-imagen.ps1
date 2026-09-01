#Requires -Version 5.1
<#
.SYNOPSIS
    Construye y publica la imagen multi-arquitectura del agente Telco Andina.

.DESCRIPTION
    1. docker login (credenciales interactivas de Docker Hub)
    2. buildx: linux/amd64 (Ryzen / Intel) y linux/arm64 (Mac ARM)
    3. push a Docker Hub: estebancardenas/telco:2026-20

    Un `docker build` + `docker push` clásico solo publica la arquitectura del
    host. Para que la misma etiqueta sirva en Ryzen y en Mac ARM hay que usar
    buildx y enviar el manifiesto al registro en el mismo paso (--push).

.EXAMPLE
    .\scripts\publicar-imagen.ps1
#>
$ErrorActionPreference = "Stop"

$Image = "estebancardenas/telco:2026-20"
$Platforms = "linux/amd64,linux/arm64"
$Builder = "telco-multiarch"
$Root = Split-Path -Parent $PSScriptRoot

Set-Location $Root

Write-Host "==> 1. Build: preparar builder buildx ($Platforms)"
$inspect = docker buildx inspect $Builder 2>$null
if ($LASTEXITCODE -ne 0) {
    docker buildx create --name $Builder --driver docker-container --bootstrap
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
docker buildx use $Builder
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> 2. Docker login"
docker login
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> 3. Docker push: buildx build --platform $Platforms -t $Image --push"
# --push sube el manifiesto multi-arch. --load solo admite una plataforma.
docker buildx build --platform $Platforms -t $Image --push $Root
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Listo: $Image ($Platforms)"
