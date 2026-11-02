# M2 受控实机推进报告（尚未通过完整 M2 Gate）

2026-11-02，Windows 11 build 26200 / Python3.11.14 / PySide6 6.12.0，普通权限。关联 [实施状态](../IMPLEMENTATION_STATUS.md)、[M2 决策](../adr/002-m2-controlled-pilot.md)、[M0/M1 历史报告](M1_CORE_TESTS.md)。原始证据保存在 `.scratch/m2/evidence/`，新增 pytest 输出沿用 `.scratch/m0-m1/evidence/`。

本轮**没有完成 DEV-015～023 的全部验收项**。完成了真实模型探针、受限系统启动、真实记事本 GUI 输入及相应安全基础；网页、真实保存审批、完整 Windows-Use 适配和视觉执行仍未交付。不能称为 M2 全部通过。

## 已验证的实际行为

| 顺序 | 行为 | 真实结果 | 证据 |
|---|---|---|---|
| 1 | 安全配置凭据 | 本机隐藏输入，只写 Windows Credential Manager；未放入 argv、配置、DB 或源码 | `scripts/mavis_model.py --save-key`；本报告不记录凭据值 |
| 2 | deepseek-flash 真实连接 | passed；input_tokens=10 / output_tokens=2 | `deepseek-connection.txt` |
| 3 | 真实函数调用能力 | forced `probe_echo`，结构和 marker 正确；input_tokens=293 / output_tokens=36；不执行系统动作 | `deepseek-tools.txt` |
| 4 | Windows 原生观察/互斥 | 自有 Qt 窗口识别、medium、96 DPI；第二进程不能抢租约，释放后可取得 | `windows-observer.json`、`windows-observer-fixed.txt` |
| 5 | L1 启动记事本 | 权限网关派发 1 次，窗口数 0→1，独立窗口后置检查通过，SUCCEEDED | `system-08990c0a/result.json`、其中的 SQLite/event 轨迹 |
| 6 | 用户物理急停 | 第三次用户按键被收到，自有挂起 worker 退出；handler 2.0525 ms；未合成按键 | `physical-stop-1793616662925478300.json` |
| 7 | 真正 GUI 输入 | 在已确认空白的测试记事本中，经 11 个独立许可动作（窗口/编辑区焦点 + 9 个字符）输入“你好，我是大肥鱼。”；逐字 UIA 读回及最终比较通过 | `gui-5554b197/result.json`、`state.db`、`gui-user-start-second.txt` |

第 7 项使用 **Windows SendInput Unicode**，没有 QTest 写编辑器、UIA SetValue、直接写文件或脚本修改页面状态。原始报告中的 `synthetic_input=true` 指 Windows 注入的键盘事件，**不是返回预设成功的模拟后端**；新脚本已改用明确的 `real_gui_input/input_method` 字段。

GUI 验收存在人工准备：用户点击本机“开始”按钮，让 Windows 有明确的前台操作来源。此样本不计作无人干预 benchmark。脚本仅复用此前自己打开、在 SQLite 中记录了 HWND/PID 的测试窗口；重新创建 Task、重新观察、重新签发许可，没有重放历史坐标或审批。未执行另存为/保存文件，未检查 Notepad 自身的自动恢复缓存。

## 失败记录和修正

- `windows-observer-run.txt`：第一次 Win32 token 读取错误地把 `(SID, attributes)` 当作 SID，实际检查后修正；重跑通过。
- 两次物理急停测试未完成，保留 `physical-stop.json` 和 `physical-stop-1793616489421205200.json`。用户说明看到了但未及时按键；不能当作通过或擅自认定热键坏了。
- `gui-565eed09`：编辑区焦点未确认，UNVERIFIED，未输入。
- `gui-04bddb64`：Windows 拒绝切前台，UNVERIFIED，未使用模拟 Alt 等方式规避。
- `gui-0ab1338c`：等候用户置前未完成，TIMED_OUT。
- `gui-user-start.txt`：测试脚本的 15 分钟物理验证记录期限提前拒绝。该期限不是动作许可要求，改为当前启动周期的验证记录；每次仍真实注册热键，每个动作仍使用新的限时、一次性许可。
- `m2-final-core.txt`：实时发布中间状态暴露了“worker 启动前取消”的竞争，以及旧 UI 测试过早断言终态。已改为可中断的 worker 就绪等待，补启动取消回归；测试等待可观察的终态/就绪条件，未放宽成功断言。

失败日志没有删除、覆盖为通过或从发布基准分母中静默排除。本轮没有运行完整 B01–B30 基准，不能计算发布成功率。

## 代码与控制中心

- `assistant/provider.py`：aiohttp、默认 deepseek-flash、TLS 官方域名、禁止重定向、响应大小/总时限、可取消请求、有限 429/5xx 重试、稳定错误码、真实 nullable usage。参考 [DeepSeek Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。只支持官方 origin 的根路径或 `/v1`，不是任意兼容端点管理器。
- `assistant/runtime.py`：复用同一 TaskService/ToolGateway，Host 注入 task/generation/tool_call ID，单步工具提案、本地审批、轮数与无进展约束、独立最终验证。模型说完成不能置成功。通用模型任务循环尚未全面接入控制中心。
- `windows_observer.py`：特定窗口身份与完整性、输入桌面可读性、用户会话命名 mutex、独立上下文监视。无窗口标题/屏幕内容遍历上传。混合 DPI 和原生会话通知仍待补。
- `system_backend.py`：仅固定注册 Notepad；当前用 ShellExecuteEx 固定 exe/`open` verb，无 PowerShell/cmd/任意命令参数。
- `notepad_backend.py`：受限焦点/单 BMP 字符输入；唯一已登记草稿、空白/期望前缀、焦点、PID/HWND、完整性、lease、热键、观察时效和停止检查；partial SendInput 停止并尝试释放自身 Unicode key-up。
- `verifier.py`：窗口/UIA 文本/URL/文件哈希独立比较函数。实机只验过窗口与 UIA 文本，不能把另外两类函数当作已完成浏览器/文件端到端。
- `visual_gate.py`：只有授权/能力/低风险/上下文/裁剪范围的拒绝门，没有截图上传或坐标执行器。
- 控制中心新增分开的模型探针与仅本次运行的受限授权。默认关闭；应用内先按急停测试、复位，再授权。支持确切指令 `打开记事本`、`输入：<最多16个单行字符>`；仅后者操作本次助手新开的空白窗口。无法明确支持的请求失败关闭，不接管原有文档。
- 任务入口增加即刻占位，阻止耗时工作期间的第二条任务被静默排队；撤销授权直接置 stop latch，不等待 Controller 命令队列。

控制中心的受限路由已接线并有单元/Qt 回归；本次成功的真实 GUI 证据来自同一控制核心上的专用实机入口，不宣称已覆盖控制中心所有实机场景。

## 执行命令

工作目录为仓库根，PowerShell，普通权限。凭据绝不出现在命令参数。

```powershell
.venv/Scripts/python.exe scripts/mavis_model.py --save-key
.venv/Scripts/python.exe scripts/mavis_model.py --probe connection --model deepseek-flash
.venv/Scripts/python.exe scripts/mavis_model.py --probe tools --model deepseek-flash
.venv/Scripts/python.exe scripts/mavis_windows_probe.py
.venv/Scripts/python.exe scripts/mavis_system_probe.py
.venv/Scripts/python.exe scripts/mavis_physical_stop.py
.venv/Scripts/python.exe scripts/mavis_gui_probe.py
.venv/Scripts/python.exe scripts/mavis_gui_start.py --resume-test-window gui-565eed09
.venv/Scripts/python.exe scripts/mavis_tests.py --name m2-complete-regression tests/mavis -q --tb=short --cov=assistant --cov-branch --cov-report=term-missing --cov-report=json:.scratch/m2/evidence/coverage-final.json
```

上面的 `gui-565eed09` 是本轮实际原始测试窗口记录，不是可跨机器照搬的资源 ID。新环境先运行不带 resume 的探针，按其输出的本轮 run ID 进行独立重试；窗口已有内容时拒绝操作，不为复验清空用户文档。

新增回归：**164 passed / 1 skipped，退出 0，75.56 秒**。覆盖率：行 80.54%、分支 66.58%、综合 77.22%，不满足全部关键分支 90% 目标。随后单独隐私/凭据/native task 收尾 **7 passed，退出0**，见 `m2-privacy-final.txt`。新增/修改代码 ruff 与 diff whitespace 检查通过；文档规范232通过/1个原始空AGENTS失败。上游完整 Qt 套件的旧失败没有变成通过。

## 尚未完成与下一步

DEV-015～023 详情见 [实施状态](../IMPLEMENTATION_STATUS.md)。缺口包括完整工具层 Windows-Use 适配、可独立终止的原生 UIA/输入执行 worker、原生锁屏/休眠通知及用户输入干扰钩子、广泛动作/DPI矩阵、B站及浏览器 URL 独立验证、授权目录/资源管理器、真实 GUI 保存的一次性审批、受控视觉执行和完整 M2 文字闭环。

本轮没有以 Python 直接写文本文件替代 GUI 保存，没有把图片能力或打开 URL 伪装成 GUI 操作。下一步先把受限执行路径隔离进 owned worker、收敛原生安全边界，再扩展范围；不能直接将完整 Windows-Use Agent 接入已保存的用户凭据。
