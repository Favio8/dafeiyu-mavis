# Mavis M2 受控原生路径交付记录（未完成全部 DEV-015～023）

2026-11-02，当前工作分支 `codex/m0-m1`，未提交或推送。详见 [M2实机报告](reports/M2_DESKTOP_E2E.md)、[最新状态](IMPLEMENTATION_STATUS.md)、[ADR-002](adr/002-m2-controlled-pilot.md)。

## 修改文件说明

| 文件 | 本轮职责与目的 |
|---|---|
| `assistant/provider.py`, `model_diagnostics.py` | 有界 DeepSeek HTTP、取消/重试/不跟重定向、严格响应与真实 usage；认证与工具能力分开 |
| `assistant/runtime.py` | 同一 TaskService/网关上的工具循环与审批续接；模型不能提供权限、task/generation 或成功 verdict |
| `assistant/windows_observer.py` | 只读窗口/完整性观察、跨进程 session mutex、上下文监视 |
| `assistant/system_backend.py` | 固定注册 Notepad 的 L1 启动；无任意执行路径/命令 |
| `assistant/notepad_backend.py` | 受限原生 GUI 焦点、单 Unicode 字符输入、期望前缀和停止检查 |
| `assistant/native_tasks.py` | 将确定性受限命令接回现有 Controller；保留本次新建草稿的内存身份 |
| `assistant/verifier.py`, `visual_gate.py` | 独立后置判断；视觉只实现拒绝门，尚无视觉执行器 |
| `assistant/actions.py`, `policy.py`, `gateway.py` | 增加精确焦点 schema、区分注册应用启动与控件自操作，保留真实执行器闭合白名单 |
| `assistant/controller.py`, `ui.py`, `pet_bridge.py` | 模型探针/本地运行期授权/受限文本入口；中间状态持续显示；入口占位防暗中排队；启动期取消修复 |
| `assistant/stop.py`, `privacy.py` | 当前应用热键事件链确认；敏感中文指令在落库前脱敏 |
| `scripts/mavis_model.py`, `mavis_windows_probe.py`, `mavis_system_probe.py` | 安全凭据输入、真实模型与只读系统/L1验证 |
| `scripts/mavis_physical_stop.py`, `mavis_gui_probe.py`, `mavis_gui_start.py` | 用户物理热键、独立 GUI 操作与 oracle，失败尝试保留，人工起点标明 |
| `tests/mavis/test_provider.py`, `test_runtime.py`, `test_observation_verifier.py` | 网络错误/取消、工具 schema、假成功、lease/观察/视觉拒绝门 |
| `tests/mavis/test_native_input_guard.py`, `test_native_tasks.py`, `test_controller_m2.py`, `test_privacy_m2.py` | 原生输入前拒绝、partial send释放、控制器接线/互斥/取消、凭据与任务隐私 |
| `tests/mavis/test_ui.py` | 新实时状态发布下等待明确的就绪/终态，保持原有成功和取消断言 |
| `requirements-mavis.in` 和两份 lock | 将实际直接使用的 aiohttp/comtypes 显式固定，使用原锁作约束，避免顺带升级 |
| M2报告、ADR、INDEX及旧状态文档 | 标清当前能力、历史快照、实际命令和未完成工作 |

累计相对上游的行数/文件清单见 [CHANGE_MANIFEST](CHANGE_MANIFEST.md)。上轮快照单独保留在 `.scratch/m2/evidence/m0-manifest.json`，不能把两轮累计增量都算作本轮新写。原用户 AGENTS/README/产品文档不改。

## 性能分析

- 同一 Windows 11 机器，真实物理热键事件处理到专用挂起 worker 退出：**2.0525 ms**，1个通过样本。前两次用户未及时按键不计通过；不声称已做20次真实输入急停。
- 真实 GUI：11个网关动作完成窗口/编辑区焦点及9字符输入，每字有 UIA 读回；没有用固定等待冒充效果，没有整体任务成功率或长期 P95 结论。
- 新路径成本：API请求才创建 aiohttp session；无后台模型轮询。native task 才持有 session mutex 和原生观察；输入期间 watcher 50ms间隔，任务结束关闭。无屏幕/音频默认采集上传。
- Controller 独立于 Qt 主线程；原生 UIA 暂在 Controller 线程，故障隔离仍不完整。M2前后没有完整空闲CPU、8小时内存/句柄测量，不能声称性能达标。
- 回归实际耗时：完整新增套件 **164 passed / 1 skipped，75.56s**；收尾隐私/凭据/native task **7 passed，7.47s**。这些测试时间不是产品 UI 延迟。

## 实机运行记录

`deepseek-connection.txt`、`deepseek-tools.txt` 为真实 `deepseek-flash` 响应指标；Key只在Windows凭据库。`windows-observer.json` 验证本进程窗口和跨进程租约。`system-08990c0a` 验证真实启动后窗口0→1。`gui-5554b197` 验证真实SendInput后的UIA内容，Task最终SUCCEEDED。

失败记录与人工操作口径全部列在 [M2报告](reports/M2_DESKTOP_E2E.md)。成功 GUI 样本由用户在本机窗口点击开始，并非无人干预基准。没有保存文件、接管管理员窗口、执行模型 shell 或操作用户已有文档。

模型/权限页原生 Qt 截图已检查：`.scratch/m2/evidence/ui/model-1040.png`、`permissions-720.png`。这是仅审查本应用窗口的预览，未注册热键的状态也明确显示；不拿预览截图冒充真实操作验收。

## 测试与未完成项

源代码 lint、compileall、diff whitespace检查通过。完整新增套件行覆盖80.54%、分支66.58%、综合77.22%；未达到全部安全覆盖要求。原有全量Qt失败未改成通过，也未再次重复耗时跑已定位的同一原生崩溃。

文档规范检查：232 passed / 1 failed；唯一失败仍是保留的用户空 AGENTS，未篡改该文件或测试。项目源码、脚本、文档与本轮证据的实际凭据值扫描匹配数为0；只记录计数，不输出凭据。

完整Windows-Use适配/原生worker、浏览器与B站、资源管理器/授权目录、真实GUI保存的一次性审批、视觉执行、完整文字→模型→GUI，以及更广安全/异常矩阵仍未完成。不能将此记录解释成完成全部 M2。下一步优先原生调用隔离与会话/用户输入保护，再逐项扩大工具范围。
