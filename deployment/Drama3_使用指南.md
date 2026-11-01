# DRAMA-3 使用指南（Windows + RTX 4090 24GB）

> 分支 `deployment/windows-4090` · 提交 `bc611e8` · 插件 v0.3.2（上游 `69104ac`）
> 本机实测：**19 张工作流 18 张通过**，唯一不可用项见第 8 节。

---

## 0. 三步跑起来

```
1) 启动 ComfyUI
   桌面版：直接打开即可
   命令行：cd "G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
           .\.venv\Scripts\python.exe -s main.py --port 8188

2) 载入工作流
   工作流在：custom_nodes\Comfyui-Drama-3\deployment\workflows\
   界面里「工作流 → 打开」选 workflow_basic.json 起步

3) 出货
   音频：D:\ComfyUI\output\Drama3_T8\*.flac
   会话：D:\ComfyUI\output\drama3_t8_sessions\*.safetensors
   工程：D:\ComfyUI\output\drama3_t8_creative\project-<uuid>.zip
```

**输入音频必须是 WAV**：本机 PyAV 不解码 FLAC，`LoadAudio` 遇 FLAC 报
`No audio frames decoded`。用 `soundfile` 转 PCM_16 WAV 再喂。

---

## 1. 模型：全部就位并已逐字节校验

| 用途 | 文件 | 所在目录 | 大小 |
|---|---|---|---|
| 主模型 | `drama3-t8-fp8.safetensors` | `J:\ComfyUI-Shared\models\diffusion_models` | 38.6 GB |
| 文本头 | `drama3-text-head.safetensors` | 同上 | 1.03 GB |
| 线头 | `drama3-line-head.safetensors` | 同上 | 8,480 B |
| Codec | `drama3-codec.safetensors` | `J:\ComfyUI-Shared\models\vae` | 1.57 GB |
| ASR | `qwen3-asr-06b.safetensors` | `J:\ComfyUI-Shared\models\asr` | 1.56 GB |
| 强制对齐器（目录版） | `qwen-aligner\model.safetensors` | `ComfyUI\models\asr` | 1.84 GB |
| 强制对齐器（单文件版） | `qwen3_forced_aligner_0.6b_bf16.safetensors` | 同上 | 1.84 GB |
| R2T2 主模型 | `Confucius4-R2T2-GGUF\Confucius4-R2T2-Q8_0.gguf` | 同上 | 1.83 GB |
| R2T2 投影 | `Confucius4-R2T2-GGUF\mmproj-Confucius4-R2T2-Q8_0.gguf` | 同上 | 348 MB |
| 流式 VAD | `FireRedVAD-ONNX\fireredvad_stream_vad_with_cache.onnx` | 同上 | 2.3 MB |
| 说话人嵌入 | `camplus-zh-en.onnx` | `ComfyUI\user\drama3_t8\native-host\models` | 28.3 MB |

**布局规则**（插件 `drama3_t8/engine.py:110-123`）：`text_head` / `line_head` / `asr`
默认按 **`model_path` 的同级目录**找，所以它们必须和主模型**并排放在 `diffusion_models`**；
`codec` 在 `vae` 目录；ASR 在 `asr` 目录。

---

## 2. 核心链路：五个节点

```
T8DramaLoader  →  T8DramaSession  →  T8DramaGenerate  →  T8DramaDecode  →  SaveAudio
   装模型          建会话/带上下文      生成语音            解码成 WAV        落盘
```

| 节点 | 作用 | 关键参数 |
|---|---|---|
| `T8DramaLoader` | 载入主模型 + codec，分配显存 | `model` / `codec` / `expert_cache_gb` / `gdn_backend` / `model_path` / `codec_path` / `text_head_path` / `line_head_path` / `scene_head_mode` / `moe_backend` / `cuda_graph` / `expert_placement` |
| `T8DramaSession` | 新会话容器，串起参考音、场景、台词 | （无控件） |
| `T8DramaGenerate` | 生成 / 导演修改 / 流式 | 13 个槽位，见第 4 节 |
| `T8DramaDecode` | 潜变量 → 音频 | `take_index` / `max_pause_seconds` 等 |
| `SaveAudio` | 核心节点，落盘 | `filename_prefix`（**必填**） |

---

## 3. 30 个节点速查（6 组）

**① 引擎与生成（7）**
`T8DramaLoader` 原生模型 · `T8DramaSession` 新会话 · `T8DramaGenerate` 生成/导演修改/流式 ·
`T8DramaScene` 多角色场景 · `T8DramaBranch` 会话分支 · `T8DramaLive` 实时语音输出 ·
`T8DramaInfill` 局部音频编辑

**② 音频编解码与后期（4）**
`T8DramaDecode` 输出音频 · `T8DramaCodecEncode` Codec 编码 · `T8DramaCodecDecode` Codec 解码 ·
`T8DramaEditor` 多轨后期剪辑（剪裁/淡入淡出/字幕）

**③ 会话与音色（5）**
`T8DramaReference` 编码参考音 · `T8DramaSaveSession` 保存会话/音色 ·
`T8DramaLoadSession` 加载会话/音色 · `T8DramaVoiceLibrarySave` 保存音色版本 ·
`T8DramaVoiceLibraryLoad` 载入音色版本 · `T8DramaVoiceLibraryList` 音色资料库

**④ 选角（2）**
`T8DramaVoiceCastBuild` 角色选角快照 · `T8DramaVoiceCastLoad` 载入选角预设

**⑤ 转写/对齐/字幕（4）**
`T8DramaTranscribe` Qwen3-ASR 转录 · `T8DramaAlign` 词级时间对齐 · `T8DramaSRT` SRT 批量台词 ·
`T8DramaR2T2Transcribe` Confucius R2T2 Q8 转写（本机不可用，见第 8 节）

**⑥ 创作工程（8）**
`T8DramaCreativeProjectCreate` 新建创作工程 · `T8DramaCreativeProjectLoad` 打开创作工程 ·
`T8DramaCreativeBatch` 原生工程批量配音 · `T8DramaCreativeDelivery` 工程交付包 ·
`T8DramaCreativeProjectExport` 导出完整工程 · `T8DramaCreativeProjectImport` 导入完整工程 ·
`T8DramaCreativeTextPreview` 朗读稿预览

---

## 4. `T8DramaGenerate` 的 13 个槽位

| # | 参数 | 默认 | 含义 |
|---|---|---|---|
| 1 | `mode` | `speech` | `speech` 朗读 · `revision` 导演修改 · `long` 长文本 · `stream` 流式 |
| 2 | `text` | — | 要念的文本（多行） |
| 3 | `lookahead` | `""` | 预读上下文（流式时给下一句，提升连贯） |
| 4 | `chunk_bytes` | `300` | 流式分块字节数（32–3000） |
| 5 | `seed` | `42` | 随机种子 |
| 6 | `temperature` | `0.7` | 0.01–2.0，越大越发散 |
| 7 | `top_p` | `0.7` | 0.01–1.0 |
| 8 | `top_k` | `30` | 0 = 保留全部候选 |
| 9 | `max_frames` | `600` | 最长生成帧数（1–8192） |
| 10 | `seed_text` | `""` | 精确 64 位十进制种子，**填了就覆盖 `seed`** |
| 11 | `opening_retries` | `0` | 开头重试次数（0–1） |
| 12 | `sampling_preset` | `custom` | `custom` / `stable` / `expressive` |
| 13 | `replace_delivery_tags` | `false` | 是否替换交付标签 |

### 四种 mode 怎么选

| mode | 场景 | 注意 |
|---|---|---|
| `speech` | 单句/短段朗读 | 最常用，`max_frames` 180 足够 |
| `long` | 长文（几百字以上） | `max_frames` 提到 600+，耗时线性增长 |
| `stream` | 边输入边出 | 配 `chunk_bytes` + `lookahead`；实测最慢（`workflow_stream` 328 s） |
| `revision` | 在已有语音上改 | 需先接 `session`（来自 `T8DramaSession`/`LoadSession`） |

### 采样手感

- **稳定**（播报、旁白）：`sampling_preset=stable` 或 `temperature=0.5, top_p=0.6, top_k=20`
- **自然**（对话、默认）：`temperature=0.7, top_p=0.7, top_k=30`
- **表现力强**（角色、情绪）：`sampling_preset=expressive` 或 `temperature=0.9, top_p=0.9, top_k=50`
- **逐字复现**：填 `seed_text`（精确种子），比只固定 `seed` 更可靠

### `T8DramaLoader` 的显存旋钮（24 GB 卡）

| 参数 | 建议 | 说明 |
|---|---|---|
| `expert_cache_gb` | `12` | 专家缓存占显存，本机实测稳定 |
| `expert_placement` | `ram` | 专家权重放内存，显存留给激活（实测稳） |
| `gdn_backend` | `torch` | 本机无 flash-linear-attention，只能走 torch |
| `moe_backend` | `auto` | 本机**自动回落到 torch**（日志：`NVRTC expert kernels are unavailable on this host`） |
| `cuda_graph` | `True` | 本机自动回落 `false`（日志：`Expert backend is not synchronization-free`） |
| `scene_head_mode` | `compact` | 多角色场景才需要 `full` |

---

## 5. 19 张工作流（全部实测过）

| 工作流 | 场景 | 节点链 | 实测 |
|---|---|---|---|
| `workflow_basic` | 最简朗读 | Loader→Session→Generate→Decode→SaveAudio | ✅ 64 s |
| `workflow_long` | 长文本 | Loader→Session→Generate→Decode→SaveAudio | ✅ 81 s |
| `workflow_stream` | 流式 | Loader→Session→Generate→Decode→SaveAudio | ✅ 329 s |
| `workflow_scene` | 多角色剧情 | Loader→Scene→Decode→SaveAudio | ✅ 36 s |
| `workflow_revision` | 导演修改 | Loader→Session→Generate→Generate→Decode→SaveAudio | ✅ 1050 s |
| `workflow_save_session` | 存会话 | Loader→Session→Generate→Branch→Decode→SaveAudio→SaveSession | ✅ 4 s |
| `workflow_load_session` | 读会话 | Loader→LoadSession→Scene→Decode→SaveAudio | ✅ 65 s |
| `workflow_live` | 实时 | Loader→Session→Live→SaveAudio | ✅ 48 s |
| `workflow_infill` | 局部编辑 | Loader→Session→Generate→Infill→Decode→SaveAudio | ✅ 44 s |
| `workflow_reference` | 声音克隆 | Loader→LoadAudio→Reference→Session→Generate→SaveSession→Decode→SaveAudio | ✅ 36 s |
| `workflow_codec` | 编解码 | Loader→LoadAudio→CodecEncode→CodecDecode→SaveAudio | ✅ 4 s |
| `workflow_asr` | 语音转文字 | LoadAudio→Transcribe→PreviewAny×2 | ✅ 12 s |
| `workflow_align` | 词级时间戳 | LoadAudio→Align→PreviewAny | ✅ 12 s |
| `workflow_srt` | 字幕 | Loader→SRT→SaveAudio→PreviewAny | ✅ 52 s |
| `workflow_editor` | 多轨剪辑 | Loader→LoadSession→Editor→SaveAudio→SaveSession→SaveText | ✅ 20 s |
| `workflow_creative_voice_project` | 创作工程（建角色+配音） | Loader→LoadAudio→Reference→Session→VoiceLibrarySave→VoiceLibraryLoad→SaveSession→VoiceCastBuild→ProjectCreate→Batch→Delivery→Export | ✅ 539 s |
| `workflow_creative_project_resume` | 打开工程续配 | Loader→ProjectLoad→Batch→Delivery→Export | ✅ 4 s |
| `workflow_creative_bundle_resume` | 导入工程包续配 | Loader→ProjectImport→Batch→Delivery→Export | ✅ 43 s |
| `workflow_r2t2` | R2T2 转写 | LoadAudio→R2T2Transcribe→PreviewAny×3 | ⚠️ 干净拒绝（第 8 节） |

**上手建议**：先跑 `workflow_basic`（64 s 出货），确认链路通 → 再挑场景。

---

## 6. 四个实战流程

### A. 文本 → 语音（最简）

1. 载入 `workflow_basic.json`
2. `T8DramaLoader`：`model` 选 `drama3-t8-fp8.safetensors`，`codec` 选 `drama3-codec.safetensors`
3. `T8DramaGenerate`：`mode=speech`，`text` 填中文，`seed=42`
4. `SaveAudio` 的 `filename_prefix` 改成你要的目录名（如 `Drama3_T8/my_line`）
5. 排队 → 音频出现在 `D:\ComfyUI\output\Drama3_T8\`

> `SaveAudio.filename_prefix` 是**必填**的，漏填 ComfyUI 会**跳过这个节点**但提示词照样报 success。

### B. 声音克隆（用自己的音色）

1. 准备一段 **5–15 秒**干净人声 WAV（单人、无背景音）
2. `LoadAudio` 载入它 → `T8DramaReference` 编码参考 → `T8DramaSaveSession`（或 `VoiceLibrarySave`）存成音色
3. `T8DramaSession` 接上这个会话（或用 `T8DramaVoiceLibraryLoad` 从音色库取）
4. `T8DramaGenerate` 念新文本 → 出来的就是克隆音色

完整链路见 `workflow_reference.json`。

### C. 转写 / 词级对齐 / 字幕

- **转文字**：`LoadAudio` → `T8DramaTranscribe`（`asr_model` 选 `qwen3-asr-06b.safetensors`）
  ⚠️ 若 `model_path` 非空，**它优先**、`asr_model` 被忽略；清空 `model_path` 才用下拉
- **词级时间戳**：`LoadAudio` → `T8DramaAlign`
  实测输出：`你@0.00-0.16 | 好@0.16-0.56 | 这@1.28-1.44 | …`
- **整段字幕**：`T8DramaSRT`

### D. 创作工程批量配音（多角色、一次出全片）

```
LoadAudio ─→ Reference ─→ VoiceLibrarySave ─→ VoiceLibraryLoad ─→ SaveSession
                                                                 ↓
                        VoiceCastBuild ─→ CreativeProjectCreate ─→ CreativeBatch
                                                                 ↓
                                              CreativeDelivery ─→ CreativeProjectExport
```

- `T8DramaCreativeBatch`：`takes_per_line=3`（每句出 3 条备选），
  `generation_mode=per_line_context`（每句带上下文，最自然），
  `sampling_json` 写采样覆盖（`{"temperature":0.7,"top_p":0.7,"top_k":30,"max_frames":600}`）
- `T8DramaCreativeDelivery`：`sample_rate=48000`、`loudness_mode=rms`、`target_db=-20`、`gap_seconds=0.15`
  → 产出 `master.wav` + 角色/单句分轨 + `subtitles.srt` + `takes.csv`
- `T8DramaCreativeProjectExport` → `<输出目录>/drama3_t8_creative/project-<uuid>.zip`

---

## 7. 坑（都是实测踩出来的）

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `No audio frames decoded` | 本机 PyAV 不解 FLAC | 转 PCM_16 WAV |
| `Required input is missing: format` | 核心节点 `SaveText` 的 `format` 没送到 | 用交付目录里的工作流（已修），别用上游那份 |
| `value_not_in_list` / `invalid_input_type` | 上游 19 张工作流控件错位 | 同上，用 `deployment/workflows/` |
| `SafetensorError: invalid JSON in header` | 对齐器权重曾是全零文件 | 已重下并按 sha256 校验通过 |
| `工程包成员数量超限` | `bundle_path` 喂了内层 `project.zip` | 要喂**导出节点产出的完整包**（3 成员：manifest.json + project.zip + voices.zip） |
| `Port 8188 is already in use` | 桌面版占着 8188 且会自启 | QA 实例换 `--port 8200` |
| 界面卡死几分钟 | `--enable-assets` 扫 44k 路径，实测完整扫描 **891 秒** | 调试时去掉该参数 |
| 启动卡在 pip | `comfy-mtb`/`GJJ`/`controlnet_aux` 要 `onnxruntime-gpu`（168 MB） | 已装好，之后启动 10 秒 |
| `session_file` 下拉是空的 | 会话文件要**先存**才有 | 先跑 `workflow_save_session`，刷新后再选 |
| Git push 失败 | 代理端口从 10808 变成 **10809** | `git config http.proxy http://127.0.0.1:10809` |

---

## 8. 唯一不可用项：R2T2（原因 + 替代）

**现象**：跑 `workflow_r2t2` 原本会让 **ComfyUI 整个进程消失**。

**根因**：随附的 `r2t2-runtime/backends/ggml-cuda.dll` 是 **CUDA 12.8 只为 Blackwell 编译**的
——二进制里只有 `sm_120a`，**没有 sm_89 的 cubin、也没有 PTX**。RTX 4090 是 sm_89，
第一个 kernel 启动就报 `no kernel image is available for execution on the device`，
然后是 C 层 `abort()`——**Python 拦不住**。

**已修复**：新增 `drama3_t8/r2t2/arch_guard.py`，在第一次调原生函数**之前**比对
「设备算力」与「二进制支持的架构」，不匹配就抛普通 Python 异常。

| 场景 | 结果 |
|---|---|
| 无闸门（旧行为） | `Fatal Python error: Aborted` → **进程消失** |
| 有闸门（当前） | 干净的 `RuntimeError` → **ComfyUI 存活**，提示改用 Transcribe/Align |

**要真正启用 R2T2**（本机不具备条件）：重编 `ggml-cuda.dll`——需要 CUDA Toolkit 的
`nvcc` + 对应版本 llama.cpp 源码（本机两者都没有；`E:\Confucius4-R2T2\.reference\llama.cpp`
只是编译期嵌入的路径字符串，不是源码）。本机无 CPU 回退路径。

**替代方案（已验证可用）**：
- 转写 → `T8DramaTranscribe`（Qwen3-ASR 0.6B）
- 词级时间戳 → `T8DramaAlign`
- 字幕 → `T8DramaSRT`

`workflow_r2t2.json` 保留在交付目录里，**换到 sm_120 的机器上可直接用**。

---

## 9. 交付物清单

```
deployment/
  workflows/                 19 张适配后的工作流（504 控件全部通过 schema 校验）
  qa/check_workflows.py      静态校验器 → PROBLEMS: 0
  qa/run_workflow.py         UI→API 转换 + 真跑（槽位从 live /object_info 泛化推导）
  qa/rebuild_workflows.py    DP 序列比对重建器
  Drama3_使用指南.md          本文件
  README.md                  部署/验收全记录（第 13–16 节：工作流错位、对齐器全零、R2T2 闸门、运行注意）
```
