# 0.1.0 安装测试候选真实验证报告

日期2026-11-03。**发布Gate未通过。** 本报告区分已执行、失败后修复、未执行。用户最新决定将候选上传GitHub，使用另一台有完整测试环境的电脑继续验收；没有将未测项改成通过。

## 产物与来源

最终本地目录 `dist-mavis/0.1.0/162d584-evaluation/`。冻结运行代码提交 `4e021822ac559519ce231fc2f5375854f1bdd6d5`；打包提交 `162d584f1b49ec642701562f2e0e7d70b9cdfa8e`。新增验收组件来自锁定pywin32 311的win32file.pyd，SHA与包内清单记录。运行代码和后续打包修复的提交不同，不把两者混作同一快照。

| 产物 | 字节数 | SHA-256 |
|---|---:|---|
| DaFeiYu-Mavis-0.1.0-win-x64-setup.exe | 1778963010 | 25edcc6b611ef9350252748ca0923614f91bc58bcee43872a6fdbc92c9b2b4b1 |
| DaFeiYu-Mavis-0.1.0-win-x64-portable.zip | 1813732958 | 9f561537081fc17dc3790a130536cb6167d1a0895750564d0a18c6afad50fd9e |

Python3.11.14、PyInstaller6.16.0、Qt/PySide6 6.12.0、sherpa-onnx1.12.26、keyring25.6.0、comtypes1.4.17。编译器为官方已验签Inno Setup6.7.4，实际组件哈希在BUILD_MANIFEST。应用exe及安装器均为 **NotSigned**，没有伪造代码签名。角色、FFmpeg/Qt及模型保留独立许可，完整分发权利仍未闭合；GitHub保持草稿，不发布正式通过版本。

## 已执行的安装版检查

工作目录仓库根，普通用户PowerShell。目标全部为真实安装目录里的冻结exe，产品进程PATH只有System32，未使用开发者Python或DSH/Codex运行时。驱动脚本和外部oracle使用开发环境不等于产品依赖该环境，也不等于干净Windows用户/VM已测。

| 项目 | 真实结果 | 原始证据 |
|---|---|---|
| 素材门禁 | 原9/106，按上游链补齐后106/106当前无损white-v6；分发包再次通过 | `.scratch/m6/frame-material.txt`；最终候选evidence目录 |
| 双exe/依赖/中文编码 | UI无控制台、固定console helper；必要模块及Qt平台插件存在，Mavis中文常量/文件名检查通过 | `evidence/package-*/bundle-verification.json`、encoding.json |
| 当前用户安装 | 中文/空格程序和数据路径；实际setup exit0；HKCU安装，无需重启 | `.scratch/m6/install-final.log` |
| 独立启动与退出 | 桌宠与控制中心实际可见；第二实例exit0；向本次启动的自有主线程发WM_QUIT后正常exit0 | `.scratch/m6/lifecycle-final/lifecycle.json` |
| 启动观测 | 单次到控制中心可见8.360s；不是桌宠首像素P95，不能据此宣称冷启动≤8s通过 | 同上；未以短样本替代性能基准 |
| 私有worker/原生准备 | 安装版真实私有管道roundtrip、原生worker就绪与退出，未派发输入 | `.scratch/m6/final-probes/runtime.json` |
| 凭据持久化 | WinVaultKeyring，随机probe跨进程比对成功且删除；已有DeepSeek Key未改写 | `.scratch/m6/final-probes/vault.json` |
| 固定安全集 | **50/50**，失败0、错误0、跳过0、未授权原生效应调用0；真实私有文件/SQLite/junction，部分OS故障明确注入 | `.scratch/m6/final-probes/security.json`、security.xml、security-cases/ |
| 本地语音功能探针 | 真实模型加载，SAPI合成固定句触发本地唤醒/ASR，语义为打开记事本；未采集麦克风、未生成电脑任务 | `.scratch/m6/final-probes/voice.json`；不算真人语音基准 |
| DeepSeek实际连接/工具探针 | deepseek-flash两项通过；实际usage分别10/2和293/36；只发固定标记，电脑动作0 | `.scratch/m6/final-probes/provider.json` |
| 分发内容隐私 | 27199文件、2114519207字节、51461嵌入代码对象；实际凭据内存比对0匹配，个人构建路径0匹配 | `.scratch/m6/final-bundle-privacy.json` |

核心执行命令（完整参数和输出在原始日志）：

```powershell
.venv/Scripts/python.exe scripts/mavis_release.py build
.venv/Scripts/python.exe scripts/mavis_release.py package --app-dir <未改运行代码的onedir> --output <候选目录>
# 真实setup以 /VERYSILENT /CURRENTUSER /DIR=<新程序目录> /DATAHOME=<测试数据目录> 安装
.venv/Scripts/python.exe scripts/mavis_installed_lifecycle.py --app-dir <安装目录> --output <新报告目录>
.venv/Scripts/python.exe scripts/mavis_benchmark.py --app-dir <安装目录> --output <新报告目录> --models <固定模型目录> --allow-network --probes-only
.venv/Scripts/python.exe scripts/mavis_bundle_audit.py --app-dir <最终onedir> --output <新隐私报告.json>
```

## 保留的失败与修复

1. 首轮把所有WAV误判成录音，检查器拒绝出包。实际四个WAV均为固定上游版本的数学合成UI音效，已核对生成器和基线SHA。仅精确匹配的四项允许，其他录音、DB与用户配置仍拒绝。没有放开任意WAV。
2. ISCC前端PE版本是0.0.0.0，不能用它冒认6.7.4。改为官方验签安装器来源与ISCC/ISCmplr/ISPP组件哈希锁定。
3. 安装器首次编译在Pascal区遇到错误注释语法，真实exit2；已修复，日志保留。
4. 首个真实安装版QtCore导入失败，未看到正常控制中心。实际依赖TOC指向开发宿主Codex/Poppler的错误ICU；正常源程序加载Windows System32 ICU。只在自有测试安装中隔离该DLL后原型恢复，再以严格构建PATH生成全新干净候选，没有把修补原型当最终分发通过。
5. 修补原型的固定安全集49/50，S15因验收文件的动态win32file依赖漏收集失败，原生效应仍0。补入锁定组件并对最终安装版完整50项重跑后50/50；没有删除/跳过S15或改断言。
6. 隐私代码扫描遇到测试框架的合法孤立代理项字符串而中断，改为surrogatepass保留数据后完成真实扫描；不忽略Key或个人路径命中。

历史候选/失败在 `dist-mavis/0.1.0/0c45a296-*`、`4e021822-*` 及 `.scratch/m6/build-run-*`、package-run-*、lifecycle-1、repaired-probes-1。仅162d584-evaluation为本轮选定候选。

## 完整Benchmark清单与未测状态

**没有声称本机完成90次GUI/Computer Use。** B01–B30各3次的完整定义在 `assistant/assets/benchmark-cases.json`，驱动和安装版入口已交付；本轮正向Task场景执行数0，GUI真实场景执行数0。名义分母90/GUI72保留，成功率、假成功率均待验证，不以零尝试推定0假成功或100%安全。另有10条同义指令入口，尚未执行。

| 范围 | 计划/门槛 | 本轮真实状态 |
|---|---|---|
| B01–B06 | 18次系统任务 | 待验证，0次正式场景提交 |
| B07–B30 | 72次真实GUI，成功≥65/72 | 待验证，0次完整GUI场景 |
| 全部正向 | ≥81/90，每场景≥2/3，假成功0 | 未形成发布指标，不能排除不擅长场景 |
| 泛化 | ≥10条未见同义指令 | 待验证 |
| 唤醒正样本 | 200条/≥5人/默认与自定义、安静与噪声分层 | 缺真实设备/数据，待验证 |
| 唤醒负样本 | 10小时，误唤醒≤2次 | 待验证，不能以静音代替真实负样本 |
| 声学防自唤醒 | 30分钟自播，任务0次 | 本机无麦克风，待验证 |
| 命令识别 | 200条，分层语义准确率 | 待验证，单句SAPI不是200条语义基准 |
| 真实语音端到端 | 20场景×3=60，≥54/60 | 待验证，不能粘贴文字代替声音 |
| 安装版急停压力 | ≥20次，≤1s，记录在途原子包 | 入口已交付，本轮安装版专项待验证；源M5结果不代替 |
| 安装版资源 | 10分钟均值、8小时、内存增长等 | 待验证；源M5的8小时不作为安装版证据 |
| 干净机/升级/卸载/回退 | 无开发工具用户/VM，保留/恢复数据 | 仅本机安装/维护写入实测；完整矩阵待验证 |
| 系统显示/设备 | 100–200%、混合DPI、插拔/默认设备变化 | 待验证；当前单屏1920×1080/96DPI |

当前代码的通用浏览器、文件保存、视觉和完整自然语言执行仍有未实现部分。另一台电脑具备测试环境不代表这些代码能力自动完成。权限与急停前置不由测试脚本绕过；用户物理热键、本地复位和会话授权后才能运行实际控制。

完整步骤见 [另一台电脑验收](../TEST_ON_SECOND_PC.md)。包内不含API Key，新机器本地配置；模型权重独立下载/导入。原始用户音频、屏幕或个人文件不应随测试报告上传。

## 结论

可供仓库拥有者下载测试的0.1.0候选产物和真实基础报告已形成。完整正向GUI、真人语音、安装版资源、干净机、覆盖率及部分权利尚未闭合；[发布门禁](../RELEASE_GATE.md)不通过，保持GitHub草稿测试候选。
