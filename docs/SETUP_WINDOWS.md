# Windows 开发与验证入口

M2 受限试验入口与最新结果见 [M2_DESKTOP_E2E](reports/M2_DESKTOP_E2E.md)。正常 `python -m assistant` 中可在模型页分别测试连接/工具；Key 仅通过 `scripts/mavis_model.py --save-key` 隐藏录入。电脑操作默认关闭，应用内先按 Ctrl+Alt+F12 测试、在概览复位，再在权限页授权本次受限操作；支持 `打开记事本`、`输入：<最多16个单行BMP字符>`。已有用户窗口不接管、不保存文件。以下原 M0/M1 文本为历史说明，其中“所有真实输入未接入”由此受限增量取代，不表示完整 M2 通过。

2026-11-02；仅 M0/M1 源码开发版，**不是 v0.1 完成版或安装包**。首版仍要求语音唤醒与真实 Computer Use。先读 [当前状态](IMPLEMENTATION_STATUS.md)、[已知限制](KNOWN_LIMITATIONS.md) 和 [上游构建说明](ONEDIR_PACKAGING.md)。

所有命令工作目录为仓库根 `D:\AAA_Favio\AI_exploring\projects\dafeiyu-mavis`，Shell 为 PowerShell，普通权限。不要用系统默认 `python`：本机默认解析到 LibreOffice 自带 Python。

## 安装锁定开发环境

```powershell
uv python install 3.11.14
uv venv --python 3.11.14 .venv
uv pip sync --python .venv/Scripts/python.exe requirements-mavis.lock.txt
uv pip check --python .venv/Scripts/python.exe
```

锁文件是本机 Windows x64 / Python 3.11 的组合。不要把 Windows-Use 审计依赖装进产品环境。

## 启动最小核心

```powershell
.venv/Scripts/python.exe -m assistant
# 明确的测试模式：审批只改变测试计数器，不操作 Windows
.venv/Scripts/python.exe -m assistant --test-mode --data-home '.scratch/手动验收 含空格'
# 不加载桌宠渲染的核心诊断窗口；仍使用同一产品单实例门
.venv/Scripts/python.exe -m assistant --test-mode --core-only --data-home '.scratch/核心诊断'
```

默认数据目录 `%LOCALAPPDATA%\DaFeiYuMavis`，测试库 `state-test.db`、正式库 `state.db` 分开。不会自动导入旧桌宠配置、聊天或 Key。控制中心关闭是隐藏，从托盘恢复；应用退出先急停并结束自有 worker。

当前文字入口只保存指令并显示“M2 Provider 未接入”，不会假装执行。语音、模型、真实输入均显示未就绪。只有测试模式提供“开始审批演练”和“挂起 worker 测急停”。

## 自动测试与原生 smoke

```powershell
.venv/Scripts/python.exe scripts/mavis_tests.py --name local-m1 tests/mavis -q
.venv/Scripts/python.exe scripts/mavis_tests.py --name local-upstream tests -q
.venv/Scripts/python.exe -m ruff check assistant tests/mavis scripts/mavis*.py pet/app.py pet/config.py pet/feature_activation.py
.venv/Scripts/python.exe scripts/mavis_core_probe.py
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe scripts/mavis_ui_smoke.py --baseline
.venv/Scripts/python.exe scripts/mavis_ui_smoke.py --scale 1.5 --profile-label '中文 路径 '
```

`mavis_tests.py` 将 APPDATA/LOCALAPPDATA/USERPROFILE/TEMP 等仅在测试子进程中指向唯一 `.scratch` 目录，默认 keyring 使用失败后端；原生凭据探针另行验证。选择已有 Git Bash 进行上游 `bash -n` 语法检查，避免 System32 的无 WSL 发行版入口。日志写 `.scratch/m0-m1/evidence/<name>.txt`，末尾有真实退出码；全量已知 abort 不能当作通过。

UI smoke 在真实 Qt 窗口中通过本窗口按钮的 `.click()` 调用业务入口，只抓取本应用 QWidget，不截取用户桌面；它不是 Windows-Use 键鼠输入测试。`--scale 1.5` 是 Qt 缩放因子，**不等同于把 Windows 系统 DPI 改成 150%**。正常 smoke 应退出；探针自带 25 秒线程栈诊断与终止上限，异常原始记录不得删除。

## 语音、TTS 与凭据 spike

```powershell
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe scripts/mavis_voice_spike.py --download
.venv/Scripts/python.exe scripts/mavis_voice_spike.py --infer --tts-smoke
.venv/Scripts/python.exe scripts/mavis_credential_probe.py
```

下载两个固定官方 release 资源到 `.scratch/m0-m1/models`，不执行压缩包内脚本；大小检查、安全解包、SHA-256 清单均留存。旧官方资源没有独立 digest，目前哈希为本地测量，尚需发布前固定受信清单；ASR 权重许可待核实。推理使用包内 WAV 和本地 SAPI 合成的测试 WAV，不采集麦克风、不播放扬声器。

凭据探针只写自己新生成的 `probe/<uuid>` 标记，另一进程读取并比对后删除。它从不读取现有用户 API Key，也没有明文回退。最小冻结探针复现：

```powershell
.venv/Scripts/python.exe -m PyInstaller --onedir --noconfirm --name mavis-credential-probe --distpath .scratch/m0-m1/frozen --workpath .scratch/m0-m1/frozen-build --specpath .scratch/m0-m1 --paths . --collect-all keyring --collect-all win32ctypes scripts/mavis_credential_probe.py
.scratch/m0-m1/frozen/mavis-credential-probe/mavis-credential-probe.exe
```

这是凭据依赖打包验证，不是完整桌宠、语音或 Computer Use 安装包。

## Windows-Use 审计复现

```powershell
uv venv --python 3.11.14 .venv-audit
uv pip sync --python .venv-audit/Scripts/python.exe requirements-audit.lock.txt
.venv-audit/Scripts/python.exe scripts/mavis_audit_windows_use.py
```

脚本在导入前拒绝网络/子进程尝试、禁 dotenv 自动搜索，只读取自己的 Qt 窗口。保持这些防护；不要照上游示例直接运行完整 Agent。参见 [审计报告](WINDOWS_USE_ADAPTER_AUDIT.md)。

## 待人工/实机验证步骤

1. 测试模式打开“挂起 worker 测急停”，**物理按** Ctrl+Alt+F12，确认 UI 锁定、子进程结束；同时验证真实按钮和托盘入口。现有自动测试只证明 OS 注册/冲突、WM_HOTKEY 分派及 StopController 链路。
2. 在 Windows 系统 100/125/150/200% DPI、双屏混合 DPI 下，检查拖拽、点击、托盘、原设置、退出再启动；当前只有单屏真实 96 DPI 与 Qt 1.5 倍缩放样本。
3. 在用户明确授权录音后实现/运行真实麦克风链；目前没有录音入口，不能拿合成语音声称唤醒准确率。
4. M2 的文件/GUI 验证只用新建专用目录；现有文件换新名称，不覆盖。`scripts/mavis_fixture_server.py` 提供 loopback 测试页，`mavis_fixture_oracle.py` 只读校验结果。M2 需为测试 HTTP origin 单独设计范围，当前生产 URL 策略只允许 HTTPS。

本轮没有 DeepSeek API 调用、真实键鼠注入、锁屏绕过、管理员窗口接管、消息发送或真实文件删除/覆盖。
