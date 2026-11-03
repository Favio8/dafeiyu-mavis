# Mavis 0.1.0 安装测试候选交付

基线bad431c；分支codex/m6-0.1.0；日期2026-11-03。用户授权推送GitHub，并在另一台完整测试环境继续验收。**总体发布Gate未通过**；源码、安装器、便携包与真实报告作为测试候选交付。

## 修改文件说明

相对M5基线的逐文件增删与目的如下。生成产物、用户数据、Key、模型、测试录音不入Git，用户既有未跟踪输入法目录保持原样。源码与打包快照分开记录，不将后续文档提交冒作已编译代码。

<!-- m6-files:start -->
| 文件 | + / - | 改动与目的 |
|---|---|---|
| [.gitignore](../.gitignore) | +1/-0 | 隔离Mavis分发和私有数据。 |
| [assistant/__init__.py](../assistant/__init__.py) | +1/-1 | 固定构建版本0.1.0，质量状态另表。 |
| [assistant/__main__.py](../assistant/__main__.py) | +2/-0 | 读取显式安装/便携数据位置。 |
| [assistant/assets/benchmark-cases.json](../assistant/assets/benchmark-cases.json) | +242/-0 | 完整B01至B30原始要求与固定90/72清单。 |
| [assistant/bundle_probe.py](../assistant/bundle_probe.py) | +195/-0 | 冻结安装版运行库/凭据/语音/固定云诊断/独立UIA只读探针。 |
| [assistant/distribution.py](../assistant/distribution.py) | +112/-0 | 闭合helper模式及安装数据位置；没有任意module/shell接口。 |
| [assistant/frozen_environment.py](../assistant/frozen_environment.py) | +30/-0 | 隔离外部注册应用的DLL搜索环境。 |
| [assistant/installed_security.py](../assistant/installed_security.py) | +36/-0 | 以安装模块执行原50断言，禁外部pytest插件与配置。 |
| [assistant/ipc.py](../assistant/ipc.py) | +6/-6 | 冻结时固定helper路由与真实进程身份。 |
| [assistant/native_fixture.py](../assistant/native_fixture.py) | +2/-1 | 诊断窗口对照实际冻结exe，维持祖先/标题约束。 |
| [assistant/release_benchmark.py](../assistant/release_benchmark.py) | +194/-0 | 实际Controller/网关基准，物理与本地授权不可绕过。 |
| [assistant/system_backend.py](../assistant/system_backend.py) | +4/-2 | 仅注册外部应用启动时恢复系统DLL环境。 |
| [assistant/upgrade.py](../assistant/upgrade.py) | +36/-0 | 新目录SQLite一致备份与有限配置快照。 |
| [docs/BUILD_MAVIS_WINDOWS.md](../docs/BUILD_MAVIS_WINDOWS.md) | +25/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/CHANGE_MANIFEST.md](../docs/CHANGE_MANIFEST.md) | +2/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/IMPLEMENTATION_STATUS.md](../docs/IMPLEMENTATION_STATUS.md) | +17/-1 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/INDEX.md](../docs/INDEX.md) | +6/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/KNOWN_LIMITATIONS.md](../docs/KNOWN_LIMITATIONS.md) | +2/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/MODEL_PACKS.md](../docs/MODEL_PACKS.md) | +31/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/PR-REPORT-MAVIS-M6-2026-11-03.md](../docs/PR-REPORT-MAVIS-M6-2026-11-03.md) | +78/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/RELEASE_GATE.md](../docs/RELEASE_GATE.md) | +24/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/TEST_ON_SECOND_PC.md](../docs/TEST_ON_SECOND_PC.md) | +47/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/USER_GUIDE.md](../docs/USER_GUIDE.md) | +33/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [docs/reports/RELEASE_VALIDATION.md](../docs/reports/RELEASE_VALIDATION.md) | +82/-0 | 记录实际实现/构建/交付结果及未测边界，互链对应证据。 |
| [packaging/bundled-audio.json](../packaging/bundled-audio.json) | +14/-0 | 精确上游合成WAV来源和SHA白名单。 |
| [packaging/licenses/FFMPEG_SOURCE.md](../packaging/licenses/FFMPEG_SOURCE.md) | +12/-0 | 实际编解码器许可与源码来源说明。 |
| [packaging/licenses/ffmpeg-COPYING.GPLv3](../packaging/licenses/ffmpeg-COPYING.GPLv3) | +674/-0 | 原样随包的GPLv3全文。 |
| [packaging/mavis-license.txt](../packaging/mavis-license.txt) | +19/-0 | 候选/独立许可边界，不扩大商用授权。 |
| [packaging/mavis-pytest.ini](../packaging/mavis-pytest.ini) | +3/-0 | 固定安装验收配置，排除外部项目干扰。 |
| [packaging/mavis.iss](../packaging/mavis.iss) | +111/-0 | 普通用户安装、数据选择、备份及保留卸载策略。 |
| [packaging/mavis.spec](../packaging/mavis.spec) | +41/-0 | 双exe和有界资源/依赖收集。 |
| [packaging/mavis_entry.py](../packaging/mavis_entry.py) | +20/-0 | UI/helper固定入口及上游设置分流。 |
| [packaging/windows-toolchain.json](../packaging/windows-toolchain.json) | +14/-0 | 官方编译器来源与组件SHA锁。 |
| [scripts/build_onedir.ps1](../scripts/build_onedir.ps1) | +8/-0 | 扩展mavis变体，保留其他上游路径。 |
| [scripts/mavis_benchmark.py](../scripts/mavis_benchmark.py) | +140/-0 | 目标为安装exe的驱动、真实HTML fixture和待测统计。 |
| [scripts/mavis_bundle_audit.py](../scripts/mavis_bundle_audit.py) | +81/-0 | 实际文件和PYZ内存凭据/个人路径比对，不导出秘密。 |
| [scripts/mavis_installed_lifecycle.py](../scripts/mavis_installed_lifecycle.py) | +73/-0 | 自有安装进程的可见窗口/单实例/正常退出oracle。 |
| [scripts/mavis_performance.py](../scripts/mavis_performance.py) | +11/-1 | 复用资源测量并支持冻结child和独立热键。 |
| [scripts/mavis_release.py](../scripts/mavis_release.py) | +235/-0 | 锁定构建、内容检查、安装/便携与SHA，保留失败候选。 |
| [scripts/mavis_stop_stress.py](../scripts/mavis_stop_stress.py) | +6/-2 | 支持安装helper fixture与明确输出目录。 |
| [scripts/mavis_voice_acceptance.py](../scripts/mavis_voice_acceptance.py) | +8/-2 | 安装版真人入口及明确输出，默认不自动采集。 |
| [tests/mavis/test_m5_safety.py](../tests/mavis/test_m5_safety.py) | +1/-1 | 仅增加证据输出覆盖，不删改50断言。 |
<!-- m6-files:end -->

## 性能分析

实测环境为本机Windows x64 build26200.9445，i7-10700F/8核16线程/约16GiB；Python3.11.14、PySide6 6.12.0、PyInstaller6.16.0、Inno6.7.4。可复现命令见 [构建说明](BUILD_MAVIS_WINDOWS.md)。

首次PyInstaller实际300.735s，干净PATH构建241.375s；最终安装器编译约159s。最终onedir27199文件、2114519207字节；安装器1778963010字节、便携zip1813732958字节。包体大头为原有106段无损动画及本地运行库，没有降低帧率、改编码或删场景来追求数字。

安装版到控制中心可见单次8.360s，测量边界不是“桌宠首像素P95≤8s”，因此性能门待验证。新增console helper只在任务/语音/诊断需要时启动，私有RPC仍有每动作系统调用与线程开销；本轮没有安装版10分钟稳态、8小时增长或每路径净增量实测，不写“开销可忽略/无增长”。源M5测量不能移作安装版通过。

CLI诊断直接运行安装目录里的exe；PATH仅System32，开发者Python只做外部驱动/只读oracle。50条安装版固定安全断言完整执行，0跳过；真实网络仅在显式allow-network的固定DeepSeek诊断请求中发生。完整GUI/语音/资源未测条目保留。

## 实机运行记录

普通用户、D盘中文和空格程序/数据目录，真实setup exit0、HKCU安装、无需重启。最终主程序显示桌宠和控制中心，第二实例exit0，自有线程WM_QUIT后正常exit0。安装版实际worker roundtrip/原生就绪退出、凭据往返、本地SAPI唤醒/ASR、DeepSeek连接/工具诊断通过；固定安全集50/50、未授权原生效应0。原始路径和精确范围见 [RELEASE_VALIDATION](reports/RELEASE_VALIDATION.md)。

首个候选QtCore无法导入，真实TOC显示误取Codex/Poppler ICU。正常源程序使用Windows System32 ICU；隔离自有测试安装中的该库后原型恢复，再用严格PATH重新构建最终候选。未将修补原型直接当完整分发通过。原49/50的junction缺依赖、错误注释编译、检查器分类等失败均保留；修复依赖后重跑全部50项，没有跳过失败项或降阈值。

包内实际文件及51461嵌入代码对象做内存凭据比较，Key0匹配、个人构建路径0匹配。安装器/程序实际NotSigned；缺麦克风、无干净VM与未实现GUI等能力没有靠文件名或输出内容补成成功。

## 交付与限制

GitHub为草稿测试候选，不发布正式通过。安装/便携/构建清单/SHA、用户/模型/跨机步骤、验证报告与门禁一并交付；新机器需本地配置Key，模型权重独立导入/下载。完整正向90/GUI72、200/10h/30min/200/60语音、安装版资源/急停矩阵等未执行项目保持待验证，数字不借用源码结果。

M6各项状态见 [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)，发布结论见 [RELEASE_GATE](RELEASE_GATE.md)。许可/覆盖率/P0未实现等阻塞继续保留。用户授权的下一步为另一台环境真实复验；不自动授予Computer Use权限，也不执行上游DSH/hooks卸载清理。
