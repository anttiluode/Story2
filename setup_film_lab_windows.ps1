# One-time Windows installer for Story2 Film Lab + DreamShaper 8.
# Uses a separate .film-venv to avoid changing existing Python/Torch projects.
# NVIDIA driver must support the selected CUDA wheel.
param(
    [switch]$SkipModelDownload,
    [string]$CudaIndex = "https://download.pytorch.org/whl/cu126"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = @("py","-3.12")
& py -3.12 --version *> $null
if ($LASTEXITCODE -ne 0) {
    $py = @("py","-3.13")
    & py -3.13 --version *> $null
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 or 3.13 is required. Install Python and retry." }
}
Write-Host "Creating isolated Film Lab environment using $($py -join ' ')" -ForegroundColor Cyan
& $py[0] $py[1] -m venv ".film-venv"
if ($LASTEXITCODE -ne 0) { throw "Virtual environment setup failed." }
$python = Join-Path $PSScriptRoot ".film-venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
Write-Host "Installing NVIDIA CUDA PyTorch. This is a large download." -ForegroundColor Cyan
& $python -m pip install torch torchvision --index-url $CudaIndex
if ($LASTEXITCODE -ne 0) {
    throw "CUDA PyTorch install failed. Check the Windows/CUDA selector at https://pytorch.org/get-started/locally/ and retry with -CudaIndex."
}
& $python -m pip install -r requirements-video.txt -r requirements-video-ai.txt
if ($LASTEXITCODE -ne 0) { throw "AI Python dependencies failed to install." }
& $python -c "import torch; print('Torch', torch.__version__); print('CUDA detected:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No GPU')"
if ($LASTEXITCODE -ne 0) { throw "PyTorch verification failed." }
if (-not $SkipModelDownload) {
    Write-Host "Downloading DreamShaper 8 once to models\dreamshaper-8" -ForegroundColor Cyan
    & $python tools\model_setup.py --download
    if ($LASTEXITCODE -ne 0) { throw "Model download failed. To resume later run: .film-venv\Scripts\python.exe tools\model_setup.py --download" }
}
Write-Host "Film Lab setup complete." -ForegroundColor Green
Write-Host "Launch: .film-venv\Scripts\python.exe tools\film_lab_gui.py"
Write-Host "Whole-book CLI: .film-venv\Scripts\python.exe tools\film_batch.py --audio-dir audio --join --strict-audio"
