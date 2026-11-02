# ADR-001：M0/M1 兼容性与隔离

日期：2026-11-02。状态：实施中、发布门禁未通过。补充 [上游基线](../UPSTREAM_BASELINE.md)、[上游开发约束](../DEV-HANDOVER.md)。

1. 保留 Python 3.11 x64、PySide6 和原 `pet/`。不引入 Electron/WebView/第二套桌宠渲染。新助手为独立包，用上游 AppShell、托盘、气泡、设置控件和单实例门。
2. PySide6 从候选 6.10.2 改锁 6.12.0：前者原聊天主题用例原生崩溃可单独复现，后者同文件 20 项通过且原生窗口可运行。完整共享 QApplication 套件仍 abort，不能按局部通过宣告解决全部生命周期问题。
3. sherpa-onnx 锁 1.12.26；官方 tokenizer 实际还需 sentencepiece/pypinyin。KWS/ASR 权重独立下载、测哈希，来源和许可证不与引擎混同。
4. Windows-Use 0.8.1 仅安装到审计环境。解析出的 mistralai 3.7.0 不可导入其需要的 Mistral API，锁到 1.9.11 实测成功；完整依赖远超执行所需。关闭遥测仍不能阻止 LiteLLM 导入联网，所以生产包禁止顶层 import/Agent.invoke，M2 维护最小受控适配。
5. M1 中唯一可执行工具是显式 test 模式的内存计数器，真实目标始终未就绪。测试记录与正式库分开，语音仍是 v0.1 必交付项，不以文字调试替代。
6. 沿用上游匿名/本机隔离思路但不复活已退役的多宠 IPC 层：助手 worker 用继承的匿名 stdio JSON 管道，只回收自有进程句柄，不接触用户应用进程。
7. 不覆盖用户原始 README/空 AGENTS/产品文档。上游规范另存快照；因根 AGENTS 空白造成的文档规范测试差异单独披露，不改测试断言掩盖它。

进入 M2 前仍须解决/明确接受 [KNOWN_LIMITATIONS](../KNOWN_LIMITATIONS.md) 中的原生运行与安全门禁。此 ADR 不是发行许可或正式发布批准。
