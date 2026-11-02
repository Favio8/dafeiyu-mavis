# ADR-002：M2 受限原生试验与渐进接入

2026-11-02，开发中。关联 [ADR-001](001-mavis-m0-baseline.md)、[M2 报告](../reports/M2_DESKTOP_E2E.md)。

M1 的纯控制核心已通过测试，但原生安全和底座完整 Gate 未全通过。本轮先扩充独立可测的模型协议、Windows 身份观察与 session lease，再按系统动作→真实 GUI 的顺序做专用受限实验，不把整个 Windows-Use package/Agent 的广泛能力带进产品。

原生 GUI pilot 采用 Win32 + Windows UI Automation COM，COM activation seam 已核对 Windows-Use `uia/core.py` 的真实实现。没有声称完成 Windows-Use 全部工具适配；其完整导入的遥测之外联网与隐式命令路径继续排除。renderer、动画、原窗口交互均沿用上游。

试验范围固定为 Notepad 新空白草稿，最多16个单行 BMP 字符；每个字符单独许可，Unicode down/up 在一次 SendInput 中派发。没有剪贴板、任意快捷键、拖动、文件保存、浏览器表单提交和视觉点击。只能由本机明确操作授权开启，且先完成当前应用 hotkey 事件链测试；默认关闭。

模型网络调用使用已锁定 aiohttp，绕开 SDK 导入副作用。配置只接受官方 DeepSeek HTTPS origin；Key 独立存 WinVault。连接和工具能力独立测试，不自动推定视觉能力，不静默上传屏幕/页面内容。

物理热键验证记录不是动作许可。诊断脚本可检查当前系统启动周期内的真实记录；每次运行仍重新注册热键并持有新 lease。真正 Permit 仍短时、单次、绑定任务/代数/参数/当前观察，不读取历史 grant 来执行。

完整会话通知、用户输入钩子、原生执行 worker、通用 GUI、R1 保存和视觉执行尚未完成。因此维持实验范围，不把本 ADR 当作 M2/发布验收完成。
