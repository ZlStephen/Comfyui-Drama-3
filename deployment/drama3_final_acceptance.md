# Drama-3 部署验收报告

**状态：passed**  ·  2026-11-01 11:05:51

## 权重校验（以 t8star/Drama-3-Comfy 的 model-manifest.json 为准）

| 文件 | 字节 | sha256 | 结果 |
|---|---|---|---|
| `drama3-t8-fp8.safetensors` | 38578460824 | 013fe091c5d6bc7c | ok |
| `drama3-text-head.safetensors` | 1033371816 | b92f64bdc9db6f21 | ok |
| `drama3-line-head.safetensors` | 8480 | 59ca2d328d79c89f | ok |
| `qwen3-asr-06b.safetensors` | 1564928184 | eb350ce7510a538e | ok |
| `drama3-codec.safetensors` | 1565647484 | 90e21f45f8a12e02 | ok |
| `Confucius4-R2T2-GGUF/Confucius4-R2T2-Q8_0.gguf` | 1834422208 | 151097e43957a199 | ok |
| `Confucius4-R2T2-GGUF/mmproj-Confucius4-R2T2-Q8_0.gguf` | 348336544 | 8dc2c67e6a048411 | ok |
| `FireRedVAD-ONNX/fireredvad_stream_vad_with_cache.onnx` | 2306042 | b3c97836130dc34f | ok |
| `FireRedVAD-ONNX/cmvn.ark` | 1311 | c87f6f13edf0f0ec | ok |
| `qwen3_forced_aligner_0.6b_bf16.safetensors` | 1835545592 | 9c33d08ca9236dca | ok |
| `qwen-aligner/config.json` | 5982 | （上游未提供哈希） | ok |
| `qwen-aligner/model.safetensors` | 1835544544 | （上游未提供哈希） | ok |
| `qwen-aligner/tokenizer_config.json` | 12666 | （上游未提供哈希） | ok |
| `qwen-aligner/vocab.json` | 2776833 | （上游未提供哈希） | ok |
| `qwen-aligner/merges.txt` | 1671853 | （上游未提供哈希） | ok |
| `qwen-aligner/preprocessor_config.json` | 330 | （上游未提供哈希） | ok |
| `qwen-aligner/generation_config.json` | 115 | （上游未提供哈希） | ok |
| `qwen-aligner/chat_template.json` | 1161 | （上游未提供哈希） | ok |
| `campplus-zh-en.onnx` | 28281164 | aa3cfc16963a1058 | ok |

## 端到端冒烟测试

- prompt_id：`25213ccf-dc42-487d-9ef6-5240ce3f47f5`
- 状态：success
- 输出文件数：1
  - `D:\ComfyUI\output\Drama3_T8\smoke_test_00001.flac` — 173224 字节

## GitHub

- fork: https://github.com/ZlStephen/Comfyui-Drama-3
- 分支: `deployment/windows-4090`
