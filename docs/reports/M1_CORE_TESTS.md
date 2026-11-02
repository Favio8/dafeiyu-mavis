# M1 核心与安全测试报告

2026-11-02；关联 [架构](../ARCHITECTURE.md)、[状态](../IMPLEMENTATION_STATUS.md)。最终命令、覆盖率与新增文件见 [交付报告](../PR-REPORT-MAVIS-M0-M1-2026-11-02.md)。

## 验证范围

- 严格契约、非法参数/预算、未知 usage 为 null、终态不可复活、各活动状态取消、暂停确认/新观察、单活动任务。
- WAL/外键/唯一索引、提交后发布、事务回滚、锁竞争/磁盘错误关闭派发、崩溃恢复不重放、旧库备份拒绝、终态保留清理、脱敏。
- R0/R1/R2/RU 本地边界、HTTPS 规范化、精确域名、终端/运行框/危险快捷键、自操作、高完整性窗口、路径逃逸/设备名/覆盖拒绝。
- 仅本机 UI 决定审批、参数绑定、过期、一次性使用、取消/焦点/权限撤销、tool ok 不等于 goal passed。
- 真实匿名管道 worker 往返、非法消息/seq/nonce 拒绝、崩溃检测、20 次挂起 worker 急停；Windows RegisterHotKey 真注册/冲突及 WM_HOTKEY 分派。
- 真实 Qt 事件循环和 Controller 线程：审批/拒绝、历史、忙碌时第二指令、暂停不重放、停止、关闭隐藏、退出先停止；桌宠状态槽在 GUI 线程。

## 真实证据

红→绿：`core-red.txt`（模块尚不存在，退出 2）→后续核心通过；`namespace-red.txt`（旧目录被错误迁入）→`namespace-green.txt`（2 passed）。

中间完整新增套件：`m1-ui-coverage.txt` 为 120 passed / 1 skipped / 86%；`m1-final.txt` 为 122 passed / 1 skipped / 86%；`m1-regression-final.txt` 为 123 passed / 1 skipped（这几次为行覆盖口径）。最终 **`m1-complete.txt`：126 passed / 1 skipped，退出 0，36.71 秒**。`coverage-final.json`：行覆盖 **90.64%**、分支覆盖 **80.45%**、综合 **88.50%**；关键许可/停止模块的分支目标尚未全部达到 90%，不能按行覆盖或四舍五入数字宣称达标。

独立性能探针（不是 Computer Use benchmark）：100 个内存 fixture 任务，P95 817.21 ms（包含多次 FULL SQLite 提交）；RSS 34.16→37.95 MiB。20 次挂起 worker 的 StopController 终止最大 11.06 ms；全部原始样本在 `core-probe.json`。测试期间有并行本地验证负载，这不是稳态或 UI P95。子进程真实 PID 的退出另外由最终 IPC 回归确认，不能只依赖启动器进程返回。

原生 UI：修复退出后 `mavis-1-97e3b640/result.json`：停止链 3.22 ms，取消可见 125 ms，正常退出；`mavis-1.5-73d42e2e/result.json`：停止链 5.20 ms，取消可见 187 ms，中文/空格数据目录、Qt 1.5 倍缩放、审批/记录/恢复/退出通过。交互是 Qt 自己按钮的 `.click()`，并非真实系统鼠标注入。截图只包含本应用内容。

## 调查并修复的退出问题

旧原生 smoke 中的 3.4 秒/86 秒取消显示和超时记录仍保留。SQLite 证据显示任务其实在约 0.6 秒内已经取消；真正的问题是 hide-on-close 控制中心否决了 QApplication 的 Quit，`aboutToQuit` 清理尚未得到执行。探针在等待退出时又重复执行最后阶段，覆盖了早先计时。

修复包含两部分：PetBridge 在应用 Quit event 上先撤销任务/收尾，再允许窗口关闭；探针在请求退出前停止自己的 timer，禁止重入覆盖计时。另将桌宠状态桥明确为 queued Slot。修复后原生 smoke 正常退出，回归覆盖隐藏与退出的不同语义。

## 仍未验证

真实键鼠输入/按键释放、锁屏/休眠/焦点抢占保护、物理热键延迟、API Key 连通、麦克风、真实 GUI 目标、完整发行包。符号链接实机用例因本账户无创建权限跳过；本阶段不得启用真实执行器。原始上游全量和 lint 失败见 [M0 报告](M0_BASELINE_RUN.md)。
