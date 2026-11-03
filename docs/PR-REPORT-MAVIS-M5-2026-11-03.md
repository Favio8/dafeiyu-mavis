# Mavis M5 权限、急停、验证与隐私收口

基线 `90af76f`；分支 `codex/m5-safety`；日期2026-11-03。安全实现冻结于 `91b2947`，8小时测量使用该提交的独立worktree；后续审计入口及文档单独提交。

本轮将原生控制移入可独立终止的固定进程，补共享停止事件与进程/文档身份，严格绑定后置验证，修复脱敏与成功率统计。后续人工交接急停20/20、8小时限定工况正常结束；新增本机便携run.bat入口。**M5整体未通过**：覆盖率、权利和未覆盖场景仍列账。按用户要求转向开发/试用迭代，不重复已结束专项。详见 [完整报告](reports/M5_SAFETY_STABILITY.md)、[逐DEV状态](IMPLEMENTATION_STATUS.md#m5-最新状态)。

## 修改文件说明

相对M4基线的当前文件清单；+/-为实际git numstat，新文档为实际行数。`.scratch`中的原始证据、模型、音频、SQLite、凭据及测量worktree不提交。根AGENTS/README、产品文档和用户数据保持原样。

<!-- m5-files:start -->
| 文件 | + / - | 改动与目的 |
|---|---|---|
| [.gitignore](../.gitignore) | +1/-0 | 排除本机便携试用数据，避免配置/DB/音频和凭据引用入Git。 |
| [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | +10/-0 | 补充Mavis模型/FFmpeg核对及尚未确认的权利，不扩大授权。 |
| [assistant/__init__.py](../assistant/__init__.py) | +1/-1 | 标记M5开发版本，避免误认发布版。 |
| [assistant/__main__.py](../assistant/__main__.py) | +2/-2 | 更新实际入口说明，电脑控制仍需本机授权。 |
| [assistant/contracts.py](../assistant/contracts.py) | +2/-0 | 观察增加窗口/文档摘要，兼容旧记录。 |
| [assistant/controller.py](../assistant/controller.py) | +26/-9 | 连接诊断改为可终止私有进程，保留凭据缺失与停止结果。 |
| [assistant/diagnostics.py](../assistant/diagnostics.py) | +3/-0 | 只导出固定错误码，避免异常详情带出个人路径或秘密。 |
| [assistant/gateway.py](../assistant/gateway.py) | +2/-0 | 派发前重新检查任务预算，过期许可不能继续执行。 |
| [assistant/history_ui.py](../assistant/history_ui.py) | +5/-0 | 呈现真实成功率、完整分母和不一致标记。 |
| [assistant/ipc.py](../assistant/ipc.py) | +100/-13 | 实际worker句柄/退出核对；保留必要SYSTEMDRIVE，不继承模型Key。 |
| [assistant/model_probe_worker.py](../assistant/model_probe_worker.py) | +43/-0 | 隔离有限API诊断，只从固定凭据引用读Key。 |
| [assistant/native_event.py](../assistant/native_event.py) | +42/-0 | nonce绑定的Win32共享停止事件与父进程生存检查。 |
| [assistant/native_fixture.py](../assistant/native_fixture.py) | +30/-0 | 仅test-mode开放祖先/解释器/标题绑定的自有窗口。 |
| [assistant/native_input_monitor.py](../assistant/native_input_monitor.py) | +80/-0 | 原生键鼠观察及固定原因码，不记录原始输入内容。 |
| [assistant/native_session.py](../assistant/native_session.py) | +150/-0 | 逐许可有界RPC，独立停止和worker回收，保留撤权原因。 |
| [assistant/native_tasks.py](../assistant/native_tasks.py) | +43/-21 | 原流程复用独立native worker；清理后独立验证，不重放未知输入。 |
| [assistant/native_worker.py](../assistant/native_worker.py) | +178/-0 | 固定原生COM/UIA/派发进程；细分撤权原因，不改授权策略。 |
| [assistant/notepad_backend.py](../assistant/notepad_backend.py) | +51/-13 | 绑定草稿/编辑区身份，精确读回、最后停止检查与输入标记。 |
| [assistant/policy.py](../assistant/policy.py) | +7/-0 | 敏感文本、内容与URL在派发前拒绝。 |
| [assistant/privacy.py](../assistant/privacy.py) | +1/-1 | 修复Key邻接中文时的脱敏缺口。 |
| [assistant/provider.py](../assistant/provider.py) | +6/-3 | 区分HTTP/连接/格式失败，有限重试仅覆盖可重试请求。 |
| [assistant/service.py](../assistant/service.py) | +5/-2 | 最终预算与Goal/Verification方法一致性，禁止假成功。 |
| [assistant/stop.py](../assistant/stop.py) | +23/-4 | 先通知所有共享事件，尝试终止所有自有进程并保留最慢延迟。 |
| [assistant/storage.py](../assistant/storage.py) | +6/-1 | 成功率由全部结束任务和独立验证结果统计。 |
| [assistant/verifier.py](../assistant/verifier.py) | +4/-0 | 加强目标窗口身份绑定。 |
| [assistant/voice_audio.py](../assistant/voice_audio.py) | +9/-0 | 无设备时先明确失败，不尝试打开不存在的输入源。 |
| [assistant/voice_host.py](../assistant/voice_host.py) | +2/-1 | 语音worker失败及会话锁定/休眠同时触发控制停止。 |
| [assistant/voice_worker.py](../assistant/voice_worker.py) | +2/-4 | 使用统一的输入设备选择检查。 |
| [assistant/windows_observer.py](../assistant/windows_observer.py) | +26/-2 | 进程出生/用户/类身份摘要，统一DPI坐标，拒绝其他用户窗口。 |
| [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) | +9/-1 | 记录已落地的原生隔离/停止架构，保留历史边界。 |
| [docs/CHANGE_MANIFEST.md](../docs/CHANGE_MANIFEST.md) | +2/-0 | 登记M5增量和逐文件审查入口。 |
| [docs/DATA_SCHEMA.md](../docs/DATA_SCHEMA.md) | +4/-0 | 说明摘要兼容与真实统计，不增加数据库版本。 |
| [docs/IMPLEMENTATION_STATUS.md](../docs/IMPLEMENTATION_STATUS.md) | +23/-1 | 逐项记录DEV-039～045实际状态和未过门禁。 |
| [docs/INDEX.md](../docs/INDEX.md) | +8/-2 | 登记新增报告、支持及许可入口。 |
| [docs/KNOWN_LIMITATIONS.md](../docs/KNOWN_LIMITATIONS.md) | +3/-1 | 补充最新已实现/未验证，保留原有失败。 |
| [docs/MAVIS_LICENSE_INVENTORY.md](../docs/MAVIS_LICENSE_INVENTORY.md) | +109/-0 | 按实际元数据收集依赖/模型/二进制许可与权利缺口。 |
| [docs/PR-REPORT-MAVIS-M5-2026-11-03.md](../docs/PR-REPORT-MAVIS-M5-2026-11-03.md) | +107/-0 | 本轮交付报告、逐文件说明及性能/实机证据入口。 |
| [docs/SETUP_WINDOWS.md](../docs/SETUP_WINDOWS.md) | +24/-1 | 给出安全、人工前台、资源与许可复验命令。 |
| [docs/SUPPORT_MATRIX.md](../docs/SUPPORT_MATRIX.md) | +22/-0 | 区分检测版本与已实测范围，不承诺未跑平台。 |
| [docs/TOOL_CONTRACTS.md](../docs/TOOL_CONTRACTS.md) | +2/-0 | 明确Host一次性许可到固定worker的真实工具范围。 |
| [docs/TRY_MAVIS.md](../docs/TRY_MAVIS.md) | +21/-0 | 提供可实际使用的启动、停止、能力边界与便携数据说明。 |
| [docs/reports/COMMAND_LOG.md](../docs/reports/COMMAND_LOG.md) | +39/-0 | 追加M5真实命令、退出状态和证据路径。 |
| [docs/reports/M5_SAFETY_STABILITY.md](../docs/reports/M5_SAFETY_STABILITY.md) | +104/-0 | 保留命令、真实结果、失败与当前8小时运行状态。 |
| [pet/window.py](../pet/window.py) | +5/-4 | 保留平台兼容别名，消除4项导入重定义F811。 |
| [run.bat](../run.bat) | +8/-3 | 固定项目venv与Mavis入口，显式便携数据目录，缺环境时提示。 |
| [scripts/mavis_history_benchmark.py](../scripts/mavis_history_benchmark.py) | +58/-0 | 构建真实隔离10k Task库并测分页过滤/统计P95。 |
| [scripts/mavis_m5_audit.py](../scripts/mavis_m5_audit.py) | +115/-0 | 凭据仅内存比对；收集实际许可/系统；逐项记录不可检查归档。 |
| [scripts/mavis_native_worker_probe.py](../scripts/mavis_native_worker_probe.py) | +54/-0 | 真实只读native worker/lease/钩子/停止链探针。 |
| [scripts/mavis_performance.py](../scripts/mavis_performance.py) | +243/-0 | 实际资源/8h记录；保留SYSTEMDRIVE供Windows组件使用。 |
| [scripts/mavis_stop_stress.py](../scripts/mavis_stop_stress.py) | +262/-0 | 一次START、真实首包后急停、逐动作结果检查及独立文本oracle。 |
| [scripts/mavis_upstream_checks.py](../scripts/mavis_upstream_checks.py) | +50/-0 | 完整相关上游模块隔离Qt生命周期并保留每个结果。 |
| [tests/fixtures/mavis/m5-negative-cases.json](../tests/fixtures/mavis/m5-negative-cases.json) | +52/-0 | 固定五类各10个安全负向样例，不删失败项。 |
| [tests/mavis/test_ipc.py](../tests/mavis/test_ipc.py) | +1/-0 | 要求实际worker退出，不能仅检查启动壳。 |
| [tests/mavis/test_m5_boundaries.py](../tests/mavis/test_m5_boundaries.py) | +121/-0 | 验证错误身份、尾部换行、错误方法、迟到结果、秘密、统计及无进展。 |
| [tests/mavis/test_m5_safety.py](../tests/mavis/test_m5_safety.py) | +256/-0 | 50项逐一检查效应陷阱、SQLite/文件oracle、共享停止和故障分支。 |
| [tests/mavis/test_native_tasks.py](../tests/mavis/test_native_tasks.py) | +5/-6 | OS边界替身适配NativeSession；业务状态仍真实运行。 |
| [tests/mavis/test_storage_state.py](../tests/mavis/test_storage_state.py) | +2/-2 | fixture验证目标使用正确predicate，不允许错误方法变成功。 |
<!-- m5-files:end -->

## 性能分析

实际环境为AMD64 build26200.9445，Python3.11.14，i7-10700F，8物理/16逻辑核，15.91GiB RAM；依赖与模型见 [支持矩阵](SUPPORT_MATRIX.md) 和 [许可清单](MAVIS_LICENSE_INVENTORY.md)。

- 10,000条真实test-mode拒绝任务，100次分页/过滤查询，完整新统计路径P95 147.63ms，门槛300ms。新统计与历史读取同频执行，不种入正式页面。证据 `.scratch/m5/history/1793639596481560200/`。
- 20秒core-only样本峰值179.57MiB、CPU均值0.183%；26秒完整桌宠+静音模型样本首像素2.625s、峰值600.95MiB、CPU9.70%。这是初始化短样本，CPU偏差保留，不当作10分钟稳态通过。UI心跳P95 140ms不是实测点击延迟。
- 冻结8小时实例600–1200秒的600样本：整机CPU均值4.238%，RSS最大580.30MiB，符合这个10分钟窗口的5%/650MiB门槛；首/末60样本句柄中位2831/2835，不推定8小时无增长。原始快照 `.scratch/m5/performance/partial-soak-91b2947-1200.json`。
- 共享事件、进程句柄、低级键鼠观察及上下文守卫引入Windows系统调用；每个活动原生会话增加独立worker/管道/监控线程，每个输入原语有请求和验证。不会为每个字符发网络请求；模型请求仍需现有云端授权。实际短样本不能单独估算这些新增路径的稳定净增成本。
- 测量器改为有界内存与JSONL落盘，未降低帧率或停动画。冻结91b2947实际28801.218s正常结束，28798样本；稳态CPU4.259%，稳态RSS最大581.28MiB、全程峰值624.69MiB。首末完整10min内存中位增长0.972%、句柄2831/2831、线程105/105，符合该合成静音工况阈值。样本仍可能遗漏极短连接及已退出子进程CPU，不能替代真人麦克风或任务场景。

可复现命令与完整原始路径见 [命令记录](reports/COMMAND_LOG.md#m5收尾2026-11-03) 和 [运行说明](SETUP_WINDOWS.md#m5-安全与资源复验)。8小时最终输出 `.scratch/m5/performance/soak-91b2947/result.json` 与 `analysis.json`；自然结束结果已保留。

## 实机运行记录

固定50条安全集在真实私有SQLite、文件及Windows junction上运行；未授权原生派发0。锁屏/磁盘满/网络挂起项目采用明确故障注入，不称已经物理锁屏或填满磁盘。50项fixture与上游测试输入均不混入正式任务记录。

真实Windows私有子窗口和UIA/SendInput路径保留了三批0/20、15/20、15/20急停结果。最后一批的5个长输入被FOCUS_CHANGED拒绝、没有实际输入包，不能算通过。随后人工START等待超时；这是当前需人工前台交接的排查证据。WM_HOTKEY消息不冒充物理按键。详见 [专项失败与下一步](reports/M5_SAFETY_STABILITY.md#急停保留失败不改20次门槛)。

后续用户配合已完成20/20：最长handler52.97ms，接收后新派发0ms，5次长输入均有实际包，所有worker退出且独立文本回读稳定。原重复START异常及一次2/20也留证。最新输出 `.scratch/m5/stop-stress/1793688459472448400/`；不是物理按键补证，不修改旧失败。

本机启动发现系统数据目录写档案报WinError17，便携run.bat显式使用项目内 `.mavis-local`，不迁移或覆盖原数据；实际启动日志载入106段动画、进入事件循环，Windows只读观察看到桌宠与控制中心。Key仍在Windows凭据库，私有数据Git排除。详见 [本机试用](TRY_MAVIS.md)。

原生只读worker建立过真实lease/钩子/私有停止事件并退出，观测停止8.25ms、handler3.59ms；它没有输入，不能代替20次最后派发证明。该早期探针时默认数据命名空间尚不存在，资源/安全测试使用隔离profile；后续实际启动及便携目录如上记录。真人麦克风仍无设备，合成静音不冒充实录。

## 测试与未过门禁

Mavis完整237 passed / 1 skipped；后续重点42 passed；固定50项加边界共60 passed。相关上游97模块均有完整单模块通过结果，首次application_icon的Git Bash路径失败保留；这不证明历史合并进程Qt abort已经解决。

覆盖行65.74%、分支46.95%、综合61.45%，低于总体80%/关键分支90%。未排除模块或修改阈值。native/voice子进程的实际运行也不自动算pytest-cov覆盖。没有构建或宣称验收本轮完整安装包。收尾静态/文档检查与未通过项见 [完整报告](reports/M5_SAFETY_STABILITY.md)。

## 风险与后续

20次受控专项已完成，物理键与更广泛设备/接管场景继续列账。现有Notepad授权默认关闭；通用浏览器/文件/视觉、M2全流程、M3真实设备、M4多DPI等范围仍未全部完成。Qt/FFmpeg/模型/角色分发权未全部闭合；本机试用不冒称全产品MIT或全部发布验收通过。

SQLite版本未变，新增Observation摘要默认空串兼容旧记录；Key引用仍指Windows凭据库。若回退代码，应先停止助手和自有worker，保留实际数据库/许可通知，不删除用户文件或凭据。冻结测量的源提交与结果继续保留，本轮不复跑完整回归与覆盖率。
