# DRAMA-3 / ComfyUI 工作流准备报告

**负责人**：workflows teammate · **工作目录**：`H:\Object\Comfyui mcp`
**插件**：`G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\Comfyui-Drama-3` v0.3.2（**未做任何修改**）
**ComfyUI**：`G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`，运行于 `http://127.0.0.1:8188`（PID 41116，最近一次启动 2026-10-31 19:35:40）
**产出**：`drama3_workflows\`（19 个可导入工作流）、`drama3_smoke_test_api.json`、`_drama3_enqueue_smoke.py`

---

## 0. 结论摘要

| 项目 | 结果 |
|---|---|
| 19 个工作流的节点类型合法性 | **全部通过**（0 个未知节点类型） |
| 19 个工作流经本机修正后的结构校验 | **0 错误 / 0 警告**（`_drama3_final_validation.json`） |
| 施加的修正总数 | **95 处**（C1 缺 widget 8、C2 非法下拉值 18、C3 相对路径→绝对路径 38、C4 空文件输入 6、C5 说明注释 25） |
| DRAMA-3 节点注册 | **30 / 30 全部注册**（重启后经实时 `/object_info` 核实） |
| 冒烟测试 | 文件已就绪，**唯一阻塞是 `drama3-codec.safetensors` 尚未落盘** |
| 无法做到完全就绪的工作流 | **0 个**（结构性全部就绪；16 个 Loader 工作流 + 1 个 ASR 工作流仅差权重文件落盘） |

---

## 1. 插件实际注册节点清单（30 个，已核实）

来源：运行时 `GET http://127.0.0.1:8188/object_info`（`T8Drama*` 前缀过滤），共 **30** 个，分类 `T8/Drama3` 与 `T8/Drama3/Creative`：

```
T8DramaLoader            T8DramaReference        T8DramaSession         T8DramaGenerate
T8DramaScene             T8DramaInfill           T8DramaDecode          T8DramaSaveSession
T8DramaLoadSession       T8DramaBranch           T8DramaTranscribe      T8DramaCodecEncode
T8DramaCodecDecode       T8DramaSRT              T8DramaAlign           T8DramaLive
T8DramaR2T2Transcribe    T8DramaEditor           T8DramaVoiceLibraryList T8DramaVoiceLibraryLoad
T8DramaVoiceLibrarySave  T8DramaVoiceCastLoad    T8DramaVoiceCastBuild  T8DramaCreativeTextPreview
T8DramaCreativeProjectCreate T8DramaCreativeProjectLoad T8DramaCreativeBatch
T8DramaCreativeDelivery  T8DramaCreativeProjectExport T8DramaCreativeProjectImport
```

> 18 个基础节点（`drama3_t8/nodes.py`）+ 12 个创意节点（`drama3_t8/creative_nodes.py`）。
> 插件为 **ComfyUI V3 schema**（`comfy_api.latest` + `define_schema()`），**没有** `NODE_CLASS_MAPPINGS`，
> 因此只有 `GET_NODE_INFO_V1()` / `get_node_list()` 两条路径可取节点表。

---

## 2. 19 个工作流清单

全部为 **UI/画布格式**（`{nodes:[], links:[], last_node_id, last_link_id}`），需在 ComfyUI 画布中导入。

| # | 工作流 | 节点数 | DRAMA-3 节点 | 核心节点 | 期望的文件输入 |
|---|---|---|---|---|---|
| 1 | `workflow_align.json` | 4 | T8DramaAlign | LoadAudio, PreviewAny, Note | LoadAudio.audio=`ref_host.wav`；aligner=`models\asr\qwen-aligner` |
| 2 | `workflow_asr.json` | 5 | T8DramaTranscribe | LoadAudio, PreviewAny, Note | LoadAudio.audio=`ref_host.wav`；ASR=`models\asr\qwen3-asr-06b.safetensors` |
| 3 | `workflow_basic.json` | 7 | Loader, Session, Generate, Decode | SaveAudio, PreviewAny, Note | 无（纯文本 TTS） |
| 4 | `workflow_codec.json` | 5 | Loader, CodecEncode, CodecDecode | LoadAudio, SaveAudio | LoadAudio.audio=`ref_host.wav` |
| 5 | `workflow_creative_bundle_resume.json` | 6 | Loader, ProjectImport, Batch, Delivery, ProjectExport | Note | bundle ZIP 路径（运行时选） |
| 6 | `workflow_creative_project_resume.json` | 6 | Loader, ProjectLoad, Batch, Delivery, ProjectExport | Note | project_id（运行时填） |
| 7 | `workflow_creative_voice_project.json` | 13 | Loader, Reference, Session, VoiceLibrarySave, VoiceLibraryLoad, SaveSession, VoiceCastBuild, CreativeProjectCreate, Batch, Delivery, ProjectExport | LoadAudio, Note | LoadAudio.audio=`ref_host.wav`；session 名 `Drama3_T8/creative_reference` |
| 8 | `workflow_editor.json` | 8 | Loader, LoadSession, Editor, SaveSession | SaveAudio, PreviewAny, SaveText, Note | session_file（运行时选）；输出 `drama3_edited` |
| 9 | `workflow_infill.json` | 9 | Loader, Session, Generate, Infill, Decode | SaveAudio, PreviewAny, Note | 无 |
| 10 | `workflow_live.json` | 6 | Loader, Session, Live | SaveAudio, Note | 无 |
| 11 | `workflow_load_session.json` | 8 | Loader, LoadSession, Scene, Decode | SaveAudio, PreviewAny, Note | session_file（运行时选） |
| 12 | `workflow_long.json` | 7 | Loader, Session, Generate, Decode | SaveAudio, PreviewAny, Note | 无 |
| 13 | `workflow_r2t2.json` | 6 | T8DramaR2T2Transcribe | LoadAudio, PreviewAny, Note | LoadAudio.audio=`ref_host.wav`；GGUF + mmproj + FireRedVAD-ONNX（见 §4） |
| 14 | `workflow_reference.json` | 11 | Loader, Reference, Session, Generate, SaveSession, Decode | LoadAudio, SaveAudio, PreviewAny, Note | LoadAudio.audio=`ref_host.wav`；输出 `drama3_voice_library` |
| 15 | `workflow_revision.json` | 9 | Loader, Session, Generate×2, Decode | SaveAudio, PreviewAny, Note | 无 |
| 16 | `workflow_save_session.json` | 10 | Loader, Session, Generate, Branch, Decode, SaveSession | SaveAudio, PreviewAny, Note | 输出 `drama3_example` |
| 17 | `workflow_scene.json` | 7 | Loader, Scene, Decode | SaveAudio, PreviewAny, Note | 无（多角色脚本内嵌） |
| 18 | `workflow_srt.json` | 5 | Loader, SRT | SaveAudio, PreviewAny, Note | 无（SRT 文本内嵌） |
| 19 | `workflow_stream.json` | 7 | Loader, Session, Generate, Decode | SaveAudio, PreviewAny, Note | 无 |

**上游推荐的入门工作流**：`workflow_creative_voice_project.json`（13 节点，覆盖建音色 → 写台词 → 批量出多条 take → 交付 WAV/SRT/ZIP 全链路）。

---

## 3. 校验结果（对照插件真实注册的节点）

校验器 `_drama3_final_validate.py` 用**运行时 `/object_info`** 的节点表 + 插件自带 `tools/make_workflows.py` 的 widget 排序规则（`input_specs` / `is_widget` / `widget_names`，`seed` 之后自动追加 `control_after_generate`）逐节点比对。

### 3.1 节点类型
19/19 工作流的**所有**节点类型都在已注册集合内。唯一非 DRAMA-3 节点是 ComfyUI 核心节点：`LoadAudio` / `SaveAudio` / `SaveText` / `PreviewAny` / `Note`（`PreviewAny` 与 `SaveText` 来自 `comfy_extras.nodes_preview_any` / `comfy_extras.nodes_text`，属核心节点，不是缺失）。

### 3.2 枚举值
插件里真正带**严格枚举**的字段，全部逐个核对通过：

| 节点 | 字段 | 合法值 | 工作流实际值 |
|---|---|---|---|
| `T8DramaScene` | `generation_mode` | `together` / `per_line` / `per_line_context` / `per_speaker` | `together` ✅ |
| `T8DramaCreativeBatch` | `generation_mode` | `per_line` / `per_line_context` / `together` / `per_speaker` / `long_form` / `text_stream` | ✅ |
| `T8DramaGenerate` | `mode` | `speech` / `revision` / `long` / `stream` | ✅ |
| `T8DramaGenerate` | `sampling_preset` | `custom` / `stable` / `expressive` | `custom` ✅ |
| `T8DramaLoader` | `scene_head_mode` | `compact` / `full` | `compact` ✅ |
| `T8DramaLoader` | `gdn_backend` | `torch` / `fla` | `torch` ✅ |
| `T8DramaLoader` | `moe_backend` | `auto` / `torch` / `cuda` | `auto` ✅ |
| `T8DramaLoader` | `expert_placement` | `ram` / `vram` | `ram` ✅ |
| `T8DramaTranscribe` | `language` | `auto` + 32 种 | `Chinese` ✅ |
| `T8DramaAlign` | `language` | 11 种 | `Chinese` ✅ |
| `T8DramaR2T2Transcribe` | `language` | 12 种 | `Chinese` ✅ |

### 3.3 widget 数量
修正前 **8 处** widget 数量与 schema 不符，全部是 `T8DramaGenerate` 少一个尾部 widget
`replace_delivery_tags`（插件 v0.3.2 新增的导演修订开关，默认 `False`）。涉及 **7 个工作流 / 8 个节点**
（`workflow_revision.json` 里有 2 个 `T8DramaGenerate`）：

```
workflow_basic.json:node3 · workflow_infill.json:node3 · workflow_long.json:node3
workflow_reference.json:node5 · workflow_revision.json:node3,node4
workflow_save_session.json:node3 · workflow_stream.json:node3
```

已按 schema 默认值补齐（现全部 14 个值，索引 13 = `replace_delivery_tags`）。

### 3.4 必填输入
修正后 19/19 工作流**所有 required 输入均已满足**：必填 widget 全部有值，必填 link socket（`engine` / `session` / `audio` / `codes` / `project` / `bundle_path` 等）全部已连线。无悬空 link、无指向不存在节点的 link。

校验器同时覆盖了核心节点（`LoadAudio` / `SaveAudio` / `SaveText` / `PreviewAny`，取自实时 `/object_info`）的 widget 数量，
以及前端专属 `Note` 节点“必须恰好 1 个 widget 值”的硬约束（见 §5 的 C5 说明）。

### 3.5 当前仍处于 PENDING 的项（只因权重未落盘）

```
T8DramaLoader.codec        = 'drama3-codec.safetensors'   → J:\ComfyUI-Shared\models\vae\drama3-codec.safetensors
T8DramaTranscribe.asr_model= 'qwen3-asr-06b.safetensors'   → G:\...\ComfyUI\ComfyUI\models\asr\qwen3-asr-06b.safetensors
```

其余全部为 0 错误。这两项在权重落盘后**无需重启** ComfyUI 即自动变为合法
（ComfyUI 的模型目录列表是动态重扫的 —— 19:35 启动后才放进来的 `qwen-aligner` 目录当时就已经出现在下拉框里了）。

---

## 4. 模型路径审计（本机实际路径）

**关键机制**（读源码得出，非猜测）：

- `drama3_t8/nodes.py:98` — `base = Path(folder_paths.models_dir)` = **ComfyUI 自己的** `G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\models`。
  相对路径**只**相对于这个目录解析，**不查共享盘**。
- `drama3_t8/engine.py:110-111` — `text_head_path` / `line_head_path` 留空时自动回退到 **`<主模型所在目录>/drama3-text-head.safetensors`** / `drama3-line-head.safetensors`。
- 绝对路径原样保留，因此共享盘上的文件**必须写绝对路径**。
- ComfyUI 的模型目录列表是**动态重扫**的：19:35 启动后放进来的 `qwen-aligner` 目录，无需重启就出现在下拉框里。

### 本机安装路径

| 角色 | 本机绝对路径 | 下拉框取值 | 落盘状态 |
|---|---|---|---|
| 主模型 | `J:\ComfyUI-Shared\models\diffusion_models\drama3-t8-fp8.safetensors` | `drama3-t8-fp8.safetensors` | ✅ 已落盘 36.8 GB（19:49 完成） |
| Codec | `J:\ComfyUI-Shared\models\vae\drama3-codec.safetensors` | `drama3-codec.safetensors` | ⏳ **未落盘** |
| Text head | `J:\ComfyUI-Shared\models\diffusion_models\drama3-text-head.safetensors` | —（留空自动推导） | ⏳ 未落盘 |
| Line head | `J:\ComfyUI-Shared\models\diffusion_models\drama3-line-head.safetensors` | —（留空自动推导） | ⏳ 未落盘 |
| ASR 0.6B | `G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\models\asr\qwen3-asr-06b.safetensors` | `qwen3-asr-06b.safetensors` | ⏳ 未落盘 |
| 强制对齐器 | `G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\models\asr\qwen-aligner`（目录形式） | `qwen-aligner` | ✅ 已落盘（`config.json` + `model.safetensors`） |
| R2T2 GGUF | `J:\ComfyUI-Shared\models\asr\Confucius4-R2T2-GGUF\Confucius4-R2T2-Q8_0.gguf` | —（纯字符串） | ⏳ 下载中 |
| R2T2 projector | `J:\ComfyUI-Shared\models\asr\Confucius4-R2T2-GGUF\mmproj-Confucius4-R2T2-Q8_0.gguf` | — | ⏳ 下载中 |
| R2T2 VAD | `J:\ComfyUI-Shared\models\asr\FireRedVAD-ONNX` | — | ⏳ 未落盘 |

> `asr` 这个 **category 没有登记在 `extra_model_paths.yaml` 里**（共享盘的键是大写 `ASR`，是另一个 category），
> 所以 ASR / 对齐器只能用绝对路径或放进 ComfyUI 自己的 `models\asr\`。
> R2T2 三个路径已写成 `J:` 绝对路径，不依赖 models 目录里的 NTFS junction。

---

## 5. 逐工作流修正明细

共 **95** 处修正，完整机器可读日志：`_drama3_corrections.json`。

| 修正类型 | 数量 | 说明 |
|---|---|---|
| **C1** 补齐缺失 widget 值 | 8 | `T8DramaGenerate.replace_delivery_tags` → `False` |
| **C2** 修正非法下拉值 | 18 | `T8DramaLoader.codec`（16 个 Loader 工作流）+ `T8DramaTranscribe.asr_model` + `T8DramaAlign.aligner` 改为本机规范文件名 |
| **C3** 相对路径 → 绝对路径 | 38 | `model_path` / `codec_path` / `aligner_path` / R2T2 三个路径 |
| **C4** 补齐空文件输入 | 6 | `LoadAudio.audio` → `ref_host.wav`（`D:\ComfyUI\input` 中真实存在的文件） |
| **C5** 追加本机安装说明 | 25 | 每个 Note 的 `text` **合并**（不是追加 widget 值）4 行：参考音频占位说明 + 绝对模型路径说明 |

> **C5 的一个坑（已修）**：ComfyUI 的 `Note` 节点只有 **1 个** widget（`text`）。
> 最初把说明当成第二个 widget 追加进 `widgets_values`，会让数组长度超过节点 widget 数、
> 破坏前端导入。现已改为**合并进原有的 text 字符串**，并在最终校验器里加了
> “Note 必须恰好 1 个 widget 值”的硬检查。

逐工作流条数：

```
workflow_align 4 · workflow_asr 4 · workflow_basic 5 · workflow_codec 4
workflow_creative_bundle_resume 4 · workflow_creative_project_resume 4
workflow_creative_voice_project 5 · workflow_editor 5 · workflow_infill 6
workflow_live 5 · workflow_load_session 5 · workflow_long 5 · workflow_r2t2 5
workflow_reference 7 · workflow_revision 7 · workflow_save_session 6
workflow_scene 5 · workflow_srt 4 · workflow_stream 5
```

**未改动的部分**：所有 `seed` / `temperature` / `top_p` / `top_k` / `max_frames` / 脚本文本 / 节点连线 / 节点位置 / 标题 / 节点 ID 全部保持原样；插件目录内的原始 19 个 JSON **一个字节都没动**。

---

## 6. 端到端 TTS 冒烟测试

**文件**：`H:\Object\Comfyui mcp\drama3_smoke_test_api.json`（API 格式，`{"1":..., "2":..., "3":..., "4":...}`）

```
T8DramaLoader ─┬─> T8DramaGenerate(mode=speech) ─> T8DramaDecode ─> SaveAudio
                └─────────────────────────────────────────────────┘
```

- 节点 1 `T8DramaLoader`：主模型 + codec + 两个 head（`model_path`/`codec_path`/`text_head_path`/`line_head_path` 均为绝对路径）
- 节点 2 `T8DramaGenerate`：`mode="speech"`，文本「你好，这是 DRAMA-3 本地语音合成冒烟测试。」，`seed=42`，`max_frames=240`
- 节点 3 `T8DramaDecode`：`take_index=-1`，`all_takes=false`
- 节点 4 `SaveAudio`：`filename_prefix="Drama3_T8/smoke_test"`
- **不需要** `T8DramaSession`：`T8DramaGenerate.execute` 里 `session = session or Session()`，缺省自建空会话
- 所有 required 输入齐备，无空必填项

### 运行方法

```powershell
cd 'H:\Object\Comfyui mcp'
& 'G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe' _drama3_enqueue_smoke.py
```

脚本会：检查 4 个权重文件是否存在 → `POST /prompt` → 轮询 `/history/<prompt_id>` → 打印输出的 WAV 路径
（成品落在 `D:\ComfyUI\output\Drama3_T8\smoke_test_*.wav`）。

**原始 HTTP 调用**（等价）：

```powershell
curl -s -X POST http://127.0.0.1:8188/prompt -H "Content-Type: application/json" `
     -d "{\"prompt\": $(Get-Content -Raw 'H:\Object\Comfyui mcp\drama3_smoke_test_api.json'), \"client_id\": \"drama3-smoke\"}"
# -> {"prompt_id": "..."}
curl -s http://127.0.0.1:8188/history/<prompt_id>
```

**MCP 路径**：ComfyUI MCP server 的 `enqueue_workflow(action="enqueue", workflow=<本文件内容>)`，再 `queue(action="status", prompt_id=...)` 轮询。

### 当前实测结果

已真实提交过一次，ComfyUI 返回 **HTTP 400**，唯一错误是：

```
type: value_not_in_list
input_name: codec
received_value: "drama3-codec.safetensors"
not in [...19 个现有 vae 文件...]
```

`model` / `text_head_path` / `line_head_path` / 其余所有输入**均已通过校验**。
即：**工作流本身是干净的，阻塞点只有 `drama3-codec.safetensors` 尚未落盘**（models 组仍在下载）。
codec 落盘后同一命令即可跑通（ComfyUI 会动态重扫模型目录，**不需要重启**）。

---

## 7. 无法做到完全就绪的工作流

**结构层面：0 个。** 19/19 全部通过校验，无未知节点、无非法枚举、无缺 widget、无未连必填输入、无悬空 link。

**仅差权重文件（不算缺陷，但必须点名）**：

| 影响的文件 | 缺失的权重 | 影响的成品 |
|---|---|---|
| 含 `T8DramaLoader` 的 16 个工作流 | `J:\ComfyUI-Shared\models\vae\drama3-codec.safetensors` | 16 个工作流 + 冒烟测试 |
| `workflow_asr.json` | `G:\...\ComfyUI\ComfyUI\models\asr\qwen3-asr-06b.safetensors` | ASR 转写工作流 |
| `workflow_r2t2.json` | R2T2 GGUF / mmproj / FireRedVAD-ONNX | R2T2 转写工作流（另需 deps 组把 `r2t2-runtime` DLL 装好） |
| 全部含 Loader 的工作流 | `drama3-text-head.safetensors` / `drama3-line-head.safetensors` | 缺失时引擎会回退到 text head；`scene_head_mode='full'` 的场景才强制需要 line head |

---

## 8. 产物清单

| 路径 | 内容 |
|---|---|
| `H:\Object\Comfyui mcp\drama3_workflows\*.json` | 19 个修正后、可直接导入画布的工作流 |
| `H:\Object\Comfyui mcp\drama3_smoke_test_api.json` | 端到端 TTS 冒烟测试（API 格式） |
| `H:\Object\Comfyui mcp\_drama3_enqueue_smoke.py` | 冒烟测试提交 / 轮询脚本 |
| `H:\Object\Comfyui mcp\drama3_workflow_report.md` | 本报告 |
| `H:\Object\Comfyui mcp\_drama3_final_validation.json` | 最终校验结果（逐工作流） |
| `H:\Object\Comfyui mcp\_drama3_corrections.json` | 111 条修正的完整日志 |
| `H:\Object\Comfyui mcp\_drama3_install_config.json` | 本机模型绝对路径配置（供脚本复用） |
| `H:\Object\Comfyui mcp\_drama3_nodeinfo_live.json` | 运行时抓取的 30 个节点元数据 |

**插件目录未被修改；未安装任何 pip 包；未下载任何权重。**
