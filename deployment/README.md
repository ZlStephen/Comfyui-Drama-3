# Comfyui-Drama-3 · Windows 本地部署分支

这是 `T8mars/Comfyui-Drama-3` 的 **Windows + 单卡 24GB 显存** 部署分支（fork 自上游 v0.3.2）。
分支只增加 `deployment/` 目录，**插件源码与上游保持零差异**，随时可以 rebase 回上游。

> 上游：<https://github.com/T8mars/Comfyui-Drama-3> · 原作者：T8 Studio / Fish Audio DRAMA-3

---

## 1. 这个分支解决什么问题

上游插件本身是完整的，但它是**按"官方 Studio 桌面版"布局**写的：所有模型路径都相对
`ComfyUI/models` 解析。普通用户在 Windows 上用自己的多盘模型库时，会遇到三个具体的坑：

| 坑 | 现象 | 本分支的处理 |
|---|---|---|
| **相对路径不查共享盘** | 模型明明在 `J:\ComfyUI-Shared\models`，节点却报文件不存在 | 全部改为绝对路径，并给出推导依据 |
| **辅助模型的真实位置和直觉不同** | text-head / line-head / ASR 模型不在 `models\asr` | 见下表 —— 它们跟着**主模型**走 |
| **R2T2 / 对齐器被硬编码** | 这两个插件按 `ComfyUI/models/asr` 写死，换盘就找不到 | 落到 `ComfyUI\models\asr`，且已注册 `asr` 根 |

---

## 2. 模型落位表（关键）

插件的路径解析规则是从源码读出来的，不是猜的：

- `drama3_t8/engine.py:110-123` —— `text_head` / `line_head` / `asr_model` 全部从
  **`model_path.parent`**（主模型所在目录）推导：

  ```python
  self.text_head_path = model_path.parent / "drama3-text-head.safetensors"
  self.line_head_path = model_path.parent / "drama3-line-head.safetensors"
  self.asr_path       = model_path.parent / "qwen3-asr-06b.safetensors"
  ```

- `drama3_t8/nodes.py:98` —— `base = folder_paths.models_dir`，**相对路径只对它解析**，
  完全不查 `extra_model_paths.yaml` 里的共享盘。
- `drama3_t8/nodes.py:414-424` —— 对齐器 `base = Path(folder_paths.models_dir)/"asr"` **硬编码**，
  且执行时校验 `path.parent != base` 就报错，所以必须**直接**放在 `models\asr` 下。
- `drama3_t8/nodes.py:440-442` —— R2T2 的 `model_path` / `projector_path` / `vad_path`
  默认值是 `"asr/..."`，同样按 `models_dir` 解析。

### 最终落位

```
J:\ComfyUI-Shared\models\diffusion_models\
    drama3-t8-fp8.safetensors          38,578,460,824   主模型（必须与下面三个同目录）
    drama3-text-head.safetensors            1,033,371,816
    drama3-line-head.safetensors                 8,480
    qwen3-asr-06b.safetensors             1,564,928,184

J:\ComfyUI-Shared\models\vae\
    drama3-codec.safetensors              1,565,647,484

G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\models\asr\      ← ComfyUI 自己的 models 目录
    qwen3_forced_aligner_0.6b_bf16.safetensors  1,835,545,592
    Confucius4-R2T2-GGUF\Confucius4-R2T2-Q8_0.gguf   1,834,422,208
    Confucius4-R2T2-GGUF\mmproj-Confucius4-R2T2-Q8_0.gguf   348,336,544
    FireRedVAD-ONNX\fireredvad_stream_vad_with_cache.onnx  2,306,042
    FireRedVAD-ONNX\cmvn.ark                                    1,311
    campplus-zh-en.onnx                              28,281,164

G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\user\drama3_t8\native-host\models\
    campplus-zh-en.onnx         ← 创意节点的默认探测路径（creative_studio.py:86-87）
```

> `asr` 目录必须同时具备 `fireredvad_stream_vad_with_cache.onnx` **和** `cmvn.ark`，
> 缺一个 `require_models` 就会拒绝加载。

---

## 3. 一键部署

```powershell
pwsh -File .\deployment\Deploy-Drama3.ps1
```

脚本做六件事，全部幂等：

| 步骤 | 内容 | 幂等性 |
|---|---|---|
| 0 | 检查 ComfyUI 根目录与 venv Python | — |
| 1 | 克隆 / `git pull` 插件 | 已存在则只更新 |
| 2 | 安装 Python 依赖 | `--upgrade-strategy only-if-needed` |
| 3 | 安装 R2T2 原生运行时（走插件自带 `install.py`，逐文件 sha256 校验） | 已装则校验跳过 |
| 4 | 下载模型权重 | 已存在则跳过 |
| 5 | 在 `extra_model_paths.yaml` 注册 `asr` 根（先自动备份） | 已注册则跳过 |
| 6 | 逐文件校验存在性与字节数，输出 `drama3_deploy_verify.json` | 只读 |

常用参数：

```powershell
pwsh -File .\deployment\Deploy-Drama3.ps1 -VerifyOnly    # 只校验，不写任何东西
pwsh -File .\deployment\Deploy-Drama3.ps1 -SkipModels    # 跳过模型下载
pwsh -File .\deployment\Deploy-Drama3.ps1 -ComfyRoot 'D:\ComfyUI' -ModelsRoot 'E:\models'
```

---

## 4. transformers 版本：为什么本机保留 5.5.0

插件 `requirements.txt` 钉的是 `transformers==4.57.1`。**本机没有降级**，原因是降级会直接
弄坏另一个已装节点：

`Higgs_v3-TTS-ComfyUI/native.py:35`

```python
from transformers import (HiggsAudioV2TokenizerConfig, HiggsAudioV2TokenizerModel, ...)
```

| transformers | `transformers/models/higgs*` | `HiggsAudioV2TokenizerConfig` |
|---|---|---|
| 5.5.0 | `higgs_audio_v2/` + `higgs_audio_v2_tokenizer/` 存在 | ✅ 可导入 |
| 4.57.1 | 条目数 = 0 | ❌ ImportError → 整个包 5 个节点注册不了 |

该节点的 `pyproject.toml:26` 写的是 `transformers = ">=5.3.0,<=5.5.0"`。

**替代验证**：插件自带的版本契约测试在 5.5.0 上 7/7 通过（退出码 0）：

```
portable/tests/test_transformers_compat.py
test_real_text_prefill_and_cached_token_match_full_sequence[eager] PASSED
test_real_text_prefill_and_cached_token_match_full_sequence[sdpa]  PASSED
test_real_text_causal_mask_prevents_future_tokens_changing_prefix[eager] PASSED
test_real_text_causal_mask_prevents_future_tokens_changing_prefix[sdpa]  PASSED
test_real_text_padding_mask_preserves_unpadded_outputs[eager] PASSED
test_real_text_padding_mask_preserves_unpadded_outputs[sdpa]  PASSED
test_native_qwen_asr_tokenizer_keeps_audio_protocol_ids_and_multilingual_text PASSED
======= 7 passed, 1 warning in 6.61s =======
```

插件实际用到的 transformers 内部 API 在 5.5.0 上 26/26 全部存在。
（`modeling_flash_attention_utils.FlashAttentionKeys` 与 `modeling_utils.TransformersKwargs`
在 v0.3.2 源码里根本不存在 —— 全插件 grep 34 处命中无这两个名字；插件用的是
`FlashAttentionKwargs` 和 `transformers.utils.generic.TransformersKwargs`，两者都在。）

pip 改动记录：**新增 9 个包，删除 0 个，修改 0 个，207 个未动**
（新增：`cython dynet38 iniconfig kaldi-native-fbank kaldiio nagisa pluggy pytest soynlp`）。
`transformers 5.5.0` / `huggingface_hub 1.33.0` / `tokenizers 0.22.2` /
`torch 2.12.1+cu130` / `torchaudio 2.11.0+cu130` 全部原封未动。

---

## 5. R2T2 原生运行时与 CUDA 版本

上游 `install.py` 首次会报 `Runtime archive integrity check failed`。**这不是文件损坏**：

- 资产 `Drama3-R2T2-native-win64-cu128.zip`，`Content-Length` = 610,460,680，与
  `r2t2-runtime.json` 的 `bytes` 完全一致
- 上游 v0.3.0 的 `SHA256SUMS.txt` 公布值 = `c075593e…3bccd`，与 manifest 一致
- 真正原因：GitHub 的 release-assets CDN 在传输中途截断了流（直连只拿到 14,187,051 字节）

修法（**不改插件任何源文件**）：

```powershell
curl.exe -L --retry 30 --retry-delay 3 --retry-all-errors -C - `
  -o drama3_r2t2_runtime.zip `
  "https://github.com/T8mars/Comfyui-Drama-3/releases/download/v0.3.0/Drama3-R2T2-native-win64-cu128.zip"
# 校验：字节数必须 = 610460680，sha256 必须 = c075593eefe24c96977246e0815c52163d7b9d5df297766df242b5a2bcf3bccd
Expand-Archive .\drama3_r2t2_runtime.zip -DestinationPath <插件目录>\r2t2-runtime -Force
cd <插件目录>; python install.py      # → R2T2 native runtime verified.
```

**CUDA 12.8 运行时与 cu130 torch 不冲突**（实测，不是推断）：`native.py::_load_library()`
在 torch 2.12.1+cu130 已驻留并跑过 CUDA 算子的前提下 `_load_library() OK in 0.06 s`，
`r2t2_api_version() = 1`，`ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24563 MiB) —
Device 0: NVIDIA GeForce RTX 4090, compute capability 8.9`。原因是 soname 不同
（`cublas64_12`/`cudart64_12` vs `cublas64_13`/`cudart64_13`），且 `native.py:70-76`
把 runtime 的 `lib` 与 `backends` 排在 torch `lib` 之前注册 DLL 搜索目录。

---

## 6. 节点注册

30/30 全部注册（`T8/Drama3` + `T8/Drama3/Creative`）。插件是 ComfyUI V3 schema，
没有 `NODE_CLASS_MAPPINGS`，只能走 `get_node_list()`：

```
T8DramaLoader            T8DramaReference      T8DramaSession       T8DramaGenerate
T8DramaScene             T8DramaInfill         T8DramaDecode        T8DramaSaveSession
T8DramaLoadSession       T8DramaBranch         T8DramaTranscribe    T8DramaCodecEncode
T8DramaCodecDecode       T8DramaSRT            T8DramaAlign         T8DramaLive
T8DramaR2T2Transcribe    T8DramaEditor         T8DramaVoiceLibraryList
T8DramaVoiceLibraryLoad  T8DramaVoiceLibrarySave  T8DramaVoiceCastLoad
T8DramaVoiceCastBuild    T8DramaCreativeTextPreview  T8DramaCreativeProjectCreate
T8DramaCreativeProjectLoad  T8DramaCreativeBatch    T8DramaCreativeDelivery
T8DramaCreativeProjectExport  T8DramaCreativeProjectImport
```

---

## 7. 19 个工作流

`deployment/workflows/` 是按本机路径适配过的副本（原插件目录里的 19 个 JSON **一字节未动**）。
共施加 111 处修正，分 5 类：

| 类别 | 处数 | 说明 |
|---|---|---|
| C1 缺 widget 值 | 8 | `T8DramaGenerate` 少 v0.3.2 新增的 `replace_delivery_tags` |
| C2 非法下拉值 | 34 | `Loader.model`/`.codec`、`Transcribe.asr_model`、`Align.aligner` 改成本机规范文件名 |
| C3 相对→绝对路径 | 38 | `model_path` / `codec_path` / 对齐器路径 + R2T2 三个路径 |
| C4 空文件输入 | 6 | `LoadAudio.audio` → `ref_host.wav`（占位，换成你自己的音色） |
| C5 说明注释 | 25 | 每个 Note 追加本机安装说明 |

未改动：所有 seed / 采样参数 / 脚本文本 / 连线 / 位置 / 标题 / 节点 ID。

---

## 8. 冒烟测试

`deployment/drama3_smoke_test_api.json`（API 格式）：

```
T8DramaLoader → T8DramaGenerate(mode=speech) → T8DramaDecode → SaveAudio
```

```powershell
cd <此目录>
python .\deployment\_drama3_enqueue_smoke.py
```

等价裸调用：`POST http://127.0.0.1:8188/prompt`，body `{"prompt": <文件内容>, "client_id":"drama3-smoke"}`，
再轮询 `/history/<prompt_id>`。输出 WAV 落在 `D:\ComfyUI\output\Drama3_T8\`。

---

## 9. 下载通道说明（为什么权重下载这么难）

这台机器到 HF 的 CAS CDN（`cas-bridge.xethub.hf.co`）**每条连接被限速在 ~50 KB/s**：
单连接 Range 请求实测 35.6 KB/s（直连）/ 56.0 KB/s（经代理）。因此：

| 并发 | 聚合速率 | 38.6 GB 预计 |
|---|---|---|
| 1 | 0.05 MB/s | ~9 天 |
| 16 | 0.91 MB/s | ~12 小时 |
| 128 | 4.70 MB/s | ~2.3 小时 |
| 256 | ~9 MB/s | ~68 分钟 |

`deployment/_dl_fast.py` 是为此写的：单次解析 CDN 签名 URL（900 秒刷新），
N 线程各持独立 session 拉固定分块 Range，写入预分配文件，用 `.parts` 位图做断点续传，
单块失败只损失一块。

```powershell
python .\deployment\_dl_fast.py .\deployment\drama3_batch.json --workers 256 --chunk-mb 8 --proxy proxy
```

---

## 10. 最终验收（2026-11-01）

`deployment/_drama3_accept.py` 是无人值守验收脚本：等全部 `.parts` 位图清零 →
逐个 sha256 对照上游 → 提交端到端冒烟测试 → 轮询 `/history` 确认出音频 → 写报告。

**结果：passed**（`drama3_final_acceptance.json` / `.md`）

| 项 | 结果 |
|---|---|
| 权重校验 | 19 项通过 / 0 失败，其中 11 项走了 sha256 |
| 主模型 `drama3-t8-fp8.safetensors` | 38,578,460,824 B，sha256 `013fe091…b276442` ✓ |
| 端到端 TTS | `prompt_id=25213ccf`，**success**，151.66 s 出音频 |
| 产出音频 | `D:\ComfyUI\output\Drama3_T8\smoke_test_00001.flac`，FLAC PCM_16 / 单声道 / 44.1 kHz / **5.20 s**，peak 0.140、rms 0.0197、非静音 |
| 专家缓存 | `4095 experts (12.0 GiB), 80% of 35840 expert reads hit` |

### 三个必须知道的坑

**① 同一文件被两个下载器同时写 = 字节损坏。**
第一个下载器（`drama3_chunked.py`）与 `_dl_fast.py` 并发写同一个输出文件和同一份
`.parts` 位图，两者各自覆写整份位图。主模型因此出现 **70 个坏块**（字节数正确、
sha256 不符）。规律可定位：它的 worker 分片是 `stride = 4599//8 = 574`，
worker w 负责索引 `w, w+574, w+1148…`，所以受污染的正是 `index % 574 < 8` 那 71 块。
`_drama3_repair_main.py` 按这个指纹只重取 71 块做逐字节比对修复，**576 MB / 62 秒**，
主模型随即哈希命中。**结论：任何时刻一个文件只允许一个下载器。**

**② HF tree API 的 `lfs.sha256` 不是文件内容哈希。**
对每一个文件它都与真实内容哈希不符（如 line-head：tree `f6fd7117…` vs 真实
`59ca2d32…`）。**唯一权威基准是 `model-manifest.json` 里的 sha256。**

**③ `campplus-zh-en.onnx` 不在 `model-manifest.json` 里**，没有任何权威哈希；
tree API 给的 `d889dde2…` 同样是错的（真实为 `aa3cfc16…`）。
对它改用**功能验证**：直接调用插件自己的 `SpeakerEmbedder`
（`drama3_t8/creative_transcript.py`），5 项元数据契约全中
（`framework=3d-speaker` / `feature_normalize_type=global-mean` /
`sample_rate=16000` / `normalize_samples=1` / 输入 `shape[-1]==80`），
在冒烟测试产出的真实音频上跑出 **192 维归一化嵌入**，判定 pass。
见 `drama3_campplus_check.json`。

---

## 11. 目录结构

```
deployment/
    Deploy-Drama3.ps1            一键部署
    README.md                    本文件
    drama3_batch.json            11 个权重的下载清单（目标路径 + 精确字节数）
    _dl_fast.py                  高并发分块下载器（256 并发，位图续传）
    drama3_model_manifest.json   模型清单（含 sha256）
    drama3_upstream_model_manifest.json  上游权威清单（校验基准）
    drama3_deps_report.md        依赖 / transformers 决策 / R2T2 运行时完整证据
    drama3_workflow_report.md    19 个工作流的校验与修正日志
    drama3_smoke_test_api.json   端到端冒烟测试（API 格式）
    drama3_final_acceptance.json 验收报告（机器可读）
    drama3_final_acceptance.md   验收报告（人读）
    drama3_campplus_check.json   campplus 功能验证证据
    drama3_smoke_test_output.flac  冒烟测试产出的真实音频
    _drama3_accept.py            无人值守验收脚本
    _drama3_repair_main.py        并发污染分块的定位与修复
    _drama3_campplus_plugin_check.py  用插件自身类做 campplus 功能验证
    drama3_workflows/            适配后的 19 个工作流
```

---

## 12. TTS → ASR 闭环回环（2026-11-01）

最强的端到端证据：插件自己的 TTS 生成音频，插件自己的 ASR 再读回文字。

| 环节 | 证据 |
|---|---|
| 输入文本 | `你好，这是 DRAMA-3 本地语音合成冒烟测试。` |
| TTS 产出 | `smoke_test_00001.flac` → FLAC PCM_16 / 单声道 / 44.1 kHz / 5.20 s / peak 0.140 / rms 0.0197 |
| ASR 回环 | `prompt_id=df048437…`，**success**，2.79 s，`Qwen3ASRModel 1492MB Staged` |
| ASR 读回 | **`您好，这是抓马三本地语音合成冒烟测试。`** |

读回文本与输入**语义完全一致**（`你好`→`您好` 同义，`DRAMA-3`→`抓马三` 为该词的中文音译，
`本地语音合成冒烟测试` 逐字命中）——证明模型发出的确实是可懂的中文语音，不是噪声。

复现：`python .\deployment\_drama3_roundtrip.py`
（工作流 `drama3_roundtrip_api.json`；音频需为 WAV——本机 ComfyUI 的 PyAV 不解码 FLAC，
`LoadAudio` 会报 `No audio frames decoded`，用 `soundfile` 转 PCM_16 WAV 即可。）

---

## 13. 工作流与对齐器模型的两个真问题（2026-11-01 晚）

### 13.1 上游 19 张工作流在 v0.3.2 下本身就校验不过

**根因**：上游 `workflows/` 里的 `widgets_values` 是按**更早的节点控件布局**写的。
v0.3.2 里 `T8DramaGenerate` 少了第 6 个控件、末尾多了 `replace_delivery_tags`，
于是**从第 6 个槽位起每个值都错位一格**。

上游 `workflows/workflow_basic.json` 的原始值：

```
["speech", "你好…", "", 300, 42, "fixed", 0.7, 0.7, 30, 180, "", 0, "custom"]
                    ^^^^^^ 这个控件在 v0.3.2 里已经不存在（当时是 exact-seed 组合框）
```

按 v0.3.2 的 schema 直接读，`temperature` 会拿到字符串 `"fixed"`，
`top_k` 拿到 `0.7`（应为整数），`sampling_preset` 拿到整数 `0`——
ComfyUI 自己会拒绝：

```
invalid_input_type: Failed to convert an input value to a FLOAT value
  temperature, fixed, could not convert string to float: 'fixed'
value_not_in_list: sampling_preset: 0 not in ['custom', 'stable', 'expressive']
```

**上游 19 张工作流全部带这个问题**（同一 commit、同一个失效控件）。

**修法**：不用「均匀位移」——因为是**中间删、末尾加**，位移模型本身就不成立。
`deployment/qa/rebuild_workflows.py` 用**序列比对（DP，允许两侧跳位）**把旧值对齐回新槽位：

- COMBO 槽位只有在值**确实属于它的选项**时才算匹配（权重 4.0）
- 基本类型槽位只在**类型精确匹配**时才算匹配（权重 2.0）
- 跳过的槽位回落到 schema 默认值（永远是合法值）
- 跳过的旧值会被**报告出来**，不会静默丢失

重建结果：`T8DramaGenerate` 13/13 槽位全部命中，唯一被丢弃的就是那个失效的 `"fixed"`；
`temperature` 拿回 `0.7`、`top_k` 拿回 `30`、`max_frames` 拿回 `180`，
正文 `text` 完整保留。19 张工作流共 **504 个控件值全部通过 schema 校验（0 问题）**。

### 13.2 `workflow_asr.json` 的 `asr_model` 指向了对齐器权重

`asr_model` 下拉里存的是 `qwen-aligner\model.safetensors`（**对齐器**权重），
而不是 ASR 模型。它当时能跑，只是因为 `model_path` 非空、优先级更高把它盖住了；
一旦用户清空 `model_path`，转写就会去加载对齐器。已改回 `qwen3-asr-06b.safetensors`。

> `T8DramaTranscribe.execute` 的解析顺序（`drama3_t8/nodes.py:347-370`）：
> `model_path` 非空 → 用它；否则才用 `asr_model` 下拉。两者只生效一个。

### 13.3 `qwen-aligner/model.safetensors` 是 100% 全零的占位文件

`workflow_align` 报 `SafetensorError: invalid JSON in header`。
查证：该文件**大小正确（1,835,544,544 B，与上游清单一致）但每个字节都是 0**——
`hf_hub_download(local_dir=...)` 把字节留在了 `local_dir/.cache/` 里，
清理 `.cache` 时最终文件只剩同尺寸的空壳。

> 上游清单给 `qwen-aligner/model.safetensors` 只有**字节数、没有 sha256**，
> 所以第 10 节的 sha256 校验没有覆盖到它——这是漏检点。
> 权威哈希来自 HF 的 LFS 元数据：`lfs.oid = 47831d0e82f96b20e9034dba01a075ee06436654719f6a68289e49f1b65ce0e7`。
> （注意第 10 节坑 ② 说的是 tree API 的 `lfs.sha256` 字段；这里取的是 `lfs.oid`，
> 对 LFS 文件它**就是**内容哈希——已用实际文件逐字节复核。）

**修法**：用 `deployment/_parallel_download.py` 重新分片拉取（它对「整块全零」的判定是
「未下载」，会重取，不会把零块当已完成），落盘后按上面的 sha256 逐字节校验。
同时补齐清单里列了但从未落盘的两个小文件：
`qwen-aligner/download-revision.json`（源 `Qwen/Qwen3-ForcedAligner-0.6B` rev `c7cbfc20…`）
与 `qwen-aligner/README.md`。

### 13.4 怎么复验

```sh
# 静态：19 张工作流 × 504 个控件，对当前 schema 全量校验
python deployment/qa/check_workflows.py

# 动态：把交付的工作流文件当 API 提示词真跑一遍（UI→API 按 schema 命名映射）
python deployment/qa/run_workflow.py workflow_basic.json
python deployment/qa/run_workflow.py workflow_asr.json overrides.json
```

`run_workflow.py` 用插件自己的 schema 做控件顺序映射，把 UI 工作流转成 API 提示词，
**跑的就是用户加载的那张工作流文件本身**，不是另搭一个相似的提示词。

