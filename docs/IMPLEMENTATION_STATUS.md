# IMPLEMENTATION_STATUS — M0 / M1 / M2 / M3

更新：2026-11-02。M2 已完成真实 DeepSeek 探针、受限系统启动与 Notepad GUI 输入试验；**DEV-015～023 尚未全部完成，M2 Gate 未通过**。M0/M1 完整出门缺口继续保留，不能称为 v0.1 已完成。

## M3 最新状态

用户确认当前没有麦克风，先完成实现和可运行验收入口。真实本地模型固定回放、SAPI 短时播报及同一 TaskService 接入已通过；**真人麦克风、30 分钟声学防自唤醒和设备释放尚未实测，M3 Gate 未通过**。详见 [M3_VOICE_E2E](reports/M3_VOICE_E2E.md)。

| DEV | 状态 | 已实现 / 实证 | 尚未完成 |
|---|---|---|---|
| DEV-024 | 开发中 | 固定 manifest、来源/大小/文件与包哈希/tokenizer；下载/导入/校验/缓存移除；KWS/ASR 复用固定官方包，VAD 本轮真实下载；三模型实际加载 | ASR 基础模型 Apache-2.0 已查，ONNX 转换包许可字段为空；完整打包资源验证待做 |
| DEV-025 | 待验证 | 独立 Qt 单采集源、重采样、16kHz mono、2秒预缓冲、本地 Silero VAD、手动结束/取消、5秒等待开口/12秒上限；PCM 连续采样检查通过 | 本机 Qt/WinMM 输入设备均0；真实采集、关闭/错误/锁屏/休眠设备释放待实机 |
| DEV-026 | 待验证 | 默认/自定义词、2–8汉字 ppinyin、单活动词、三档模型绑定阈值、应用失败保留原配置；默认“大肥鱼”与“小助手”真实模型合成回放通过 | 新旧词真人切换、召回/误触发基准及噪声集未跑 |
| DEV-027 | 待验证 | KWS时间戳+预缓冲、仅前缀边界清理、最终ASR、原始/修正文本、null置信度、VoiceAttempt；连续句/正文保留唤醒词/只喊词合成回放通过 | 真人连续说话、不清晰/方言/噪声与最长录音等设备场景 |
| DEV-028 | 开发中 | 实际本地ASR → 原 Controller/TaskService/NativeTasks；source=voice、相同授权网关/验证链；忙碌丢弃、不凭语音审批、独立取消与原语前暂停；3条真实ASR生成权限关闭的0动作任务 | M2通用模型路径与澄清后恢复仍缺失；当前仅记录澄清答案，不伪装已恢复 |
| DEV-029 | 待验证 | 本地SAPI枚举/音量/试听/停止；PLAYBACK_GUARD关采集清缓冲与冷却；真实短时播报后保持原OFF；正样本波形在guard被阻断 | 真实麦克风+扬声器自播放30分钟、原ON恢复及播放中关闭的声学实机专项 |
| DEV-030 | 待验证 | 麦克风选择/真实音量/错误与设备变化处理、Ctrl+Alt+Space、托盘入口、录音/识别/忙碌/停止状态及原桌宠气泡；Windows明暗720/1100页面已看图 | 实际拔插/默认设备变化/重连、麦克风隐私拒绝及物理录音热键待硬件验收 |
| DEV-031 | 待验证 | `mavis_voice_acceptance.py`真人窗口与30分钟专项入口；`mavis_voice_probe.py`真实模型回放和SAPI探针；Mavis回归176通过/1跳过，收尾重点14通过 | 用户无麦克风；语音→真实GUI未跑，B站/网页搜索依赖未完成M2，不能标记完成 |

## M2 最新状态

2026-11-02 UI 增量：已按用户确认完成蓝白控制中心、原创 M core SVG/PNG/ICO 和提交事件驱动的屏幕边缘流光。Windows 单屏原生焦点/边缘命中查询、透明中心、停止隐藏、720/1100 与 Qt 1.5 缩放已验证；Mavis 回归 171 passed / 1 skipped。未重跑真实输入任务，未扩大权限或 M2 验收范围。详见 [UI 变更与证据](reports/UI_DESIGN_2026-11-02.md)。下表的未完成项仍然有效。

| DEV | 状态 | 已实现 / 实证 | 尚未完成 |
|---|---|---|---|
| DEV-015 | 开发中 | `provider.py/model_diagnostics.py`、安全凭据工具、控制中心连接/工具探针；deepseek-flash 两项真实 API 测试通过，usage 原样记录 | 视觉能力真实探针、完整配置管理；目前仅官方 HTTPS origin |
| DEV-016 | 开发中 | `runtime.py` 复用 TaskService/网关的单步模型循环、审批恢复、预算、禁止模型口头成功；`native_tasks.py` 接控制中心确定性受限指令 | 通用自然语言与完整模型循环尚未全面接入控制中心；澄清/恢复和全面预算测试待补 |
| DEV-017 | 开发中 | 固定 Notepad 系统启动经网关派发一次，窗口 0→1，独立后置验证通过 | URL/授权目录/注册应用管理和广泛窗口操作未完成 |
| DEV-018 | 开发中 | 已核对实际 UIA COM seam；原生受限 pilot 绕开完整 Agent/SDK | 尚未交付完整 Windows-Use 工具层适配；不能把 native pilot 等同于该项完成 |
| DEV-019 | 开发中 | 特定 HWND/PID/进程身份/完整性/焦点/DPI观察、跨进程用户会话 lease、上下文 watchdog；只读实机探针通过 | 锁屏/休眠原生通知、用户非注入输入钩子、同名多窗/混合 DPI/遮挡矩阵、原生调用进程隔离 |
| DEV-020 | 开发中 | 真实窗口/编辑区焦点与逐 BMP 字符 SendInput，每字新许可、停止与独立 UIA 读回；测试文本通过 | 滚动、拖动、广泛快捷键、窗口布局、长文本/复杂 Unicode、Explorer/浏览器等未完成 |
| DEV-021 | 开发中 | 窗口/UIA文本/URL/文件哈希 verifier；实机窗口和文本通过，tool-ok 假成功负向测试 | 浏览器/文件真实闭环与更广泛 oracle 绑定测试 |
| DEV-022 | 开发中 | 只有屏幕授权/模型能力/风险/上下文/裁剪范围的拒绝门 | 截图、上传、视觉定位与受控点击、B30 均未完成 |
| DEV-023 | 待验证 | 真 API、真实 Notepad启动/输入成功；完整失败尝试保留，成功 GUI 样本含用户点击开始的人工起点 | B站、GUI 新文件保存审批、完整文字→模型→GUI、故障矩阵与无人干预 M2 验收未通过 |

详细命令、数据与未覆盖项见 [M2_DESKTOP_E2E](reports/M2_DESKTOP_E2E.md)。最新整套 164 passed / 1 skipped，行/分支/综合覆盖为80.54% / 66.58% / 77.22%，未达到全部安全门槛。

下表保留 M0/M1 收尾快照。其“未接入/未验证”描述中的增量以本节为准：本轮已验证真实物理热键2.05ms、session lease与受限原生窗口观察；尚未完成完整会话/输入安全验收。

状态按配套清单使用：未开始 / 开发中 / 待验证 / 已验证 / 阻塞 / 后置。“已验证”仅覆盖本表明确写出的本轮范围；不把 fixture、Qt offscreen 或直接按钮调用冒充 Computer Use。

统一命令工作目录：仓库根；Shell：PowerShell。原始输出 `.scratch/m0-m1/evidence/`，不上传个人数据。详见 [M0 报告](reports/M0_BASELINE_RUN.md)、[M1 报告](reports/M1_CORE_TESTS.md)、[实际文件清单](CHANGE_MANIFEST.md)。

| DEV | 状态 | 本轮实际实现 / 证据 | 未覆盖与最小下一步 |
|---|---|---|---|
| DEV-001 | 已验证 | 固定上游 SHA、upstream remote、codex 分支，保留原始文件；读完上游规范/开发/构建/测试约束；`UPSTREAM_BASELINE.md`、`docs/upstream/` | 原始空 AGENTS 与短 README 保持不变，不拿其相对上游差异冒充本轮编辑 |
| DEV-002 | 阻塞 | 原生窗口/托盘、透明像素与动画变化已有成功证据；`baseline-1-8d66a43f/`；Qt 1.5 倍和中文/空格路径有样本 | 负载下首帧失败、全量 Qt abort；完整拖动/点击/原设置/重启、系统 DPI 矩阵未验。先解决稳定底座门禁 |
| DEV-003 | 待验证 | Python3.11.14、Qt6.12.0、sherpa1.12.26、keyring25.6、审计 windows-use0.8.1 实装；两份带哈希锁；pip check 通过；ADR-001 | 完整上游回归/全产品打包未通过，不将“可导入”当全面兼容 |
| DEV-004 | 已验证 | 真实源码/方法/危险路径、wheel 哈希、PostHog 与 LiteLLM 出站审计；真实自有窗口 UIA；原方法体逐原语替身拦截；`WINDOWS_USE_ADAPTER_AUDIT.md`、`windows-use-audit.json` | 实际 Windows 输入适配器未接入，属于 M2；完整 Agent 永不直接启用 |
| DEV-005 | 待验证 | ppinyin 构建默认/自定义词；真实 KWS、ASR、Huihui 本地合成；WinVaultKeyring 源码/冻结跨进程通过；`voice-spike.json`、`tts-kws-spike.json`、`credential-frozen.txt` | 麦克风与真人唤醒未验；ASR 权重独立许可待核实；不是完整语音打包验证 |
| DEV-006 | 已验证 | `ARCHITECTURE.md`、上游复用映射、`python -m assistant`、独立目录与禁止旧数据迁移；namespace 红→绿；真实气泡/控制中心/托盘接线 | 保持 renderer 不变；下一阶段先处理底座阻塞，不开启旧可选系统工具 |
| DEV-007 | 已验证 | `assistant/contracts.py/actions.py`：七类记录及 ToolResult、严格 Schema、枚举/预算/nullable；`test_core.py/test_storage_state.py/test_policy*.py` | M2 原生观察和真实工具契约只能增量扩展；本轮未交付全仓静态类型检查 |
| DEV-008 | 已验证 | `service.py`：合法转移、单任务、generation、终态、取消优先、暂停确认、预算超时、独立 verification；新增套件 | 当前没有 LLM 回调；迟到回调用控制器测试验证，不宣称 API 实测 |
| DEV-009 | 待验证 | `storage.py`：WAL/事务/外键/唯一键/有序事件、单写者、故障关闭、崩溃恢复、终态清理；DB 锁/半事务/磁盘错误测试 | 目前只有 schema v1；真实升级迁移与备份轮转/自动保留策略未实现；磁盘满为故障注入 |
| DEV-010 | 已验证 | `ipc.py/worker.py/controller.py`：真实父子私有管道、闭合 Schema、nonce/seq/大小限制、EOF/崩溃、自己的进程句柄清理；最终测试还核对 worker 实际 PID 退出 | worker 仅生命周期探针；VoiceWorker/LLM worker 和冻结版 worker 路由属 M2/M3/M6 |
| DEV-011 | 待验证 | `policy.py/gateway.py`：范围与危险动作、URI/路径/快捷键、自操作/完整性/未知语义拒绝，测试覆盖 | 原生 HWND/焦点/完整性观察源未接；真实 reparse 用例跳过；不开放实际 GUI 输入 |
| DEV-012 | 已验证 | 真实 Qt 审批界面；Host-only authority、60秒许可、一用、参数/上下文/代数绑定；拒绝/失效/重放/DB错误无 fixture 副作用 | 真实文件或 Windows 输入审批仍待 M2，当前 UI 明确标测试 |
| DEV-013 | 待验证 | 独立 RegisterHotKey 线程、注册冲突/WM_HOTKEY 测试、stop latch、自有 worker 终止、UI/托盘入口、退出先停止；20次挂起 worker 测试 | 物理热键、真实输入最后派发点、自产生按键释放、锁屏/休眠/会话通知尚未实机验证；启用输入前补齐 |
| DEV-014 | 已验证 | `tests/mavis/`、`tests/fixtures/mavis/controlled.html`、loopback fixture server、独立只读文件 oracle；test/live DB 分开；需求映射如下 | fixture 供后续 GUI 验收，不是已经跑过 B01–B30 / 50 条安全基准；完整随机布局和实机集留待 M2/M5 |

## 命令与退出码

| 验证 | 实际命令（根目录 PowerShell） | 结果 / 证据 |
|---|---|---|
| 新增最终套件 | `.venv/Scripts/python.exe scripts/mavis_tests.py --name m1-complete tests/mavis -q --cov=assistant --cov-branch --cov-report=term-missing --cov-report=json:.scratch/m0-m1/evidence/coverage-final.json` | 126 passed / 1 skipped；退出 0；行 90.64%、分支 80.45%、综合 88.50%；关键安全分支 90% 目标待补 |
| 上游受影响门 | `.venv/Scripts/python.exe scripts/mavis_tests.py --name upstream-affected-final tests/test_architecture.py tests/test_config_schema.py tests/test_feature_modules_gating.py tests/test_overlay_instance_gate.py tests/test_hotkeys.py tests/test_runtime.py tests/test_application_icon.py -q --tb=short` | 259 passed，退出 0；`upstream-affected-final.txt` |
| 原生 Mavis | `.venv/Scripts/python.exe scripts/mavis_ui_smoke.py --scale 1.5 --profile-label '中文 路径 '` | 退出 0，审批/记录/停止/隐藏/恢复/退出；`mavis-native-150-final.txt` |
| 全量上游 | `.venv/Scripts/python.exe scripts/mavis_tests.py --name upstream-qt612-final --timeout 1500 tests --ignore=tests/mavis -q --tb=short` | 未通过，fatal abort 后超时 124；完整原始日志保留 |
| 增量 lint | `.venv/Scripts/python.exe -m ruff check assistant tests/mavis scripts/mavis*.py pet/app.py pet/config.py pet/feature_activation.py` | 退出 0；`ruff-incremental.txt` |
| 全仓 lint | `.venv/Scripts/python.exe -m ruff check pet tests assistant scripts/mavis*.py` | 退出 1，未修改的 window.py 中 4 条 F811；`ruff.txt` |

## 需求映射

| 需求 | 本轮位置 | 验证 / 后续 |
|---|---|---|
| F-01/15/18 桌宠、状态、控制中心 | 原 pet 核心 + `pet_bridge.py/ui.py` | Qt 原生样本、bridge/UI 回归；AC-31 系统 DPI 完整矩阵待验证 |
| F-03/19 凭据、隐私 | `credentials.py/privacy.py`、凭据/许可探针 | AC-28 源码/最小冻结探针；真实 Provider M2 |
| F-04/05/16 语音 | `mavis_voice_spike.py`、本地固定模型清单 | M0 可行性；AC-04–09 / 完整语音 M3 |
| F-07/13/20 任务与控制 | `contracts.py/service.py/ipc.py/stop.py/controller.py` | AC-17/20/27/29 的 M1 控制器范围；真实 OS 会话与输入 M2/M5 |
| F-08/09/10/11/12 工具与权限 | `actions.py/policy.py/gateway.py`、Windows-Use 审计 | AC-13–16/22/29 的 schema/fixture 范围；B01–B30 尚未执行 |
| F-14 验证 | `Verification`、`TaskService.finish`、FixtureBackend oracle | AC-24 假成功负向测试；真实目标 oracle M2 |
| F-17/19/22 记录、诊断 | `storage.py/ui.py`、各验证脚本 | AC-25/27/34 的 M1 范围；完整过滤/导出/保留 M4/M5 |
| F-02/06 首次引导、备用入口 | M1 明确未就绪状态与文字记录 | 正式首次引导/录音入口 M3/M4 |
| F-21 独立安装 | 复用原 packaging；最小凭据冻结探针 | 完整安装包/干净机/升级 M6，未验证 |

## 本轮结束边界

未执行任意模型 shell、真实文件删除/覆盖、管理员窗口控制、外部发布或上传；没有 API Key 写入配置、数据库、日志或源码。仅对自己的测试 credential、fixture、worker、临时数据进行验证。

进入 M2：先收敛底座原生运行/全量 Qt 问题，补物理急停与原生会话/焦点防护，再做固定应用的只读观察→单个输入原语→独立后置验证。API Key 连接、语音首版和素材/模型许可不能被本轮 fixture 通过替代。
