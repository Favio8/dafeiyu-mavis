# Mavis M0/M1 交付报告

2026-11-02，`codex/m0-m1`，上游 `34d810b1eadd98d00e7cb9b3b51428a45b5bf03e`。没有提交或推送；范围仅 M0 基线与安全 M1。[完整状态](IMPLEMENTATION_STATUS.md)、[架构](ARCHITECTURE.md)、[复现入口](SETUP_WINDOWS.md)。

## 修改文件说明

逐文件目的、增删行数及 SHA-256 见 [CHANGE_MANIFEST.md](CHANGE_MANIFEST.md)。核心新增 `assistant/`，原有渲染、资源、窗口交互保持原文件；仅在 `pet/app.py` 增加装配/清理边界、`pet/config.py` 增加独立目录与禁止旧数据迁移、`feature_activation.py` 收紧 Mavis 可选能力。

根 AGENTS、README、两份产品文档的原始字节保留。相对上游的 AGENTS/README 大差异是导入时保留的用户文件，不是本轮删除。所有 `.venv*`、模型、原始日志、截图、测试 DB 和构建产物均被忽略，不进入提交。

## 性能分析

测试硬件：i7-10700F / 16 逻辑核 / 15.91 GiB / Windows 11 build 26200。以下只有实测样本，不代表发布预算达标。

- 独立核心：100 个 fixture 完整任务（含多次 FULL SQLite 提交）P95 **817.21 ms**；RSS **34.16→37.95 MiB**。完整样本 `core-probe.json`。有并行本地验证负载，不是空闲或长时趋势。
- 20 次挂起 worker 急停：StopController 置闩锁并终止自有启动进程的最大样本 **11.06 ms**；真实 worker PID 退出在后续 IPC 回归逐次检查。不是“物理按键至最后一条真实输入”的测量。
- 修复后原生窗口：100% 样本取消显示 **125 ms** / 停止处理 **3.22 ms**；Qt 1.5 倍中文路径样本 **187 ms / 5.20 ms**。短样本 RSS **195.79 / 216.61 MiB**，运行总时长 **5.72 / 4.89 s**；不同样本不能作 P95。
- 新常驻工作：一个 Controller 线程、一个独立热键消息线程；GUI stop 观察 timer 100 ms、托盘重建检测 timer 500 ms；无任务时没有 Agent/语音 worker，没有 LLM 网络请求或麦克风流。SQLite 只在命令/状态变化写入，记录查询在 Controller 线程。
- 有任务测试路径增加一个私有 worker 和读管道线程；结束后回收，截图只在验证脚本显式请求时生成。没有 8 小时稳定性/句柄增长结论。原生负载首帧失败仍保留，不降低动画标准来掩盖。

## 实机运行记录

见 [M0_BASELINE_RUN](reports/M0_BASELINE_RUN.md)、[M1_CORE_TESTS](reports/M1_CORE_TESTS.md)。确认过原生 Qt 窗口、托盘、可见角色/不同动画帧、控制中心审批/记录/停止/恢复/退出、自己的 UIA 窗口、实际本地 KWS/ASR/TTS、源码/冻结 WinVaultKeyring。

真实 Computer Use、模型 API、麦克风、锁屏/焦点干扰、真实按键释放、系统 DPI 矩阵、安装版均未验。界面测试按钮来自本进程 Qt 调用，测试数据显式标记，不能算真实 Windows Agent 任务。

## 测试与验证

完整关键命令及失败索引见 [COMMAND_LOG](reports/COMMAND_LOG.md)。

- 新增最终套件 **126 passed / 1 skipped，退出 0**：`.scratch/m0-m1/evidence/m1-complete.txt`。`coverage-final.json`：行 90.64%、分支 80.45%、综合 88.50%；关键安全分支 90% 目标尚未全满足。测试包含实际管道与子进程、Windows 热键注册/冲突、真实 Qt 事件循环、故障注入；符号链接权限用例明确跳过。
- 上游受影响子集 **259 passed**；原上游全量仍 fatal abort/超时。原聊天主题单文件 6.12.0 下 **20 passed**，这不等于全量通过。
- 增量 ruff 通过；全仓保留 4 条上游 F811。`git diff --check` 通过。没有改上游断言、skip 或预算。
- 文档纪律完整文件：230 passed / 1 failed；唯一失败为用户原始空 AGENTS 未含上游证据规范，文件保持原样。新增报告的章节与索引检查通过。
- 红→绿包括核心缺失、旧配置误迁入；native 退出失败已定位并修复，原始超时日志保留。见 M1 报告对错误计时探针的说明。

## 风险与后续

详细限制见 [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md)。没有启用真实输入，因此未知原生窗口语义、过期观察或不完整急停验收都不会触发 Windows 操作。先完成底座和安全前置，再进入 M2；语音仍是首版必需。回退只需不运行 `assistant` 入口；原 `python -m pet` 路径保留，Mavis 数据与上游数据分开，不自动迁移或删除。
