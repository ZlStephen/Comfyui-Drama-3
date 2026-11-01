# Comfyui-Drama-3 (v0.3.2) — Dependency & Compatibility Report

**Job:** `deps` teammate — ComfyUI shared-venv dependency deployment for `Comfyui-Drama-3`
**Date:** 2026-10-31 (Asia/Shanghai)
**ComfyUI root:** `G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`
**Venv python (authoritative):** `G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe` — Python 3.13.12
**Plugin root:** `G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\Comfyui-Drama-3`

---

## 0. TL;DR

| Item | Result |
|---|---|
| **transformers decision** | **(A) KEEP 5.5.0** — documented deviation from the plugin's `==4.57.1` pin |
| Reason | Plugin's own compat test passes **7/7 on 5.5.0**; downgrading **hard-breaks `Higgs_v3-TTS-ComfyUI`** (imports `HiggsAudioV2TokenizerConfig/Model`, which exist only in transformers 5.x) |
| huggingface-hub | **kept 1.33.0** (coupled to transformers 5.5.0; nothing in the other 54 nodes requires hub >= 1.x) |
| pip changes | **9 packages ADDED, 0 removed, 0 changed** (207 packages untouched) |
| Plugin requirements | **all installed except the two deliberate pins** (`transformers`, `huggingface-hub`) |
| R2T2 native runtime | **installed + authoritatively verified** (`install.py` → *"R2T2 native runtime verified."*), loads on the RTX 4090 |
| Drama-3 node registration | **30 node classes register, no exception** |
| Other-node import checks | FeiHou-H3 16 ✅, Qwen-TTS 9 ✅, Higgs_v3-TTS 5 ✅, WanVideoWrapper 147 ✅, ComfyUI_GJJ_Nodes 365 ✅ |
| ComfyUI restarted? | **NO** (as instructed — port 8188 untouched) |

Artifacts:
- `H:\Object\Comfyui mcp\drama3_pip_freeze_before.txt` (208 lines)
- `H:\Object\Comfyui mcp\drama3_pip_freeze_after.txt` (217 lines)
- `H:\Object\Comfyui mcp\drama3_compat_test_final.log`
- `H:\Object\Comfyui mcp\drama3_install_py.log`
- `H:\Object\Comfyui mcp\drama3_r2t2_runtime.zip` (verified installer archive, 610,460,680 B)

---

## 1. Step 1 — Plugin artifacts located and read

### 1.1 The transformers compatibility test

Path (**not** at repo root, as expected — it lives under `portable/`):

```
G:\...\custom_nodes\Comfyui-Drama-3\portable\tests\test_transformers_compat.py
```

Docstring (line 1): *"Real CPU Qwen forwards and tokenizer contracts across supported Transformers versions."*
It is explicitly a **multi-version contract test**, not a single-version pin test. 4 test functions,
one of them parameterised `('eager', 'sdpa')` → **7 test cases**:

| Test | What it proves |
|---|---|
| `test_real_text_prefill_and_cached_token_match_full_sequence[eager/sdpa]` | Real CPU forward, KV-cache prefill == full-sequence forward |
| `test_real_text_causal_mask_prevents_future_tokens_changing_prefix[eager/sdpa]` | Causal masking correct |
| `test_real_text_padding_mask_preserves_unpadded_outputs[eager/sdpa]` | Padding mask correct |
| `test_native_qwen_asr_tokenizer_keeps_audio_protocol_ids_and_multilingual_text` | Qwen2 tokenizer protocol ids + CJK/EN round-trip |

It imports the plugin's **vendored** Qwen3-ASR implementation:
```python
from drama3_t8.vendor_qwen.core.transformers_backend.configuration_qwen3_asr import Qwen3ASRTextConfig
from drama3_t8.vendor_qwen.core.transformers_backend.modeling_qwen3_asr import Qwen3ASRThinkerTextModel
```

### 1.2 Node registration entry point

Plugin root `__init__.py` (9 lines) → `comfy_entrypoint()` → `drama3_t8/nodes.py:561 comfy_entrypoint()`
→ `register_routes()` + returns `Drama3Extension(ComfyExtension)`.
`drama3_t8/nodes.py:548` defines `NODES = [ ... 18 base classes ... ]` plus
`NODES += get_creative_nodes(...)` from `creative_nodes.py` → **30 node classes total**.
This is the new ComfyUI **v3 extension API** (`comfy_api.latest`, `ComfyExtension`, `io`/`ui`).

### 1.3 What the vendored Qwen3-ASR actually imports from transformers

`drama3_t8/vendor_qwen/core/transformers_backend/modeling_qwen3_asr.py`:
```python
from transformers.activations import ACT2FN
from transformers.cache_utils import Cache, DynamicCache
from transformers.generation import GenerationMixin
from transformers.integrations import use_kernel_forward_from_hub
from transformers.masking_utils import create_causal_mask
from transformers.modeling_flash_attention_utils import FlashAttentionKwargs
from transformers.modeling_layers import GradientCheckpointingLayer
from transformers.modeling_outputs import (...)
from transformers.modeling_rope_utils import ROPE_INIT_FUNCTIONS, dynamic_rope_update
from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS, PreTrainedModel
from transformers.processing_utils import Unpack
from transformers.utils import auto_docstring, can_return_tuple
from transformers.utils.deprecation import deprecate_kwarg
from transformers.utils.generic import TransformersKwargs, check_model_inputs
```
Plus `configuration_qwen3_asr.py` → `transformers.configuration_utils.PretrainedConfig`;
`processing_qwen3_asr.py` → `transformers.audio_utils.AudioInput`, `feature_extraction_utils.BatchFeature`,
`processing_utils.ProcessingKwargs/ProcessorMixin`, `tokenization_utils_base.TextInput`.

**The plugin additionally ships its own version-tolerance shim** — `modeling_qwen3_asr.py:51-67`:
```python
_CAUSAL_MASK_PARAMETERS = signature(create_causal_mask).parameters
def _create_causal_mask_compat(*, config, inputs_embeds, attention_mask, ...):
    ...
    return create_causal_mask(**kwargs)
```
i.e. it introspects `create_causal_mask`'s signature and adapts. This is a deliberate
multi-transformers-version design, not a pin-and-hope design.

> **Correction to the task brief:** the brief stated the plugin imports
> `transformers.modeling_flash_attention_utils.FlashAttentionKeys` and
> `transformers.modeling_utils.TransformersKwargs`. **Neither appears anywhere in the v0.3.2 source**
> (grep over the whole plugin, `*.py`, 34 matches — none of those two names). The plugin uses
> `FlashAttentionKwargs` and `transformers.utils.generic.TransformersKwargs`, both of which exist in 5.5.0.

---

## 2. Step 2 — Compat test run against the CURRENT transformers 5.5.0 (BEFORE any change)

### 2.1 API availability probe (all 28 candidates probed individually under 5.5.0)

```
transformers 5.5.0
OK 26/28
FAIL transformers.modeling_flash_attention_utils.FlashAttentionKeys -> AttributeError: module 'transformers.modeling_flash_attention_utils' has no attribute 'FlashAttentionKeys'
FAIL transformers.modeling_utils.TransformersKwargs            -> AttributeError: module 'transformers.modeling_utils' has no attribute 'TransformersKwargs'
```

**Both failures are for symbols the plugin does not use** (see §1.3). Every symbol the plugin
*actually* imports is present in 5.5.0.

### 2.2 The plugin's own test — first attempt (before installing plugin deps)

```
collected 0 items / 1 error
ImportError while importing test module .../portable/tests/test_transformers_compat.py
  from drama3_t8.vendor_qwen.core.transformers_backend.configuration_qwen3_asr import Qwen3ASRTextConfig
  drama3_t8\vendor_qwen\__init__.py:1: in <module>
      from .inference.qwen3_forced_aligner import Qwen3ForcedAligner
  drama3_t8\vendor_qwen\inference\qwen3_forced_aligner.py:21: in <module>
      import nagisa
E   ModuleNotFoundError: No module named 'nagisa'
```
→ The venv was missing the plugin's own dependencies. Fixed in §4 (installed *without* touching
transformers/hub, so the test still ran under 5.5.0).

### 2.3 The plugin's own test — FINAL RUN under transformers 5.5.0

Run twice: against `portable/drama3_t8` and against the **root** `drama3_t8` (the copy ComfyUI
actually loads; the three vendored `transformers_backend/*.py` files are byte-identical between the
two trees — SHA-256 `F78FE217CCD0…`, `102B3BDC6ABC…`, `D77764BB0BDE…`).

```
portable\tests\test_transformers_compat.py::test_real_text_prefill_and_cached_token_match_full_sequence[eager] PASSED
portable\tests\test_transformers_compat.py::test_real_text_prefill_and_cached_token_match_full_sequence[sdpa]  PASSED
portable\tests\test_transformers_compat.py::test_real_text_causal_mask_prevents_future_tokens_changing_prefix[eager] PASSED
portable\tests\test_transformers_compat.py::test_real_text_causal_mask_prevents_future_tokens_changing_prefix[sdpa]  PASSED
portable\tests\test_transformers_compat.py::test_real_text_padding_mask_preserves_unpadded_outputs[eager] PASSED
portable\tests\test_transformers_compat.py::test_real_text_padding_mask_preserves_unpadded_outputs[sdpa]  PASSED
portable\tests\test_transformers_compat.py::test_native_qwen_asr_tokenizer_keeps_audio_protocol_ids_and_multilingual_text PASSED

======================== 7 passed, 1 warning in 6.61s =========================
pytest exit code = 0
```

**Result: 7 / 7 PASSED under transformers 5.5.0. Zero failures.**

Non-fatal noise observed (does not fail the run):
- `[ERROR] \`cache_position\` is part of Qwen3ASRThinkerTextModel.forward's signature, but not documented.`
  — emitted by transformers 5.x's `auto_docstring` checker; the run still reports 7 passed / exit 0.
- `The \`check_model_inputs\` decorator is deprecated in favor of \`merge_with_config_defaults\`.` — deprecation warning.
- `Unrecognized keys in \`rope_parameters\` for 'rope_type'='default': {'mrope_section'}` × 6 — informational.
- `BPE.__init__ will not create from files anymore` — tokenizers deprecation warning.

Full log: `H:\Object\Comfyui mcp\drama3_compat_test_final.log`

---

## 3. Step 3 — The transformers decision

### 3.1 Candidate (B) downgrade to 4.57.1 — what it would change

`pip install --dry-run -r requirements.txt` (respecting installed packages) reports **exactly**:

```
Would install huggingface_hub-0.36.2 transformers-4.57.1
```

i.e. the *only* remaining delta of the plugin's pinned requirement set is those two packages.
`transformers 4.57.1` declares `huggingface-hub>=0.34.0,<1.0`, so **the hub downgrade is coupled and
unavoidable** with the transformers downgrade. `transformers 5.5.0` declares `huggingface-hub>=1.5.0,<2.0`.

### 3.2 Full dependency scan of the other 54 custom_nodes (all requirement files, including nested)

104 requirement/pyproject files were enumerated and scanned (nested `requirements-*.txt`,
`requirements/*.txt`, `vendor/*/requirements.txt`, `upstream/requirements.txt`, all `pyproject.toml`).

| Node | Declared transformers / hub constraint | Source |
|---|---|---|
| **ComfyUI core** | `transformers>=4.50.3`, `tokenizers>=0.13.3` — **no hub pin at all** | `ComfyUI/requirements.txt:9-10` |
| **Higgs_v3-TTS-ComfyUI** | `transformers = ">=5.3.0,<=5.5.0"`, `recommended-transformers = "5.5.0"` | `Higgs_v3-TTS-ComfyUI/pyproject.toml:26-27` |
| **Higgs_v3-TTS-ComfyUI** | *"This nodepack intentionally does not pin or upgrade torch/transformers because the native path is built for **Transformers 5.3.0 through 5.5.0**, with 5.5.0 recommended."* | `Higgs_v3-TTS-ComfyUI/requirements.txt:1-4` |
| ComfyUI-FeiHou-Easy-H3 | `transformers>=4.51.0` (both `requirements.txt` and `requirements-local-llm.txt`) | ✅ satisfied by 4.57.1 *and* by 5.5.0 |
| ComfyUI-Qwen-TTS | `transformers>=4.57.0` (`requirements.txt`) / `transformers>=4.57.0,<5.0.0` (`pyproject.toml`) | ✅ satisfied by 4.57.1; `<5.0.0` cap **already violated today** (5.5.0 installed, and `requirements.txt` is what Manager installs) |
| Higgs / InfiniSplat / controlnet_aux / Qwen-TTS / GJJ_Nodes | bare `huggingface_hub` — **unpinned**, no `>=1.x` anywhere | ✅ no node requires hub ≥ 1.x |
| ComfyUI_GJJ_Nodes | `x-transformers` (an unrelated package, not `transformers`) | n/a |

**Nothing in the other 54 nodes requires huggingface-hub ≥ 1.x.** The hub downgrade alone would be
technically feasible. The transformers downgrade is not.

### 3.3 🔴 The decisive conflict: `Higgs_v3-TTS-ComfyUI` breaks on transformers 4.57.1

`Higgs_v3-TTS-ComfyUI/native.py:35-41`:
```python
from transformers import (
    HiggsAudioV2TokenizerConfig,
    HiggsAudioV2TokenizerModel,
    PreTrainedTokenizerFast,
    Qwen3Config,
    Qwen3ForCausalLM,
)
```

Verified against the two library versions:

```
transformers 5.5.0   ->  HiggsAudioV2TokenizerConfig / HiggsAudioV2TokenizerModel  PRESENT
                          transformers/models/higgs_audio_v2/  +  transformers/models/higgs_audio_v2_tokenizer/

transformers 4.57.1 ->  __init__.py HiggsAudioV2 export lines: 0
                          transformers/models/higgs* entries:    []
```
(The 4.57.1 wheel was downloaded with `pip download --no-deps` to a temp dir and inspected **without
installing it** — the shared venv was never touched by this probe. The only `higgs`-named files in
4.57.1 are `transformers/integrations/higgs.py` and `transformers/quantizers/quantizer_higgs.py`,
which are unrelated to the model classes.)

⇒ On transformers 4.57.1, `from transformers import HiggsAudioV2TokenizerConfig` raises
**ImportError**, `Higgs_v3-TTS-ComfyUI/native.py` fails to import, and the whole nodepack
(5 nodes: Higgs v3 TTS, clone, multi-speaker, longform, AIMDO DynamicVRAM) fails to register.
**This node is currently installed and working on 5.5.0.**

### 3.4 DECISION: **(A) keep transformers 5.5.0 — documented deviation**

Rationale, in order of weight:

1. **A downgrade would break another node.** `Higgs_v3-TTS-ComfyUI` hard-requires transformers
   `>=5.3.0,<=5.5.0` and imports `HiggsAudioV2TokenizerConfig/Model`, which **do not exist in
   4.57.1** (proved in §3.3). Per the hard rules, a downgrade that breaks another node must not be
   forced — this is exactly that case.
2. **The plugin's own contract test passes 7/7 on 5.5.0** (§2.3) — and that test is *by name* the
   multi-version contract test ("across supported Transformers versions"), run against the exact
   code tree ComfyUI loads. The pin `==4.57.1` is a known-good pin, not a hard requirement.
3. **Every transformers internal the plugin uses exists in 5.5.0** (26/26) and the plugin ships a
   `create_causal_mask` signature shim proving multi-version intent.
4. **No other constraint is violated by 5.5.0**: ComfyUI core (`>=4.50.3`) ✅, FeiHou-H3 (`>=4.51.0`) ✅,
   Qwen-TTS `requirements.txt` (`>=4.57.0`) ✅, Higgs (`>=5.3.0,<=5.5.0`) ✅.
5. The blast radius of a downgrade in a **shared** venv serving 55 custom_nodes + a live ComfyUI
   session is far larger than the blast radius of keeping a version that is *proven* to work for
   the new plugin.

**Documented deviation:** `custom_nodes/Comfyui-Drama-3/requirements.txt:5-6` pin
`transformers==4.57.1` / `huggingface-hub==0.36.2`; the live venv runs
`transformers 5.5.0` / `huggingface_hub 1.33.0`. **Deviation accepted and verified** by the
plugin's own compat test.

*Counterfactual, for the record (what (B) would have cost):* `transformers 5.5.0 → 4.57.1`,
`huggingface_hub 1.33.0 → 0.36.2`, and `Higgs_v3-TTS-ComfyUI` becomes unloadable
(ImportError on `HiggsAudioV2TokenizerConfig`). No *other* node is affected by that pair.

**Isolated-venv alternative** (if the pin must be honoured later): run Drama-3 in its own venv
(`portable/requirements.txt` already pins `torch==2.8.0` + `torchaudio==2.8.0` + `transformers==4.57.1`
+ `huggingface-hub==0.36.2` for the portable build) and expose it to ComfyUI as an out-of-process
worker, instead of sharing the main venv. Not required for the current deployment.

### 3.5 Rollback path (if a future change must revert to 4.57.1)

```powershell
$py = 'G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
# 1) snapshot current state
& $py -m pip freeze --all > H:\Object\Comfyui mcp\drama3_pip_freeze_rollback_point.txt
# 2) roll transformers+hub back to the plugin pin
& $py -m pip install "transformers==4.57.1" "huggingface-hub==0.36.2"
# 3) re-verify the plugin + the rest of the venv
cd G:\...\custom_nodes\Comfyui-Drama-3\portable
& $py -m pytest tests/test_transformers_compat.py -q -p no:cacheprovider
# 4) RE-INSTALL OR REMOVE Higgs_v3-TTS-ComfyUI (it will fail to import on 4.57.1)
```
Full pre-change state is preserved in `drama3_pip_freeze_before.txt`, so any of the 9 added
packages can be removed individually (`pip uninstall cython dynet38 iniconfig kaldi-native-fbank
kaldiio nagisa pluggy pytest soynlp`) and the venv restored byte-for-byte in version terms.

---

## 4. Step 4 — Dependency installation into the ComfyUI venv

All installs used the venv's own interpreter (`…\.venv\Scripts\python.exe -m pip`), never a system
Python. **No package was removed and no existing package was upgraded.**

### 4.1 Dry run first (authoritative delta)

`pip install --dry-run -r Comfyui-Drama-3/requirements.txt` against the live venv:
```
Would install Cython-3.3.0 dyNET38-2.2 huggingface_hub-0.36.2 kaldi_native_fbank-1.22.5
            kaldiio-2.18.1 nagisa-0.3.0 soynlp-0.0.493 transformers-4.57.1
```
→ only the two pinned packages are contested; the other 8 are genuinely missing.

### 4.2 Installed (only what was genuinely missing)

| Package | Version | Why |
|---|---|---|
| `nagisa` | 0.3.0 | plugin requirement (JP word segmentation) — was missing, broke test collection |
| `soynlp` | 0.0.493 | plugin requirement (forced aligner text normalisation) |
| `kaldi-native-fbank` | 1.22.5 | plugin requirement |
| `kaldiio` | 2.18.1 | plugin requirement |
| `dyNET38` | 2.2 | transitive dep of `nagisa` (cp313 win_amd64 wheel) |
| `cython` | 3.3.0 | build dep of `dyNET38` (cp313 win_amd64 wheel) |
| `pytest` | 9.2.0 | **test harness** (added by me to run the plugin's compat test) |
| `pluggy` | 1.7.0 | transitive dep of pytest |
| `iniconfig` | 2.3.1 | transitive dep of pytest |

All wheels (no source builds), `packaging` was left at 26.3 (already satisfied).

### 4.3 Requirements that were ALREADY satisfied and were left alone

`torch 2.12.1+cu130`, `torchaudio 2.11.0+cu130`, `safetensors 0.8.0`, `tokenizers 0.22.2`,
`einops 0.8.2`, `scipy 1.18.1`, `soundfile 0.14.0`, `accelerate 1.12.0`, `librosa 1.0.0`,
`imageio-ffmpeg 0.6.0`, `sox 1.5.0`, `soxr 1.1.0`, `onnxruntime 1.30.0`.

### 4.4 Final state vs. the plugin's requirements.txt

```
$ pip install --dry-run -r Comfyui-Drama-3/requirements.txt
Would install huggingface_hub-0.36.2 transformers-4.57.1
```
→ **the ONLY outstanding delta is the two deliberate pins** from §3.4. Everything else in
`requirements.txt` is installed and version-matching.

### 4.5 pip freeze before/after diff

`drama3_pip_freeze_before.txt` (208 lines) → `drama3_pip_freeze_after.txt` (217 lines)

```
=== ADDED (9) ===
  cython == 3.3.0
  dynet38 == 2.2
  iniconfig == 2.3.1
  kaldi_native_fbank == 1.22.5
  kaldiio == 2.18.1
  nagisa == 0.3.0
  pluggy == 1.7.0
  pytest == 9.2.0
  soynlp == 0.0.493

=== REMOVED ===  (none)
=== CHANGED ===  (none)
=== UNCHANGED === 207 packages
```

Unchanged and explicitly verified still in place:
`torch 2.12.1+cu130`, `torchaudio 2.11.0+cu130`, `transformers 5.5.0`, `huggingface_hub 1.33.0`,
`tokenizers 0.22.2`, `numpy 2.5.2`, `safetensors 0.8.0`, `accelerate 1.12.0`, `librosa 1.0.0`,
`onnxruntime 1.30.0`, `soundfile 0.14.0`, `einops 0.8.2`, `scipy 1.18.1`.

---

## 5. Step 5 — R2T2 native runtime (plugin's own `install.py`)

### 5.1 First run: FAILED — and why (not a bad artifact)

```
$ python install.py
Downloading R2T2 CUDA native runtime (no Python or model weights)...
ValueError: Runtime archive integrity check failed; installation unchanged
```
(`install.py:78` — `if total != manifest['bytes'] or digest(archive) != manifest['sha256']`.)

Diagnosis:
- `r2t2-runtime.json` → url `…/releases/download/v0.3.0/Drama3-R2T2-native-win64-cu128.zip`,
  `bytes = 610460680`, `sha256 = c075593eefe24c96977246e0815c52163d7b9d5df297766df242b5a2bcf3bccd`.
- **The manifest is correct**: upstream `SHA256SUMS.txt` for release **v0.3.0** publishes exactly
  `c075593eefe24c96977246e0815c52163d7b9d5df297766df242b5a2bcf3bccd  Drama3-R2T2-native-win64-cu128.zip`.
- HEAD probe: `status 200`, `Content-Length: 610460680` (== manifest), `Accept-Ranges: bytes`,
  magic bytes `PK\x03\x04` (valid ZIP).
- **Actual cause: the `release-assets.githubusercontent.com` CDN truncates the stream.** A direct
  `urlopen` fetch delivered only **14,187,051 of 610,460,680 bytes** in 8.8 s, then closed.
  `install.py` sees `total != manifest['bytes']` and (correctly) aborts without touching the tree.

### 5.2 Remediation (no plugin source was modified)

Resumable download with HTTP `Range` (Python urllib) → then `curl -C -` resume, per the lead's
instruction. The download URL is the **original `github.com/.../releases/download/...` URL** (not the
resolved signed CDN URL, which expires in ~40 min).

```powershell
curl.exe -L --retry 30 --retry-delay 3 --retry-all-errors --speed-time 60 --speed-limit 10240 `
         -C - -o "H:\Object\Comfyui mcp\drama3_r2t2_runtime.zip" `
         "https://github.com/T8mars/Comfyui-Drama-3/releases/download/v0.3.0/Drama3-R2T2-native-win64-cu128.zip"
```

Verification:
```
bytes : 610460680 (expect 610460680) -> True
sha256: c075593eefe24c96977246e0815c52163d7b9d5df297766df242b5a2bcf3bccd
expect: c075593eefe24c96977246e0815c52163d7b9d5df297766df242b5a2bcf3bccd -> True
```

Extraction (zip root = `lib/ backends/ licenses/`) →
`G:\...\custom_nodes\Comfyui-Drama-3\r2t2-runtime\`.

### 5.3 Authoritative verification by the plugin's own installer

```
$ cd G:\...\custom_nodes\Comfyui-Drama-3
$ python install.py
R2T2 native runtime verified.
INSTALL_EXITCODE=0
```

`install.py` re-verified **all 30 manifest files** individually (size + SHA-256) and printed
`R2T2 native runtime verified.` — it took the "already present and intact" path, i.e. every
extracted byte matches the upstream manifest. (Note `install.py`'s `existing_file()` fallback also
looks for `licenses/*` at the plugin root, which already carries an identical license set — not needed
here because the archive's own `licenses/` were extracted into the runtime dir.)

Installed layout:
```
r2t2-runtime/
  lib/       ggml.dll  ggml-base.dll  llama.dll  mtmd.dll  drama_r2t2.dll
             cublas64_12.dll  cublasLt64_12.dll  cudart64_12.dll   <-- CUDA 12.8 runtime
  backends/  ggml-cpu.dll  ggml-cuda.dll
  licenses/  24 license/notice files
```
**No model weights are in this bundle** (manifest = DLLs + licenses only).

### 5.4 Real load test — CUDA 12.8 runtime vs. the +cu130 torch

**(A) isolated** (no torch preloaded):
```
step2 CDLL ggml.dll -> loaded in 4.32 s
step3 ggml_backend_dev_count()      -> 2
step4 ggml_backend_dev_by_type(0 CPU) -> FOUND
step5 ggml_backend_dev_by_type(1 CUDA)-> FOUND
step9 CDLL drama_r2t2.dll -> r2t2_api_version() -> 1
DONE R2T2_NATIVE_RUNTIME_LOADS=YES
```

**(B) realistic ComfyUI order (torch 2.12.1+cu130 imported and a CUDA op executed FIRST):**
```
torch first: 2.12.1+cu130 cuda 13.0 avail True
torch CUDA op: 0.0
runtime_directory: …\custom_nodes\Comfyui-Drama-3\r2t2-runtime
_load_library() OK in 0.06 s
r2t2_api_version: 1
[stderr] ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24563 MiB):
         Device 0: NVIDIA GeForce RTX 4090, compute capability 8.9, VMM: yes, VRAM: 24563 MiB
```

**The plugin's own loader (`drama3_t8/r2t2/native.py::_load_library`) succeeds with the cu130 torch
already resident.** There is **no** "CUDA 12.8 runtime vs cu130 torch mismatch" problem. Why:

- **No DLL soname collision.** torch cu130 ships `cublas64_13.dll`, `cublasLt64_13.dll`,
  `cudart64_13.dll`; the R2T2 bundle ships `cublas64_12.dll`, `cublasLt64_12.dll`, `cudart64_12.dll`.
  Different filenames ⇒ both CUDA stacks coexist in one process.
- **Search-order is correct.** `native.py:70-76` registers `r2t2-runtime/lib` and
  `r2t2-runtime/backends` *before* torch's `site-packages/torch/lib`, so ggml-cuda.dll binds the
  runtime's own CUDA 12.8 libraries.
- **Driver is new enough.** NVIDIA driver **621.01** on the RTX 4090 ⇒ CUDA 12.8 apps (needs ≥570)
  and CUDA 13.0 (needs ≥580) both run.
- `drama_r2t2.dll` reports `r2t2_api_version() == 1` — the ABI matches what `native.py` expects.

The benign stderr line `load_backend: failed to find ggml_backend_init in …\ggml-cuda.dll` seen in the
isolated probe is **not** an error: the CUDA backend was already registered by `ggml.dll`'s own
load-time init, so the explicit `ggml_backend_load()` call is a no-op. The plugin only calls it when
`ggml_backend_dev_by_type(1)` is NULL — which it is not.

**Full inference (a real transcription) was not exercised**: it needs the `Confucius4-R2T2-Q8_0.gguf`,
`mmproj-Confucius4-R2T2-Q8_0.gguf` and the `FireRedVAD-ONNX` directory, which are **model weights and
explicitly out of my scope** (models teammate). The runtime/library/ABI/CUDA layer is fully verified.

---

## 6. Step 6 — Import checks (outside a running ComfyUI)

Harness: a clean subprocess per node, `sys.path` = [ComfyUI core, custom_nodes] (ComfyUI core first,
exactly like the real loader), with a **stub for `server.PromptServer.instance`** (a real ComfyUI
server is not running; `PromptServer.instance` is only set in `PromptServer.__init__`). The stub
provides `routes = aiohttp.web.RouteTableDef()` and an `app`, which is all `register_routes()` uses.

### 6.1 Drama-3 — real entry point (`__init__.py` → `comfy_entrypoint()` → `get_node_list()`)

```
{"target": "Comfyui-Drama-3", "ok": true, "nodes": 30,
 "classes": ["T8DramaAlign","T8DramaBranch","T8DramaCodecDecode","T8DramaCodecEncode",
   "T8DramaCreativeBatch","T8DramaCreativeDelivery","T8DramaCreativeProjectCreate",
   "T8DramaCreativeProjectExport","T8DramaCreativeProjectImport","T8DramaCreativeProjectLoad",
   "T8DramaCreativeTextPreview","T8DramaDecode","T8DramaEditor","T8DramaGenerate","T8DramaInfill",
   "T8DramaLive","T8DramaLoadSession","T8DramaLoader","T8DramaR2T2Transcribe","T8DramaReference",
   "T8DramaSRT","T8DramaSaveSession","T8DramaScene","T8DramaSession","T8DramaTranscribe",
   "T8DramaVoiceCastBuild","T8DramaVoiceCastLoad","T8DramaVoiceLibraryList","T8DramaVoiceLibraryLoad",
   "T8DramaVoiceLibrarySave"]}
```
**30 node classes register with no exception** — matches the independent count from the workflows
teammate (30 node classes, `GET_NODE_INFO_V1()` on all of them).

### 6.2 High-risk pre-existing nodes (same venv, after all installs)

| Node | Result | Nodes registered |
|---|---|---|
| `ComfyUI-FeiHou-Easy-H3` | ✅ ok | 16 |
| `ComfyUI-Qwen-TTS` | ✅ ok | 9 |
| `Higgs_v3-TTS-ComfyUI` | ✅ ok | 5 |
| `ComfyUI-WanVideoWrapper` | ✅ ok | 147 |
| `ComfyUI_GJJ_Nodes` | ✅ ok | 365 |

**All 6/6 import clean on the final venv state.**

> Harness note (not a dependency problem): two first-pass failures were caused by the *harness*, not
> the venv — (a) `sys.path` order made `import nodes` resolve to `custom_nodes/ComfyUI-Qwen-TTS/nodes.py`
> instead of ComfyUI's core `nodes.py`; (b) `PromptServer.instance` is `None` outside a live server.
> Both were fixed in the harness (correct path order + `PromptServer.instance` stub).

---

## 7. Model paths — for the workflows teammate

`install.py` places **nothing** under `ComfyUI\models\ASR`. It only creates
`custom_nodes\Comfyui-Drama-3\r2t2-runtime\` (lib / backends / licenses). The ASR **model files are
user configuration**, resolved by `drama3_t8/model_paths.py`:

- `model_path()`: absolute/UNC paths stay absolute; **relative paths resolve against the models root
  the user selects in the plugin's runtime settings** — *not* auto-discovered under `models\ASR`.
- Defaults (relative names):
  - `r2t2_model` → `Confucius4-R2T2-GGUF/Confucius4-R2T2-Q8_0.gguf`
  - `r2t2_projector` → `Confucius4-R2T2-GGUF/mmproj-Confucius4-R2T2-Q8_0.gguf`
  - `r2t2_vad` → `FireRedVAD-ONNX` (a **directory**; must contain `fireredvad_stream_vad_with_cache.onnx`
    and `cmvn.ark`)
- Integrity: `native.py` checks the GGUF magic `GGUF\3` plus a **pinned size + SHA-256** per role
  (`model`: 1,834,422,208 B / `151097e43957a19984ea7de66e8144ce69b95039eb31c93da4f58db367e455c3`;
  `projector`: 348,336,544 B / `8dc2c67e6a0484114928142d098db7ad94ae9f34c78948ef9d37a9678418cb65`).

⇒ Unless the plugin's models root is deliberately set to ComfyUI's own `models\ASR`, the R2T2/ASR
path widgets in a workflow **must be absolute paths** (or relative to the plugin's configured root).
The `"asr"` category is not registered in `extra_model_paths.yaml`, so ComfyUI will not expose it as a
relative model folder.

---

## 8. Write scope / hygiene

| Path | Action |
|---|---|
| `…\.venv\Lib\site-packages` | 9 packages added (pip). **No plugin source file was modified.** |
| `…\custom_nodes\Comfyui-Drama-3\r2t2-runtime` | created by the plugin's own `install.py` (30 files, each sha256-verified) |
| `H:\Object\Comfyui mcp\drama3_deps_report.md` | this report |
| `H:\Object\Comfyui mcp\drama3_pip_freeze_before.txt` / `…_after.txt` | freeze snapshots |
| `H:\Object\Comfyui mcp\drama3_compat_test_final.log` | compat test output |
| `H:\Object\Comfyui mcp\drama3_install_py.log` | installer log |
| `H:\Object\Comfyui mcp\drama3_r2t2_runtime.zip` | verified installer archive (610 MB — safe to delete) |
| `H:\Object\Comfyui mcp\drama3_r2t2_dl*.log` | download attempt logs |

**ComfyUI was NOT restarted** (port 8188 left alone, as instructed).

---

## 9. Status

**deps DONE.** The plugin is dependency-complete in the shared venv, its native runtime is installed
and verified, and all 30 of its nodes register cleanly. The shared venv is intact for the other 54
custom nodes (6 high-risk ones re-verified after every install).
