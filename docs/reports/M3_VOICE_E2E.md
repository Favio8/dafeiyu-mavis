# M3 本地语音接入与验收

更新：2026-11-02。分支 `codex/m3-voice`，基于已同步的 `12b0d1e`。用户确认当前没有麦克风，改为先完成实现及可运行验收入口。**M3 Gate 尚未通过；没有把合成音频、设备缺失清理或短时 TTS 当成真人麦克风验收。**

## 已落地路径

`Qt QAudioSource → 单一 PCM 流/必要重采样 → 16kHz 单声道 → 2 秒内存预缓冲 → sherpa KWS 时间戳 → VAD 断句 → 最终 ASR → VoiceHost → 原 Controller → 同一个 TaskService/NativeTasks/权限网关/验证器/SQLite`。

音频在独立 `assistant.voice_worker` 子进程中采集、识别和播报；复用原有私有 stdio IPC 的 nonce、序列和消息大小约束。生命周期 worker 与 voice worker 各有固定命令白名单，语音 worker 无审批、策略变更或桌面派发命令。独立急停直接终止其自有进程。没有新增音频依赖，继续使用 sherpa-onnx 1.12.26、PySide6 6.12.0、现有 numpy/pywin32。

- 默认麦克风关闭，校准模式默认开启，只回显文字。最终文本才进入任务；空指令和只喊唤醒词只留 VoiceAttempt 元数据。
- 预缓冲按 KWS 时间戳裁剪；只在文本开头按唤醒边界处理同音转写，正文里的“大肥鱼”保留。ASR 未提供置信度，原样为 null。
- 一次录音最长 12 秒，手动录音等待开口最长 5 秒，VAD 为本地 Silero；手动结束/取消、设备错误、关闭监听和退出有清理路径。活动任务中语音新指令被记录为 `busy_ignored`，不排队；语音“同意”不会审批。
- 语音取消立即设置独立急停；语音暂停在下一原生动作派发前确认。澄清答案可以关联原任务记录，**现有 M2 通用 Runtime 的澄清后恢复仍未接通**，不会假装恢复执行。
- TTS 使用本地 SAPI，枚举声音、音量、试听、停止和错误降级；播放前关采集并清空未提交缓冲，进入 `PLAYBACK_GUARD`。结束加 700ms 冷却，按原监听偏好恢复；原本 OFF 保持 OFF。只有后置验证通过的终态才播报“已验证，操作完成”。
- UI 提供设备选择、真实输入音量、中文唤醒词、灵敏度、手动录音、文字核对/修正、模型下载/导入/移除和语音尝试记录；托盘录音入口与 Ctrl+Alt+Space 已接线。唤醒词等偏好持久保存，麦克风/电脑权限不持久恢复。
- Windows 会话锁定/休眠通知和设备变化接线负责关闭语音；实机锁屏、休眠、拔插验证尚未执行。

## 模型与许可

固定来源、大小、文件/压缩包 SHA-256、tokenizer、许可与来源在 `assistant/assets/voice-models.json`；哈希是对固定官方发布资产的本地实测值，不是上游签名。

| 资源 | 固定组合 | 实际确认 |
|---|---|---|
| KWS | zipformer-wenetspeech-3.3M-2024-01-01；epoch-12-avg-2-chunk-16-left-64，encoder/joiner int8、decoder fp32；ppinyin | 复用 M0 官方包；完整文件哈希复核、本地真实加载；模型卡 Apache-2.0 |
| ASR | paraformer-zh-small-2024-03-09，model.int8.onnx、tokens.txt | 官方包与来源 README 已读；真实推理。ModelScope 基础模型 metadata 为 Apache-2.0；crazyant ONNX 转换仓库的 License 字段为空，分发许可继续待确认 |
| VAD | sherpa 官方 `silero_vad.onnx`，643854 bytes | 本轮真实下载；SHA-256 `9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`；Silero MIT |

来源：[KWS 官方示例](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/keyword-spotter-from-microphone.py)、[VAD 官方示例](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/vad-microphone.py)、[ASR 来源](https://www.modelscope.cn/models/crazyant/speech_paraformer_asr_nat-zh-cn-16k-common-vocab8358-onnx/summary)、[基础 ASR 模型](https://www.modelscope.cn/models/damo/speech_paraformer_asr_nat-zh-cn-16k-common-vocab8358-tensorflow1/summary)、[Silero 许可](https://github.com/snakers4/silero-vad/blob/master/LICENSE)。

模型管理只导入 manifest 中列出的普通数据文件，不执行压缩包脚本、不调用 tar.extract。校验失败不能就绪；移除操作只删除应用模型目录内的登记文件，保留其他文件。语音资源和合成测试 WAV 均留在忽略的本地缓存，不入 Git。

## 实际运行结果

| 命令/检查 | 真实结果 | 证据 |
|---|---|---|
| Qt `QMediaDevices.audioInputs()` 与 WinMM `waveInGetNumDevs()` | 两者均为 0；用户确认无麦克风 | 本轮工具输出；真人验证待设备 |
| 固定模型导入与 VoiceEngine 实例化 | KWS/ASR/VAD 均通过哈希并实际加载 | `.scratch/m3/models/`；正式可复现命令见下文 |
| `scripts/mavis_voice_probe.py` | 连续句“打开记事本”、正文保留“大肥鱼”、仅唤醒词无指令、自定义“小助手”共 4 个固定合成句全部通过；有明确唤醒内容的音频在 guard 下未进入 KWS | `.scratch/m3/evidence/1793628506737725100/result.json`、`synthetic-*.wav` |
| 同一探针 ASR → Controller → TaskService | 3 条真实 ASR 输出形成 source=voice 的测试模式任务，保留原始/修正文本；电脑权限关闭，均为 FAILED / COMPUTER_CONTROL_DISABLED / action_count=0 | 同目录 `profile/state-test.db` 与 `real_asr_to_shared_task_gate_passed=true` |
| 同一探针真实 SAPI 播放与 private IPC | 实际播放含“大肥鱼”的句子；PLAYBACK_GUARD → playback_end → OFF，未偷偷开麦；开启监听返回真实 MICROPHONE_UNAVAILABLE；关闭确认 buffer_samples=0；自有进程退出 | 同目录 worker_events；不算真实麦克风释放证明 |
| `scripts/mavis_tests.py --name m3-focused tests/mavis/test_voice.py tests/mavis/test_ipc.py tests/mavis/test_bridge.py -q` | 29 passed | `.scratch/m0-m1/evidence/m3-focused.txt` |
| `scripts/mavis_tests.py --name m3-regression tests/mavis -q` | 176 passed, 1 skipped，43.73s | `.scratch/m0-m1/evidence/m3-regression.txt` |
| 收尾 `--name m3-delivery-focused tests/mavis/test_voice.py tests/mavis/test_bridge.py tests/mavis/test_native_tasks.py tests/mavis/test_worker_contract.py -q` | 14 passed，5.98s；覆盖偏好持久化、原语前暂停、来源/转写、忙碌不排队和无效语音元数据不建任务 | `.scratch/m0-m1/evidence/m3-delivery-focused.txt` |
| `scripts/mavis_voice_acceptance.py --ui-probe` | Windows 原生 1100/720 无横向滚动，截图上/下区域可达，未开麦 | `.scratch/m3/acceptance/1793628506831420500/` |
| 同上 `--dark` | 深色原生页面同样通过 | `.scratch/m3/acceptance/1793628571932361700/` |
| 增量 ruff、compileall、git diff --check | 退出 0 | `.scratch/m3/final-checks.txt` |

兼容性试错保留：sherpa-onnx 1.12.26 不能在构造 KWS 时使用空 keywords_file，首次退出 1；改为应用缓存内以词条哈希命名的文件后加载成功。VAD 内部活动片段缓存改为覆盖最长录音的 16 秒；2 秒预缓冲仍独立受限。固定回放只运行两轮，第二轮增加真实 ASR → 同一个 Controller 的证据，没有据此计算真人召回率。

## 可运行真人验收

已有本机模型缓存时：

```powershell
.venv/Scripts/python.exe scripts/mavis_voice_acceptance.py
```

其他环境可在应用语音页下载固定模型，或准备相同 manifest 的离线模型目录：

```powershell
.venv/Scripts/python.exe scripts/mavis_voice_models.py --root .scratch/m3/models --download
.venv/Scripts/python.exe scripts/mavis_voice_models.py --root .scratch/m3/models --import-dir D:/path/to/complete/model-cache
```

验收顺序：

1. 接入麦克风，刷新设备，选择后应用配置。保持校准模式开启，再开启监听，确认真实音量变化和 ARMED 状态。
2. 无刻意停顿地说“大肥鱼帮我打开记事本”；再说“大肥鱼输入你好我是大肥鱼”、仅“大肥鱼”。检查前两条文字及正文保留，最后一条没有任务。原始音频不落盘。
3. 换“小助手”并应用；新词应触发，旧词不触发。严格/标准/灵敏为当前模型的 0.45/0.25/0.15，并非未经测量的成功率。
4. 试听含唤醒词的 TTS，观察保护状态；播报中关闭监听，结束应保持 OFF。再开启监听测试恢复。长期专项入口如下，先手动刷新并开启真实麦克风，脚本才开始计时：

```powershell
.venv/Scripts/python.exe scripts/mavis_voice_acceptance.py --tts-soak-seconds 1800
```

5. 长测结束保留 `tts_soak.completed`、实际 playback 数量、wake/final 事件计数和 capture 开/关序列。只有真实开过麦克风的报告才会标记 release 已观察；否则明确为 pending。过程中出现的非测试人声需单独核对，不能归因于自播放。
6. 在实际录音中关闭监听、取消、关闭验收窗口、按 Ctrl+Alt+F12，检查 capture=false、缓冲清空与自有进程退出；另做锁屏、休眠、拔插和重新选择设备验证。
7. 进入语音→真实 GUI 前，先物理测试急停并复位，在电脑权限页授予本次 Notepad 范围，再关闭校准。先说打开记事本，再说输入指令；检查同一 TaskService 的动作、许可和独立验证记录。忙碌时第二条新命令不能排队，“同意”不能批准动作。

验收窗口配置与 SQLite 使用新的 `.scratch/m3/acceptance/<run>/profile/`；关闭窗口结束该隔离 host。日志只保留状态与必要元数据。`--tts-soak-seconds` 入口已实现，**本轮未运行 30 分钟实测**。

## 待验证与阻塞

- DEV-025/026/027/029/030 的真人、声学回声、真实设备释放、拔插/锁屏/休眠、物理录音热键均待麦克风与人类配合；未进行 200 条/5 人、10 小时负样本或 30 分钟自播放基准。
- DEV-031 的 B 站、网页搜索和通用模型失败/澄清恢复仍依赖未完成的 M2 路径；本轮没有绕过权限增加浏览器黑箱。Notepad 语音→GUI 本轮亦未实机完成。
- ONNX ASR 转换包许可、冻结 worker/音频插件完整打包及干净机安装均未完成。
- 未重跑已有失败的全上游 Qt 套件；本轮不宣称全仓门禁通过。

## 本轮修改映射

| 文件 | 目的 |
|---|---|
| `assistant/assets/voice-models.json`、`voice_models.py` | 固定模型来源/哈希/许可，下载、离线导入、校验和管理缓存 |
| `assistant/voice_engine.py`、`voice_audio.py` | 连续 PCM、重采样、预缓冲、KWS/VAD/ASR 与命令边界 |
| `assistant/voice_worker.py`、`voice_tts.py` | 独立采集和本地半双工播报 |
| `assistant/voice_host.py`、`voice_preferences.py` | 生命周期、过期回调、热键、会话通知、显式偏好 |
| `assistant/voice_ui.py`、`ui.py`、`ui_theme.py` | 语音页、任务中的语音尝试视图、真实状态与可访问入口 |
| `assistant/controller.py`、`service.py`、`native_tasks.py`、`storage.py` | 原 TaskService 接入、来源/原始文本、暂停、VoiceAttempt 持久化 |
| `assistant/ipc.py`、`stop.py`、`pet_bridge.py` | 固定语音 worker 消息、急停拥有关系、录音热键和原托盘/气泡复用 |
| `scripts/mavis_voice_{models,probe,acceptance}.py` | 可复现模型准备、真实固定回放和真人验收入口 |
| `tests/mavis/test_voice.py` | 六个与任务完整性、边界、采样和持久化相关的检查 |
| `docs/IMPLEMENTATION_STATUS.md`、`SETUP_WINDOWS.md`、`INDEX.md`、`CHANGE_MANIFEST.md`、本报告 | 本轮状态、操作步骤、映射与证据 |

原 AGENTS、README、产品 PRD/清单、上游 renderer、用户密钥和用户文件未修改。未调用付费 API；没有把已配置 Key 放进语音进程、偏好文件或日志。
