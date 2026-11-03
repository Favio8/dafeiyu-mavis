# 在另一台电脑验证 0.1.0

从GitHub测试候选下载完整安装器或便携zip、SHA256SUMS及验证报告。候选不代表发布通过；本机未测项保持待验证。API Key和个人数据不随包迁移，新电脑需在本地界面重新配置Key。

## 基础安装

普通用户运行安装器，选择程序和数据目录；数据目录检查失败时换一个可写盘。便携版解压整个zip再运行主exe。不要复制单个exe，不需要安装Python/DSH/Codex来运行产品。

安装目录的 `mavis-worker.exe` 是固定辅助程序，不是任意命令终端。以下PowerShell命令的输出目标必须为新的路径：

```powershell
./mavis-worker.exe --probe runtime --output '<新的目录>/runtime.json'
./mavis-worker.exe --probe vault --output '<新的目录>/vault.json'
./mavis-worker.exe --security-suite --output '<新的目录>/security.json'
./mavis-worker.exe --probe provider --allow-network --output '<新的目录>/provider.json'
```

凭据探针只临时写入随机probe标记并删除，不改已有DeepSeek Key。模型探针发送固定短标记，无电脑动作。没有网络授权时不要加allow-network。

## 90项 Computer Use

源码仓库切到 `codex/m6-0.1.0`。基准驱动使用Python标准库，目标产品仍是安装目录里的冻结exe，不是源码Python。先确认没有其他测试占用Ctrl+Alt+F11。

```powershell
python scripts/mavis_benchmark.py --app-dir '<实际安装目录>' --output '<新的验收目录>' --models '<固定模型目录>' --allow-network
```

真实基准控制中心出现后，物理按Ctrl+Alt+F11，在界面明确复位，再勾选本次受限记事本授权。没有这一步就保持未授权/待验证，不允许脚本伪造physical_seen。开始后避免人为操作目标；任何人工干预需记入报告。不会接管或关闭已有用户记事本。当前通用浏览器/文件/视觉未全部实现，相关指令失败与未触达GUI必须保留，不按“环境齐全”推定成功。

B01–B30各3次，分母90；B07–B30为GUI72次。整体目标81/90、GUI65/72、每场景至少2/3、假成功0。另有10条同义指令。只有实际目标oracle通过才计成功，不能靠模型说完成或工具ok。

## 急停与安装版资源

与上面的GUI基准顺序运行，不能同时争抢F11。专用窗口出现后人工点击START并保持前台：

```powershell
./mavis-worker.exe --stop-stress --wait-start --output '<新的急停目录>'
./mavis-worker.exe --residency --seconds 28800 --warmup 600 --voice-models '<模型目录>' --output '<新的常驻目录>' --emergency-shortcut Ctrl+Alt+F8 --recording-shortcut Ctrl+Alt+F7
```

急停20次脚本使用WM_HOTKEY消息，不冒充物理键；物理键另留真实记录。资源脚本完整桌宠+合成静音模型，不打开麦克风；只有自然结束result.json可证明8小时，不能拿源码版或短样本替代安装版。

## 真人语音、显示器及恢复

接麦克风后，安装辅助程序的 `--voice-acceptance --models <目录> --output <新目录>` 打开正常监听/校准界面。`--tts-soak-seconds 1800`用于真实设备下的自播专项；录音需要明确手动开启，原始音频默认不保存。完整样本要求：200条正唤醒、5位说话者、默认/自定义词和安静/噪声均衡；10小时负样本；30分钟声学自播；200条有效命令；20场景各3次真实麦克风端到端共60次（至少12个GUI场景，目标54/60）。不要以SAPI回放代替真人样本或以文字粘贴代替声音。

记录Windows构建、麦克风型号/距离/噪声方法、模型、屏幕/DPI。另在新用户或VM、100–200%与混合DPI、升级/卸载/重装、离线基础模式检查；未做的留待验证。卸载应保留应用数据和Windows凭据。不要发送Key或原始个人音频，分享脱敏报告即可。
