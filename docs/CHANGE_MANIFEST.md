# 累计实际文件清单（M0～M2）

M5增量（2026-11-03）：相对 `90af76f` 的安全基础实现为 `91b2947`；后续补停止源日志、START事件修复和便携run.bat。逐文件目的与+/-见 [M5 PR报告](PR-REPORT-MAVIS-M5-2026-11-03.md#修改文件说明)。20/20专项和8小时限定工况最终结果已补齐，原失败继续保留；模型/音频/截图/日志/数据库/凭据、便携数据和soak worktree留本机。

M4增量（2026-11-02）：相对 `b3fbb41` 的模块与文件映射见 [M4报告](reports/M4_UI_ACCEPTANCE.md#本轮修改文件)。当前是已实现/待统一验收状态，不将早期表的行数或测试结果当成本轮结果。

M3 语音增量（2026-11-02）：相对同步提交 `12b0d1e` 的逐模块变更清单见 [M3报告](reports/M3_VOICE_E2E.md#本轮修改映射)。原累计表是此前阶段快照；模型缓存、合成 WAV、SQLite 和凭据均不随本次源码发布。

后续 UI 增量（2026-11-02）：本表为之前 M2 的行数快照；本次控制中心、图标与透明流光的准确修改清单见 [UI 报告](reports/UI_DESIGN_2026-11-02.md#实际修改文件)，不将整个已有未提交目录重新算作本轮新增。

2026-11-02；相对固定上游 commit 截至本轮的累计增量。没有提交/推送。参见 [M0/M1报告](PR-REPORT-MAVIS-M0-M1-2026-11-02.md)、[M2报告](PR-REPORT-MAVIS-M2-2026-11-02.md) 与 [状态](IMPLEMENTATION_STATUS.md)。上轮清单快照保留在 .scratch/m2/evidence/m0-manifest.json。

根 AGENTS.md、README.md 保持用户原始字节；两项相对上游的大差异不计为本轮编辑。docs/product 原文保留并忽略。上游导入的其余未变文件不重复列入。

修改文件行数来自 `git diff --numstat`；新增文件为实际行数/+N/-0。源码/证据哈希清单保存在本机 `.scratch/m0-m1/evidence/change-manifest.json`。模型、截图、日志、DB、venv、凭据探针二进制不入 Git。

| 文件 | + / - | 改动与目的 |
|---|---|---|
| [.gitignore](../.gitignore) | +4/-0 | 保护本地产品文档、venv、coverage 和生成数据，不上传。 |
| [.python-version](../.python-version) | +1/-0 | 固定已实测的 Python 3.11.14。 |
| [assistant/__init__.py](../assistant/__init__.py) | +3/-0 | DaFeiYu Mavis core. Importing this package performs no I/O or desktop actions. |
| [assistant/__main__.py](../assistant/__main__.py) | +50/-0 | Independent Mavis entry; desktop presentation remains the upstream pet app. |
| [assistant/actions.py](../assistant/actions.py) | +75/-0 | Small, closed tool schemas. No arbitrary callable, command, or raw URI dispatch. |
| [assistant/contracts.py](../assistant/contracts.py) | +227/-0 | Versioned host-owned records. Unknown measurements remain null, never guesses. |
| [assistant/controller.py](../assistant/controller.py) | +253/-0 | Qt signal bridge to a single controller/SQLite writer thread. |
| [assistant/credentials.py](../assistant/credentials.py) | +54/-0 | Windows Credential Manager only. No config, database, log or plaintext fallback. |
| [assistant/gateway.py](../assistant/gateway.py) | +231/-0 | Host-owned action gate and one-use permits. M1 has no real input backend. |
| [assistant/ipc.py](../assistant/ipc.py) | +167/-0 | Private parent/child stdio pipes: bounded JSON, no listener, pickle or dynamic code. |
| [assistant/model_diagnostics.py](../assistant/model_diagnostics.py) | +27/-0 | Separate connection/tool probes; never create successful user tasks or enable input. |
| [assistant/native_tasks.py](../assistant/native_tasks.py) | +117/-0 | Restricted deterministic tasks used by the existing Controller, not a second service. |
| [assistant/notepad_backend.py](../assistant/notepad_backend.py) | +188/-0 | Restricted GUI pilot: a newly launched empty Notepad, one Unicode scalar per grant. |
| [assistant/pet_bridge.py](../assistant/pet_bridge.py) | +114/-0 | Thin adapter to upstream public tray and bubble APIs; no renderer replacement. |
| [assistant/policy.py](../assistant/policy.py) | +153/-0 | Fail-closed local policy, independent of prompts, pages and model risk labels. |
| [assistant/privacy.py](../assistant/privacy.py) | +12/-0 | Central storage redaction; credential values never enter the task API. |
| [assistant/provider.py](../assistant/provider.py) | +157/-0 | Bounded DeepSeek HTTP client. No SDK auto-telemetry, redirects or plaintext keys. |
| [assistant/runtime.py](../assistant/runtime.py) | +191/-0 | Single-task model loop atop the M1 state machine, gateway and host verifier. |
| [assistant/service.py](../assistant/service.py) | +219/-0 | Single task state machine. No worker, tool or UI owns a competing task state. |
| [assistant/stop.py](../assistant/stop.py) | +102/-0 | Independent stop latch and Windows message-thread hotkey; no Qt/LLM dependency. |
| [assistant/storage.py](../assistant/storage.py) | +168/-0 | SQLite single-writer store. Every snapshot and its event commit atomically. |
| [assistant/system_backend.py](../assistant/system_backend.py) | +88/-0 | Narrow L1 executor: registered Notepad launch only. No shell, URI or GUI input. |
| [assistant/ui.py](../assistant/ui.py) | +286/-0 | Minimal readable Qt control centre: real records, local approval, persistent stop. |
| [assistant/verifier.py](../assistant/verifier.py) | +65/-0 | Independent postconditions. Model text and tool return values are not evidence. |
| [assistant/visual_gate.py](../assistant/visual_gate.py) | +28/-0 | Visual fallback prerequisites only. No screenshot upload or coordinate executor. |
| [assistant/windows_observer.py](../assistant/windows_observer.py) | +171/-0 | Read-only Windows identity observations and a session-wide executor lease. |
| [assistant/worker.py](../assistant/worker.py) | +46/-0 | M1 lifecycle worker. It has no model, microphone or desktop-input imports. |
| [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) | +36/-0 | Mavis M0/M1 实际架构 |
| [docs/CHANGE_MANIFEST.md](../docs/CHANGE_MANIFEST.md) | +98/-0 | 本轮生成的逐文件审查清单。 |
| [docs/DATA_SCHEMA.md](../docs/DATA_SCHEMA.md) | +23/-0 | M1 数据与恢复 |
| [docs/IMPLEMENTATION_STATUS.md](../docs/IMPLEMENTATION_STATUS.md) | +73/-0 | IMPLEMENTATION_STATUS — M0 / M1 / M2 |
| [docs/INDEX.md](../docs/INDEX.md) | +27/-0 | 登记 Mavis 文档与上游快照，保持可追踪。 |
| [docs/KNOWN_LIMITATIONS.md](../docs/KNOWN_LIMITATIONS.md) | +21/-0 | M0/M1 已知限制与进入 M2 的门槛 |
| [docs/PR-REPORT-MAVIS-M0-M1-2026-11-02.md](../docs/PR-REPORT-MAVIS-M0-M1-2026-11-02.md) | +39/-0 | Mavis M0/M1 交付报告 |
| [docs/PR-REPORT-MAVIS-M2-2026-11-02.md](../docs/PR-REPORT-MAVIS-M2-2026-11-02.md) | +51/-0 | Mavis M2 受控原生路径交付记录（未完成全部 DEV-015～023） |
| [docs/SETUP_WINDOWS.md](../docs/SETUP_WINDOWS.md) | +87/-0 | Windows 开发与验证入口 |
| [docs/TOOL_CONTRACTS.md](../docs/TOOL_CONTRACTS.md) | +32/-0 | M1 工具与许可契约 |
| [docs/UPSTREAM_BASELINE.md](../docs/UPSTREAM_BASELINE.md) | +76/-0 | Mavis M0 上游与依赖基线 |
| [docs/WINDOWS_USE_ADAPTER_AUDIT.md](../docs/WINDOWS_USE_ADAPTER_AUDIT.md) | +53/-0 | Windows-Use 逐动作接入审计 |
| [docs/adr/001-mavis-m0-baseline.md](../docs/adr/001-mavis-m0-baseline.md) | +13/-0 | ADR-001：M0/M1 兼容性与隔离 |
| [docs/adr/002-m2-controlled-pilot.md](../docs/adr/002-m2-controlled-pilot.md) | +15/-0 | ADR-002：M2 受限原生试验与渐进接入 |
| [docs/reports/COMMAND_LOG.md](../docs/reports/COMMAND_LOG.md) | +41/-0 | M0/M1 实际执行命令与证据索引 |
| [docs/reports/M0_BASELINE_RUN.md](../docs/reports/M0_BASELINE_RUN.md) | +35/-0 | M0 本机运行与兼容性报告 |
| [docs/reports/M1_CORE_TESTS.md](../docs/reports/M1_CORE_TESTS.md) | +32/-0 | M1 核心与安全测试报告 |
| [docs/reports/M2_DESKTOP_E2E.md](../docs/reports/M2_DESKTOP_E2E.md) | +73/-0 | M2 受控实机推进报告（尚未通过完整 M2 Gate） |
| [docs/upstream/AGENTS.md](../docs/upstream/AGENTS.md) | +307/-0 | 锁定上游工程规范快照；根空 AGENTS 原样保留。 |
| [docs/upstream/README.md](../docs/upstream/README.md) | +768/-0 | 锁定上游说明快照；保留用户根 README。 |
| [pet/app.py](../pet/app.py) | +7/-2 | Mavis 装配入口与旧缓存/注册表清理隔离；保留原 AppShell。 |
| [pet/config.py](../pet/config.py) | +8/-0 | 独立数据命名空间；禁止复制旧桌宠配置/会话。 |
| [pet/feature_activation.py](../pet/feature_activation.py) | +4/-0 | M0/M1 关闭上游可选模块，避免绕过新网关。 |
| [requirements-audit.in](../requirements-audit.in) | +5/-0 | 隔离的 Windows-Use 审计依赖与 SDK 兼容约束。 |
| [requirements-audit.lock.txt](../requirements-audit.lock.txt) | +4912/-0 | 隔离审计环境的完整解析和哈希。 |
| [requirements-mavis.in](../requirements-mavis.in) | +18/-0 | 可审查的运行/开发直接依赖与候选精确版本。 |
| [requirements-mavis.lock.txt](../requirements-mavis.lock.txt) | +2224/-0 | Windows 运行环境全部传递依赖与下载哈希。 |
| [scripts/mavis_audit_windows_use.py](../scripts/mavis_audit_windows_use.py) | +94/-0 | Audit installed Windows-Use, with shell/network blocked before its first import. |
| [scripts/mavis_core_probe.py](../scripts/mavis_core_probe.py) | +87/-0 | Measured core/stop probe. Only isolated test records and owned worker processes. |
| [scripts/mavis_credential_probe.py](../scripts/mavis_credential_probe.py) | +45/-0 | Real cross-process vault probe using a random disposable marker, never an API Key. |
| [scripts/mavis_fixture_oracle.py](../scripts/mavis_fixture_oracle.py) | +23/-0 | Independent, read-only oracle for a new UTF-8 test document. |
| [scripts/mavis_fixture_server.py](../scripts/mavis_fixture_server.py) | +17/-0 | Manual M2 fixture server. This is test infrastructure, not product IPC. |
| [scripts/mavis_gui_probe.py](../scripts/mavis_gui_probe.py) | +166/-0 | Real GUI pilot: a fresh empty Notepad, per-character grants, independent UIA oracle. |
| [scripts/mavis_gui_start.py](../scripts/mavis_gui_start.py) | +80/-0 | User-started GUI pilot: a real foreground gesture, no focus-stealing workaround. |
| [scripts/mavis_inventory.py](../scripts/mavis_inventory.py) | +33/-0 | Local dependency/license/source inventory, containing no environment secrets. |
| [scripts/mavis_model.py](../scripts/mavis_model.py) | +59/-0 | Local secure credential setup and separate small, explicitly requested API probes. |
| [scripts/mavis_physical_stop.py](../scripts/mavis_physical_stop.py) | +78/-0 | User-assisted physical hotkey test. Never synthesizes a hotkey or desktop input. |
| [scripts/mavis_system_probe.py](../scripts/mavis_system_probe.py) | +77/-0 | Explicit real L1 acceptance: gateway -> fixed Notepad launch -> independent window oracle. |
| [scripts/mavis_tests.py](../scripts/mavis_tests.py) | +61/-0 | Run pytest in a private workspace profile; never replace the user's profile. |
| [scripts/mavis_ui_smoke.py](../scripts/mavis_ui_smoke.py) | +186/-0 | Native/offscreen Qt smoke using only our own widgets and an isolated profile. |
| [scripts/mavis_voice_spike.py](../scripts/mavis_voice_spike.py) | +167/-0 | Download fixed official model archives and run CPU inference without a microphone. |
| [scripts/mavis_windows_probe.py](../scripts/mavis_windows_probe.py) | +52/-0 | Read-only native observation + cross-process lease probe; never injects input. |
| [tests/fixtures/mavis/controlled.html](../tests/fixtures/mavis/controlled.html) | +20/-0 | 后续 GUI 验收的可变顺序测试页及独立结果字段。 |
| [tests/mavis/test_bridge.py](../tests/mavis/test_bridge.py) | +49/-0 | Quit must revoke execution before hide-on-close or upstream decoder cleanup. |
| [tests/mavis/test_controller_m2.py](../tests/mavis/test_controller_m2.py) | +116/-0 | Admission, consent and cancellation at the existing controller boundary. |
| [tests/mavis/test_core.py](../tests/mavis/test_core.py) | +50/-0 | M1 safety requirements at the public controller boundary (no real input). |
| [tests/mavis/test_credentials.py](../tests/mavis/test_credentials.py) | +35/-0 | Credential references cannot target other products; backend failures do not leak secrets. |
| [tests/mavis/test_gateway.py](../tests/mavis/test_gateway.py) | +141/-0 | Approval/TOCTOU/replay/storage safety tests; effects are isolated fixture counters. |
| [tests/mavis/test_ipc.py](../tests/mavis/test_ipc.py) | +87/-0 | Real private-pipe worker tests; injected Windows messages never type into user apps. |
| [tests/mavis/test_namespace.py](../tests/mavis/test_namespace.py) | +40/-0 | Mavis composes the upstream core without borrowing its credentials or optional agents. |
| [tests/mavis/test_native_input_guard.py](../tests/mavis/test_native_input_guard.py) | +73/-0 | Native input boundary tests with an inert SendInput sink; real GUI probes are separate. |
| [tests/mavis/test_native_tasks.py](../tests/mavis/test_native_tasks.py) | +65/-0 | Host workflow tests substitute only OS effects; no real applications are opened. |
| [tests/mavis/test_observation_verifier.py](../tests/mavis/test_observation_verifier.py) | +62/-0 | Postconditions and native leases cannot be replaced by tool/model success text. |
| [tests/mavis/test_policy.py](../tests/mavis/test_policy.py) | +81/-0 | Local policy never accepts model risk labels or a page's purported permission. |
| [tests/mavis/test_policy_positive.py](../tests/mavis/test_policy_positive.py) | +36/-0 | Positive scopes stay narrow, and semantic uncertainty always stops the action. |
| [tests/mavis/test_privacy_m2.py](../tests/mavis/test_privacy_m2.py) | +12/-0 | 模块/测试入口。 |
| [tests/mavis/test_provider.py](../tests/mavis/test_provider.py) | +103/-0 | API contract/transport safety; no fixture is counted as a live provider test. |
| [tests/mavis/test_runtime.py](../tests/mavis/test_runtime.py) | +63/-0 | Model proposals use the existing host state machine, never an independent agent. |
| [tests/mavis/test_storage_state.py](../tests/mavis/test_storage_state.py) | +184/-0 | Durability, recovery, exhaustive terminal guards, and honest verification semantics. |
| [tests/mavis/test_ui.py](../tests/mavis/test_ui.py) | +113/-0 | Real Qt event loop and controller thread, with isolated SQLite and private workers. |
| [tests/mavis/test_worker_contract.py](../tests/mavis/test_worker_contract.py) | +32/-0 | Exercise the worker parser with private in-memory streams; no code deserialization. |
