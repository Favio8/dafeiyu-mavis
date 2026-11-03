# Mavis 0.1.0 Windows构建

普通用户PowerShell，仓库根目录。固定Python3.11.14、requirements-mavis.lock.txt、PyInstaller6.16.0；安装器使用Inno Setup6.7.4。源代码与依赖摘要写入build-info.json。

```powershell
uv python install 3.11.14
uv venv --python 3.11.14 .venv
uv pip sync --python .venv/Scripts/python.exe requirements-mavis.lock.txt
.venv/Scripts/python.exe scripts/prepare_frameseq_bundle.py
./scripts/build_onedir.ps1 -Variant mavis
# 也可显式指定已安装的Inno Setup编译器
.venv/Scripts/python.exe scripts/mavis_release.py build --iscc '<Inno Setup6.7.4目录>/ISCC.exe'
```

Inno Setup来源为jrsoftware/issrc的is-6_7_4 release，下载后核对Authenticode。默认构建工具路径 `.scratch/m6/tools/InnoSetup6.7.4/ISCC.exe`；不是产品运行依赖。

Mavis变体沿用上游onedir、UTF-8编码隔离、素材门禁、Qt/解码器和许可收集思路；不调用DSH桥接、hook或上游卸载清理。界面程序无控制台，固定console worker通过继承的私有管道工作，不调用系统Python。没有任意模块、shell或动态模型工具入口。依据 [PyInstaller6.16官方冻结进程说明](https://pyinstaller.org/en/v6.16.0/common-issues-and-pitfalls.html)，注册外部应用启动时仅在独立原生worker内临时恢复系统DLL搜索环境，避免把打包库注入外部应用；自有helper仍用包内运行库。

构建输出独立候选目录 `dist-mavis/0.1.0/<源码提交与时间>/`，包含onedir、安装器、便携zip、构建日志、BUILD_MANIFEST与SHA256SUMS。帧序列缺失时使用上游同一转换链补齐后检查，不降低编码档或改帧率。

包内权重采用固定清单下载/离线导入策略，默认不分发。构建配方和输入锁定可复跑；独立二次构建是否字节相同需单独证明，不能由固定脚本推定。

安装版基准由同一包内mavis-worker.exe的显式benchmark入口运行，默认不授予权限：需要真实急停热键、本地复位与授权。清单B01–B30各3次固定90分母，GUI72分母；不支持、环境阻塞和未执行分别记录，语音缺设备/数据不得补成通过。详细命令和本轮实际结果见RELEASE_VALIDATION。
