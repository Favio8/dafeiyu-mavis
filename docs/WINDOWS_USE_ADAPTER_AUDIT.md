# Windows-Use 逐动作接入审计

2026-11-02，M0/M1 范围。关联 [上游基线](UPSTREAM_BASELINE.md)、[工具契约](TOOL_CONTRACTS.md)。

## 两个独立来源

- GitHub 公开仓库现为 [Jeomon/Windows-Use](https://github.com/Jeomon/Windows-Use)，CursorTouch URL 重定向到此。读取的 main SHA：`1be0c217cd3fd229fe62b0578fe323f39526f888`，pyproject 声明 0.8.1。
- 实际运行检查使用 PyPI **windows-use==0.8.1**。wheel 与该 main 不是逐文件相同，不能把它们混写成同一源码基线。审计环境锁文件保留 wheel 哈希。
- wheel `agent/desktop/service.py` SHA-256：`34cf64f127e8f227945f190c96a97c743a88da16abc640cb803bf9b2f0857aca`；完整文件哈希/实际方法表见 `.scratch/m0-m1/evidence/windows-use-audit.json`。

## 真实接口与危险路径

| 实际接口 | 行为 / 隐式动作 | 接入决定 |
|---|---|---|
| `windows_use.agent.desktop.service.Desktop.get_state` | 枚举窗口、UIA tree，可按配置截屏；读取当前虚拟桌面 | M2 只考虑限定目标的观察适配，不直接全桌面上下文上传 |
| `Desktop.warm_up` | 并发预热系统版本、语言、用户类型，内部触发 PowerShell | 禁止进入主链路 |
| `Desktop.execute_command` | `subprocess.run(['powershell','-NoProfile','-EncodedCommand',...])`，工作目录为用户 home | 永不开放 |
| `get_apps_from_start_menu/get_default_language/get_windows_version/get_user_account_type/launch_app` | 都会调用 `execute_command` | 用固定 Win32/注册应用查询替代；不能只删 `shell_tool` 就认为安全 |
| `Desktop.click(loc, button='left', clicks=2)` | 可能多次点击；坐标默认没有任务/窗口授权绑定 | 拆成受控单次原语，M1 未启用 |
| `Desktop.type(loc,text,caret_position,clear,press_enter)` | 点击 → Home/End → 可选 Ctrl+A/Back → SendKeys → 可选 Enter | 不能把整个方法当作一次安全动作；每个输入原语需要独立许可 |
| `Desktop.scroll` | 可先移动鼠标，再派发 wheel | 移动和滚动分别校验 |
| `shortcut` | 将字符串拼成 SendKeys，支持危险系统快捷键 | 只允许本地固定枚举；Win+R、终端、Enter 等不放行 |
| `multi_select/multi_edit/drag/move` | 内部循环/按住 Ctrl/拖拽；没有本项目取消令牌和逐动作边界 | 首版不直接开放批量方法，需独立释放按键和分块适配 |
| `app/switch_app/resize_app/bring_window_to_top` | 找窗口、切焦点、移动/调整；部分路径可启动应用 | 用已识别的 HWND/PID 和当前完整性级别绑定，不能凭模糊名称执行 |
| `Desktop.scrape` | UIA 之外可 `requests.get(url)` 获取网页 | 禁止未经域名/网络授权的隐式下载路径 |
| `agent/tools/service.py::shell_tool/file_tool/memory_tool/desktop_tool` | shell、覆盖/删除/复制/移动文件、记忆文件、虚拟桌面变更 | 不注册到 Mavis |
| `windows_use.tools.service.Tool.invoke/ainvoke` | 调用封装函数；本身不提供 Mavis 一次性许可 | 不当权限边界 |
| `windows_use.agent.service.Agent` 的 loop/aloop | 自行规划、调用工具、持有广泛能力 | 不实例化、不调用完整 Agent |

## 实际拦截验证

运行 `scripts/mavis_audit_windows_use.py`：

1. 从已安装 wheel 读取 AST 和 SHA，不猜类名/API。
2. 提取实际 `Desktop.type` 方法体，给它注入完全无副作用的 UIA 替身。第一次 Click 被记录；第二个 SendKeys 因缺少下一次许可而抛出异常。真实轨迹为 `['Click','SendKeys']`，后续 Enter 未发生。
3. Mavis gateway 测试另外验证批准前零计数器变化、一次消费、参数变更、旧 generation、焦点变化、权限撤销、DB 故障、急停均阻断。
4. 在真实 Windows 上导入经过防护的 package，构造 `Desktop(use_vision=False)`，用 `uia.ControlFromHandle` 只读取审计程序自己的 Qt 窗口；PID 与标题均符合。

第 2 步是**原方法体 + 惰性替身原语的边界实验**，不是实际键鼠注入验证。M1 中所有真实动作最终都被 `REAL_BACKEND_NOT_CONNECTED` 拒绝；只有显式测试模式的 `fixture.increment` 可执行。

## 遥测与隐式联网

`windows_use.telemetry.service.ProductTelemetry` 默认读取 `ANONYMIZED_TELEMETRY`，默认为 True；PostHog 地址为 `https://us.i.posthog.com`。审计在导入前设为 `false`，实测 `capture/flush` 未构造客户端、未创建 telemetry user ID。

**关闭这个开关不等于整包离线。** 顶层 `windows_use/__init__.py` 导入 Agent，继而导入所有 providers。实测 LiteLLM 尝试读取 GitHub 上的 model cost map。审计钩子捕获并拒绝了 3 次 DNS 尝试和 3 次 subprocess 创建尝试；完整日志保留。这些请求未执行成功，但足以否定“只设遥测变量就不会联网”的假设。

审计关闭 dotenv 自动发现，避免扫描无关 `.env`；Python audit hook 在导入前拒绝 `socket.connect/getaddrinfo`、`subprocess.Popen/os.system`。这验证 Python 进程中的尝试，不是 OS 级全进程抓包，也不是恶意代码沙箱。

## M2 最小接入条件

先在固定 wheel 的小范围源代码基础上维护最小适配/补丁：避开顶层 import 的 SDK 副作用；限定 UIA 观察；单次 click、单块文本、单个 shortcut 各自进入 Host gateway。每步重取 HWND/PID/完整性/焦点/控件语义；新动作再取得许可；finally 只释放本进程按下的键。真实输入前还需物理急停、锁屏、焦点干扰和权限撤销实机门禁。

M1 没有宣称完成这个真实执行器。没有运行 PowerShell 工具、任意命令、文件工具、远程通信或管理员窗口操作。
