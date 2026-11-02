# M0 本机运行与兼容性报告

2026-11-02；[基线](../UPSTREAM_BASELINE.md)、[状态](../IMPLEMENTATION_STATUS.md)、[命令与复现](../SETUP_WINDOWS.md)。原始证据仅在工作区 `.scratch/m0-m1/evidence/`，不随 Git 上传。下面全部区分实测与待验证。

## 环境

Windows 11 专业版 10.0.26200，Intel i7-10700F，16 逻辑核、15.91 GiB RAM，x64，普通权限；单屏 1920×1080，实际系统 DPI=96。`QT_SCALE_FACTOR=1.5` 是 Qt 缩放测试，不是系统 DPI 设置变更。默认系统 Python 指向 LibreOffice，因此使用独立 CPython 3.11.14 venv。

## 实测

| 内容 | 真实结果 | 原始证据 |
|---|---|---|
| 依赖 runtime/audit | pip check 均通过；80 / 210 个发行包；锁文件含哈希 | `pip-check-runtime.txt`, `pip-check-audit.txt`, `runtime-dependencies.json` |
| Qt 6.10.2 原聊天主题 | 全量及单独复跑原生访问冲突 | `upstream-baseline.txt`, `upstream-focused.txt` |
| Qt 6.12.0 原聊天主题单文件 | 20 passed | `qt612-chat.txt` |
| Qt 6.12.0 上游全量 | fatal abort；未完成；最终 runner 退出 124 | `upstream-qt612-final.txt` 及 `upstream-qt612-final-diagnostic/pytest-breadcrumb.txt` |
| 上游受影响子集 | 初次 257 passed / 2 failed；2 项因选到 System32/WSL bash；测试环境使用已安装 Git Bash 后 259 passed | `upstream-affected.txt`, `upstream-affected-final.txt` |
| 原生底座安静样本 | 1 个呈现目标、托盘可见，118834 非透明像素，4 次采样中 3 个不同帧；正常退出 | `baseline-1-8d66a43f/result.json`、本应用窗口 PNG |
| 原生底座负载失败 | 非透明像素 0，reader 退役池增长；不能算通过 | `baseline-1-91cec55c/result.json`、对应隔离 profile 的 pet log |
| 原生 Qt 1.5 倍样本 | 可见角色截图；托盘与窗口存在 | `baseline-1.5-d19c94e2/`；没有完整帧率统计 |
| 真实 FFmpeg | 固定 argv 解码一帧成功，921600 字节；二进制 7.1，GPLv3+ | `ffmpeg-license.txt`、`inventory-run.txt` |
| Windows-Use | 固定 wheel 可在保护下导入；本进程窗口 UIA PID/标题匹配；遥测 client 未创建；检测到其他出站/进程尝试并拒绝 | `windows-use-audit.json`, `windows-use-audit-final.txt` |
| 中文 ASR | 实际 CPU 模型转写包内 16kHz `0.wav`，输出保存在 JSON | `voice-spike.json` |
| 中文 KWS / 本地 TTS | Huihui 中文本地声音可用；本地合成“大肥鱼”“小助手”各一次，KWS 均检测到；静音无关键词 | `tts-kws-spike.json`, `voice-spike.json` |
| WinVaultKeyring | 源码及最小冻结产物均跨进程读回测试标记，并删除自己的标记 | `credential-source.txt`, `credential-frozen.txt`, `credential-build.txt` |

KWS archive：`sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01.tar.bz2`，32654866 字节；ASR archive：`sherpa-onnx-paraformer-zh-small-2024-03-09.tar.bz2`，77920048 字节。全部 archive/解包文件哈希见 `.scratch/m0-m1/models/model-manifest.json`。候选关键词通过真正的 ppinyin tokenizer；默认/自定义词合成样本不是用户麦克风准确率。

## 失败和未覆盖

保留缺失 sherpa 候选版本、缺少 sentencepiece、mistralai 3.7.0 不兼容、Qt 原生崩溃、首帧失败以及原 smoke 探针退出问题。上游相关失败未无声修复或归因给新功能。

没有完整拖动/点击/原设置/重启的人工验收、系统真实 150%/混合 DPI 矩阵、8 小时稳定性、完整打包、真实麦克风或 DeepSeek API 测试。动画与 ASR 权重的精确分发许可仍需补齐。

M0 产物已建立，但“所有运行/许可/回归门已通过”不成立；下一步按 [限制清单](../KNOWN_LIMITATIONS.md) 执行。
