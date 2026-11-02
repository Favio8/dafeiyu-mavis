# Mavis 组件与素材许可清单

核对日期：2026-11-03。以下是实际安装元数据、随包许可文件哈希和来源清单，不是对整个产品作MIT或商用授权。

## 尚未闭合的权利与分发条件

- 角色动画：继续保留原作者/来源与非商业限制；精确素材许可版本及分发权未独立确认，不扩大授权。
- ASR基础模型metadata为Apache-2.0，ONNX转换仓库许可字段为空；转换包权利链仍待核实。
- imageio-ffmpeg自带FFmpeg实际编译含--enable-gpl和--enable-version3，不能只写Python封装的BSD/MIT。
- Qt/PySide及传递依赖的许可正文/通知仍需在M6实际产物中核对；本轮没有完整安装包。

## 语音资源来源

| 资源 | 声明/已核对内容 | 来源 |
|---|---|---|
| kws | Apache-2.0 | https://www.modelscope.cn/models/pkufool/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01 |
| asr | Apache-2.0 base model; ONNX converter license unspecified | https://www.modelscope.cn/models/damo/speech_paraformer_asr_nat-zh-cn-16k-common-vocab8358-tensorflow1/summary |
| vad | MIT | https://github.com/snakers4/silero-vad/blob/master/LICENSE |

模型版本、大小、包/文件SHA-256及tokenizer仍以 `assistant/assets/voice-models.json` 为准。ModelScope本轮实查：KWS与基础ASR为Apache License 2.0，转换仓库License为空；不将空字段推定成已确认授权。

## 当前安装发行包

许可栏按元数据原文提取；未声明项不自动视为MIT。完整文件列表和SHA在本机审计JSON。

| 发行包 | 版本 | 许可元数据 | 许可文件数 |
|---|---|---|
| aiohappyeyeballs | 2.7.1 | PSF-2.0 | 1 |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT | 2 |
| aiosignal | 1.4.0 | Apache 2.0 | 1 |
| altgraph | 0.17.5 | MIT | 1 |
| annotated-types | 0.8.0 | MIT | 1 |
| attrs | 26.1.0 | MIT | 1 |
| backports.tarfile | 1.2.0 | not declared in metadata | 1 |
| certifi | 2026.10.23 | MPL-2.0 | 1 |
| charset-normalizer | 3.5.2 | MIT | 1 |
| colorama | 0.4.6 | not declared in metadata | 1 |
| colorlog | 6.12.0 | MIT License | 1 |
| comtypes | 1.4.17 | MIT | 1 |
| coverage | 7.17.0 | Apache-2.0 | 2 |
| edge-tts | 7.3.1 | not declared in metadata | 1 |
| flatbuffers | 25.12.19 | Apache 2.0 | 0 |
| frozenlist | 1.8.0 | Apache-2.0 | 1 |
| idna | 3.20 | BSD-3-Clause | 1 |
| imageio-ffmpeg | 0.6.0 | BSD-2-Clause | 1 |
| importlib_metadata | 10.1.0 | Apache-2.0 | 1 |
| iniconfig | 2.3.1 | MIT | 1 |
| jaraco.classes | 3.4.0 | not declared in metadata | 1 |
| jaraco.context | 6.1.2 | MIT | 1 |
| jaraco.functools | 4.6.0 | MIT | 1 |
| keyring | 25.6.0 | not declared in metadata | 1 |
| lunar_python | 1.4.8 | MIT | 1 |
| more-itertools | 11.2.1 | MIT | 1 |
| multidict | 7.2.1 | Apache-2.0 | 1 |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | 20 |
| omegaconf | 2.4.0 | not declared in metadata | 1 |
| onnxruntime | 1.31.1 | MIT License | 1 |
| opencv-python-headless | 5.0.0.93 | Apache 2.0 | 4 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | 1 |
| pefile | 2023.2.7 | MIT | 1 |
| pillow | 11.3.0 | MIT-CMU | 1 |
| pluggy | 1.7.0 | MIT | 1 |
| propcache | 0.5.4 | Apache-2.0 | 1 |
| protobuf | 7.36.2 | 3-Clause BSD License | 1 |
| psutil | 7.1.0 | BSD-3-Clause | 1 |
| pycaw | 20260927 | MIT | 1 |
| pyclipper | 1.4.0 | MIT | 1 |
| pydantic | 2.11.9 | MIT | 1 |
| pydantic_core | 2.33.2 | MIT | 1 |
| Pygments | 2.21.0 | BSD-2-Clause | 1 |
| pyinstaller | 6.16.0 | GPLv2-or-later with a special exception which allows to use PyInstaller to build and distribute non-free programs (including commercial ones) | 1 |
| pyinstaller-hooks-contrib | 2026.9 | not declared in metadata | 1 |
| pypinyin | 0.55.0 | MIT | 1 |
| PySide6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 1 |
| PySide6_Addons | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 1 |
| PySide6_Essentials | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 1 |
| PySide6_Pdf | 6.12.0.140 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 1 |
| PySide6_WebEngine | 6.12.0.140 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 1 |
| pytest | 8.4.2 | MIT | 1 |
| pytest-cov | 6.2.1 | MIT | 2 |
| pywin32 | 311 | PSF | 4 |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause | 1 |
| PyYAML | 6.0.3 | MIT | 1 |
| rapidocr | 3.10.0 | Apache-2.0 | 2 |
| requests | 2.34.2 | Apache-2.0 | 1 |
| ruff | 0.13.3 | not declared in metadata | 1 |
| sentencepiece | 0.2.1 | not declared in metadata | 0 |
| setuptools | 84.2.1 | MIT | 13 |
| shapely | 2.2.0 | BSD-3-Clause | 1 |
| sherpa-onnx | 1.12.26 | Apache licensed, as found in the LICENSE file | 1 |
| sherpa-onnx-core | 1.12.26 | Apache-2.0 | 0 |
| shiboken6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 1 |
| six | 1.17.0 | MIT | 1 |
| tabulate | 0.10.0 | MIT | 1 |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | 0 |
| typing-inspection | 0.4.4 | MIT | 1 |
| typing_extensions | 4.16.0 | PSF-2.0 | 1 |
| tzdata | 2026.6 | Apache-2.0 | 1 |
| urllib3 | 2.8.0 | MIT | 1 |
| winrt-runtime | 4.1.0 | MIT | 1 |
| winrt-Windows.Foundation | 4!10.0.28000.2957 | MIT | 1 |
| winrt-Windows.Foundation.Collections | 4!10.0.28000.2957 | MIT | 1 |
| winrt-Windows.Media | 4!10.0.28000.2957 | MIT | 1 |
| winrt-Windows.Media.Control | 4!10.0.28000.2957 | MIT | 1 |
| winrt-Windows.Storage.Streams | 4!10.0.28000.2957 | MIT | 1 |
| yarl | 1.25.1 | Apache-2.0 | 1 |
| zipp | 4.1.2 | MIT | 1 |

审计证据：`.scratch/m5/audit/1793638043749642600/inventory.json`。未把包元数据等同于最终二进制全部授权；详见 `THIRD_PARTY_NOTICES.md` 的原素材声明和 `docs/reports/M5_SAFETY_STABILITY.md`。
