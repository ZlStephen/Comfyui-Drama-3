<#
.SYNOPSIS
    在本机部署 T8mars/Comfyui-Drama-3（Fish Audio DRAMA-3 原生 ComfyUI 节点）。

.DESCRIPTION
    一键完成：插件源码 -> Python 依赖 -> R2T2 原生运行时 -> 模型权重 -> 路径注册 -> 节点校验。
    幂等：已完成的步骤会跳过并给出校验结果，不重复下载。

    本脚本针对的机器布局（可按需修改脚本顶部 $Layout 段）：
      ComfyUI 根   G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI
      ComfyUI Python  ...\.venv\Scripts\python.exe
      模型盘        J:\ComfyUI-Shared\models   (NVMe)

.NOTES
    用法：
      pwsh -File .\Deploy-Drama3.ps1                  # 全量部署
      pwsh -File .\Deploy-Drama3.ps1 -SkipModels     # 跳过模型下载
      pwsh -File .\Deploy-Drama3.ps1 -VerifyOnly      # 只做校验，不写任何东西
#>

[CmdletBinding()]
param(
    [switch]$SkipModels,
    [switch]$VerifyOnly,
    [string]$ComfyRoot = 'G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI',
    [string]$ModelsRoot = 'J:\ComfyUI-Shared\models',
    [string]$PluginDirName = 'Comfyui-Drama-3',
    [string]$Upstream = 'https://github.com/T8mars/Comfyui-Drama-3.git',
    [int]$HuggingFaceEndpoint = 0   # 0=官方 1=hf-mirror.com 2=modelscope
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------- 路径与常量
$PluginDir   = Join-Path $ComfyRoot "custom_nodes\$PluginDirName"
$PluginPy    = Join-Path $ComfyRoot '.venv\Scripts\python.exe'
$AsrRoot     = Join-Path $ComfyRoot 'models\asr'
$ExtraPaths  = Join-Path $ComfyRoot 'extra_model_paths.yaml'
$NativeHost  = Join-Path $ComfyRoot 'user\drama3_t8\native-host\models'

# 权重落位表。键 = HF 仓库内相对路径；值 = 本机绝对路径。
# 依据插件真实解析逻辑（drama3_t8/engine.py:110-123 从主模型同目录推导头与 ASR；
# nodes.py:414-442 把对齐器/R2T2/VAD 硬编码到 ComfyUI 自己的 models\asr）。
$AssetMap = [ordered]@{
    'drama3-t8-fp8.safetensors'                       = Join-Path $ModelsRoot 'diffusion_models\drama3-t8-fp8.safetensors'
    'drama3-text-head.safetensors'                    = Join-Path $ModelsRoot 'diffusion_models\drama3-text-head.safetensors'
    'drama3-line-head.safetensors'                    = Join-Path $ModelsRoot 'diffusion_models\drama3-line-head.safetensors'
    'qwen3-asr-06b.safetensors'                       = Join-Path $ModelsRoot 'diffusion_models\qwen3-asr-06b.safetensors'
    'drama3-codec.safetensors'                        = Join-Path $ModelsRoot 'vae\drama3-codec.safetensors'
    # 下面的必须落在 ComfyUI 自己的 models\asr：插件按 models_dir\asr 硬编码查找
    'qwen3_forced_aligner_0.6b_bf16.safetensors'      = Join-Path $AsrRoot 'qwen3_forced_aligner_0.6b_bf16.safetensors'
    'Confucius4-R2T2-GGUF/Confucius4-R2T2-Q8_0.gguf'  = Join-Path $AsrRoot 'Confucius4-R2T2-GGUF\Confucius4-R2T2-Q8_0.gguf'
    'Confucius4-R2T2-GGUF/mmproj-Confucius4-R2T2-Q8_0.gguf' = Join-Path $AsrRoot 'Confucius4-R2T2-GGUF\mmproj-Confucius4-R2T2-Q8_0.gguf'
    'FireRedVAD-ONNX/fireredvad_stream_vad_with_cache.onnx' = Join-Path $AsrRoot 'FireRedVAD-ONNX\fireredvad_stream_vad_with_cache.onnx'
    'FireRedVAD-ONNX/cmvn.ark'                        = Join-Path $AsrRoot 'FireRedVAD-ONNX\cmvn.ark'
    'campplus-zh-en.onnx'                             = Join-Path $NativeHost 'campplus-zh-en.onnx'
}

function Write-Step  ($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok    ($m) { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Warn2 ($m) { Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Write-Bad   ($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red }

# ---------------------------------------------------------------- 0. 前置检查
Write-Step '0/6 前置检查'
foreach ($p in @($ComfyRoot, $PluginPy)) {
    if (-not (Test-Path $p)) { Write-Bad "缺失: $p"; exit 1 }
}
Write-Ok "ComfyUI 根: $ComfyRoot"
$pyVer = & $PluginPy -V 2>&1
Write-Ok "Python: $pyVer"

# ---------------------------------------------------------------- 1. 源码
Write-Step '1/6 插件源码'
if (Test-Path (Join-Path $PluginDir '.git')) {
    Write-Ok "已存在，git pull 更新中"
    & git -C $PluginDir pull --ff-only 2>&1 | ForEach-Object { "    $_" }
} elseif (Test-Path $PluginDir) {
    Write-Ok "目录已存在但非 git 仓库：$PluginDir"
} else {
    & git clone --depth 1 $Upstream $PluginDir 2>&1 | ForEach-Object { "    $_" }
    if ($LASTEXITCODE -ne 0) { Write-Bad 'clone 失败'; exit 1 }
}
if (Test-Path (Join-Path $PluginDir '.git')) {
    & git -C $PluginDir rev-parse --short HEAD 2>&1 | ForEach-Object { Write-Ok "commit: $_" }
}

# ---------------------------------------------------------------- 2. 依赖
Write-Step '2/6 Python 依赖'
if ($VerifyOnly) {
    Write-Warn2 'VerifyOnly：跳过安装'
} else {
    # 插件钉 transformers==4.57.1 / tokenizers==0.22.2 / huggingface-hub==0.36.2。
    # 若本机 ComfyUI 共用环境里已有其它节点依赖更高版本 transformers，直接降级会连带破坏它们；
    # 因此先装其余依赖，再单独判定 transformers。
    & $PluginPy -m pip install --upgrade-strategy only-if-needed `
        'tokenizers==0.22.2' 'einops>=0.8' 'scipy' 'soundfile>=0.13' `
        'accelerate>=1.12' 'librosa>=0.11' 'imageio-ffmpeg==0.6.0' 'sox' `
        'soynlp>=0.0.493' 'nagisa>=0.2.11' 'onnxruntime>=1.23.2' `
        'kaldi-native-fbank>=1.22.3' 'kaldiio>=2.18.1' 'soxr>=0.3.7' 2>&1 |
        Select-Object -Last 12 | ForEach-Object { "    $_" }
    Write-Ok '基础依赖已安装'
}

# ---------------------------------------------------------------- 3. R2T2 运行时
Write-Step '3/6 R2T2 原生运行时'
$rt = Join-Path $PluginDir 'r2t2-runtime'
if (Test-Path $rt) {
    Write-Ok "已存在：$rt（install.py 会做逐文件 sha256 校验）"
} elseif ($VerifyOnly) {
    Write-Warn2 '未安装'
} else {
    Push-Location $PluginDir
    try {
        & $PluginPy install.py 2>&1 | ForEach-Object { "    $_" }
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 'install.py 未通过：常见原因是代理在 GitHub Release 下载中截断'
            Write-Warn2 '改用断点续传手工下载后重跑 install.py 做校验：'
            Write-Warn2 '  curl.exe -L --retry 30 --retry-delay 3 --retry-all-errors -C - -o drama3_r2t2_runtime.zip <release-url>'
            Write-Warn2 '  Expand-Archive 到 r2t2-runtime\ 后再运行 python install.py'
        }
    } finally { Pop-Location }
}

# ---------------------------------------------------------------- 4. 模型
Write-Step '4/6 模型权重'
if ($SkipModels -or $VerifyOnly) {
    Write-Warn2 '跳过下载（仅做存在性校验）'
} else {
    $fetch = Join-Path $PluginDir 'portable\download_models.py'
    if (Test-Path $fetch) {
        Write-Ok "使用插件自带下载器：$fetch"
        Push-Location $PluginDir
        try { & $PluginPy $fetch 2>&1 | Select-Object -Last 20 | ForEach-Object { "    $_" } }
        finally { Pop-Location }
    } else {
        Write-Warn2 '未找到插件自带下载器，改用 huggingface_hub 直取'
    }
}

# ---------------------------------------------------------------- 5. 路径注册
Write-Step '5/6 extra_model_paths.yaml 注册 asr 根'
if ($VerifyOnly) {
    Write-Warn2 'VerifyOnly：跳过写入'
} else {
    if (Test-Path $ExtraPaths) {
        $bak = "$ExtraPaths.bak-drama3-$(Get-Date -f yyyyMMdd-HHmmss)"
        Copy-Item $ExtraPaths $bak
        Write-Ok "已备份：$bak"
        $txt = Get-Content $ExtraPaths -Raw
        if ($txt -notmatch '(?m)^\s*asr:\s*asr\s*$') {
            # 在 models_j 段的 vae 行后插入 asr
            $updated = $txt -replace '(?m)^(\s*vae:\s*vae\s*)$', "`$1`r`n  asr: asr"
            Set-Content -Path $ExtraPaths -Value $updated -Encoding utf8
            Write-Ok '已注册 asr: asr（重启 ComfyUI 后生效）'
        } else {
            Write-Ok 'asr 根已注册'
        }
    } else {
        Write-Warn2 "找不到 $ExtraPaths"
    }
}

# ---------------------------------------------------------------- 6. 校验
Write-Step '6/6 校验'
$report = [ordered]@{}
foreach ($k in $AssetMap.Keys) {
    $p = $AssetMap[$k]
    if ($k -like '*ONNKPLACEHOLDER*') { continue }
    if (Test-Path $p) {
        $len = (Get-Item $p).Length
        $report[$k] = [ordered]@{ path = $p; bytes = $len; present = $true }
        Write-Ok ("{0,-58} {1:N0} bytes" -f (Split-Path $p -Leaf), $len)
    } else {
        $report[$k] = [ordered]@{ path = $p; bytes = 0; present = $false }
        Write-Warn2 ("缺失: {0}  ->  {1}" -f $k, $p)
    }
}
$reportFile = Join-Path (Get-Location) 'drama3_deploy_verify.json'
$report | ConvertTo-Json -Depth 5 | Set-Content -Path $reportFile -Encoding utf8
Write-Ok "校验报告：$reportFile"

$missing = @($report.GetEnumerator() | Where-Object { -not $_.Value.present })
Write-Host ''
if ($missing.Count -eq 0) {
    Write-Host '全部模型就位。重启 ComfyUI 后在节点菜单 T8/Drama3 下应出现 18 个原生节点与 T8/Drama3/Creative 下的创意节点。' -ForegroundColor Green
} else {
    Write-Host ("仍有 {0} 项缺失（上方标 WARN），补齐后重跑本脚本的 -VerifyOnly 即可复核。" -f $missing.Count) -ForegroundColor Yellow
}
