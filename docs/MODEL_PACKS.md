# 本地语音模型与离线导入

0.1.0安装包包含本地推理引擎、tokenizer依赖和固定清单，不捆绑模型权重。清单在程序内部 `assistant/assets/voice-models.json`，逐文件固定大小与SHA-256；下载与导入使用同一校验。

在控制中心“语音与唤醒”下载模型，或选择本地导入目录。离线完整目录应包含三个清单模型ID对应的子目录，各目录含清单所列文件；缺失任一模型时不能显示语音全部就绪。导入不执行脚本、不加载清单外模型，损坏的已有文件不会被静默覆盖。

默认数据目录由安装时选择，模型在其中DaFeiYuMavis/voice/models。便携版位于data/DaFeiYuMavis/voice/models。包内不带麦克风授权或启用状态，安装/启动不会自动录音。

KWS和基础ASR的来源元数据为Apache-2.0；ONNX转换包权利链仍未闭合，VAD来源与MIT声明见固定清单。没有把缺失许可推定为允许再分发。相关限制见组件许可清单；不将本地导入或功能探针冒充真人语音基准通过。

源码环境准备已校验模型的命令（工作目录仓库根，PowerShell）：

```powershell
.venv/Scripts/python.exe scripts/mavis_voice_models.py --root .scratch/m3/models --download
```

安装版功能探针使用安装目录里的固定控制台辅助程序，不调用开发者Python：

```powershell
./mavis-worker.exe --probe voice --models '<已校验模型目录>' --output '<新建报告路径.json>'
```

该探针在本地SAPI合成已知句子并运行实际模型，不采集麦克风；单句回放不能代替200条正样本、10小时负样本、30分钟声学自播或60次真实语音端到端。

接入真实麦克风后的安装版验收窗口（默认不自动开启采集；明确点击监听后才录音，原始音频不落盘）：

```powershell
./mavis-worker.exe --voice-acceptance --models '<模型目录>' --output '<新的验收目录>'
# 真实麦克风开启后的30分钟声学专项，不能用合成回放代替
./mavis-worker.exe --voice-acceptance --models '<模型目录>' --output '<另一新的验收目录>' --tts-soak-seconds 1800
```
