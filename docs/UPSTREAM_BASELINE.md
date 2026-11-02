# Mavis M0 上游与依赖基线

基线日期：2026-11-02；工作分支 `codex/m0-m1`。这是本工作区的实测记录，不能把上游历史报告中的数字当作本机结果。入口见 [文档索引](INDEX.md)，当前门禁见 [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)。

## 工作区与来源

- 初始仓库没有提交、没有 remote、没有桌宠代码。仅有用户未提交的空 `AGENTS.md`、218 字节 `README.md`、`docs/product/`。
- 需求实际位于 `docs/product/PRD.md` 和 `docs/product/CODEX_EXECUTION_CHECKLIST.md`；已完整读取，原文未改。该目录原有“不上传以及 git 同步”的提示，因此增加 `/docs/product/` 忽略规则。
- 使用 GitHub 专用工具核对仓库、commit、文件和目录，再执行固定 SHA 的 fetch。保留 `upstream=https://github.com/MerZlin/dsh-pet-indesktop.git`，没有配置发布 remote、没有 push、没有生成本项目提交。
- 桌宠上游：[MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop)，`main` 的锁定 SHA 为 **`34d810b1eadd98d00e7cb9b3b51428a45b5bf03e`**，提交时间 `2026-10-23T00:14:41+08:00`。
- 非强制 `git checkout-index --all` 导入缺失文件；它拒绝覆盖已存在的 AGENTS/README。两者仍保持用户原始字节内容。因此 `git diff HEAD` 中这两项是**导入时保留的本地差异**，不是本轮删除上游说明的编辑。
- 上游指南与 README 独立保存在 [upstream/AGENTS.md](upstream/AGENTS.md)、[upstream/README.md](upstream/README.md)。已读取开发交接、构建说明、`tests/conftest.py`、配置与架构约束，以及上游 UI skill。历史 `PROJECT_HANDOFF.md` 的旧类名、用例数不作为当前源码事实。
- 两份快照保留原文，其相对链接按原上游仓库根目录解释；本项目当前可用入口使用本页和 `docs/INDEX.md`，不把快照内的相对路径当作重新组织后的文档链接。

初始且仍保留的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| AGENTS.md | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| README.md | `5a52ab536584b4afc389585d0f3d75141dafe5ad0cb0109939785d57b5093154` |
| docs/product/PRD.md | `7a8a7d39d1eb3d00cb673553cfa5c07d469abd8ead0fd924a8f58821fd990176` |
| docs/product/CODEX_EXECUTION_CHECKLIST.md | `a0930716dc09b99866497e12b9e78714984a423c99b281ffbeed8d00218f7d14` |

## 实际入口与复用映射

| 上游实际位置 | 原职责 | Mavis 处理 |
|---|---|---|
| `pet/__main__.py::_main` → `pet/app.py::main` | 原源码入口 | 保留；新增 `python -m assistant` 调用 `app.main(enable_chat=False)` |
| `pet/app.py::AppShell`, `PetInstance` | 应用和单宠装配、托盘、生命周期 | `main` 中增加一个显式 Mavis 分支，在 `start()` 后 attach 助手；Mavis 跳过旧临时目录/自启注册表清理 |
| `pet/overlay_shell.py::OverlayShell`, `pet/pet_sprite.py`, `pet/overlay_window.py` | 默认合成窗、动画、拖拽、交互 | 文件未改，仍由上游负责 |
| `pet/window.py::PetWindow` | legacy/capture 渲染路径 | 文件未改；不是新增另一套桌宠 |
| `pet/library.py::MovieLibrary`, `pet/webm_clip.py`, `pet/decode_fanout.py` | 素材和解码 | 文件未改；负载下首帧失败、全量 Qt 生命周期问题保留为阻塞 |
| `pet/multi_window_shared.py::presentation_targets`、目标的 `show_bubble` | 两种拓扑统一呈现 | `assistant/pet_bridge.py` 复用，只显示真实状态文本；不编造动画 ID 或模拟成功庆祝 |
| `pet/config.py` | 上游设置与迁移 | Mavis 使用 `%LOCALAPPDATA%/DaFeiYuMavis`；禁止自动迁入旧桌宠配置/会话 |
| `pet/feature_activation.py::is_active` | 可选模块开关 | Mavis M0/M1 运行时关闭全部已登记的可选模块，避免旧聊天、联动、网络及系统工具绕过新网关 |
| `pet/settings_widgets.py::SettingRow/SettingsCard` | 原 Qt 控件 | 控制中心复用；左导航、右内容、蓝白配色 |
| `pet/overlay_instance_gate.py` | 本机单实例门 | 主入口原样使用，core-only 诊断入口也取得同一把门锁 |
| `packaging/`、`scripts/build_onedir.ps1` | 原 onedir 构建 | 保留，尚未构建完整 Mavis 安装包；只构建过凭据探针 |
| 上游 `pet/chat`、`agent_link`、在线 TTS | 聊天、外部运行时联动等 | 不作为 Mavis 的 Agent、凭据或语音主链路 |

## 实测候选组合

| 组件 | 锁定版本 | 实测边界 |
|---|---|---|
| CPython x64 | 3.11.14 | `uv` 安装；Windows 11 非管理员进程 |
| PySide6 / shiboken6 | 6.12.0 | 原生 Qt 窗口、动画样本、核心 UI；完整上游套件仍未通过 |
| Windows-Use | 0.8.1，仅审计环境 | 完整依赖安装、受出站/子进程防护的导入、读取本进程 Qt 窗口 UIA；无真实输入 |
| mistralai | 1.9.11，仅审计环境 | 0.8.1 的 `from mistralai import Mistral` 与解析出的 3.7.0 不兼容，降到实测可导入版本 |
| sherpa-onnx / core | 1.12.26 | 真实 CPU KWS/ASR 推理；不是麦克风端到端验证 |
| sentencepiece / pypinyin | 0.2.1 / 0.55.0 | 官方 `text2token(..., tokens_type='ppinyin')` 的实际依赖 |
| keyring | 25.6.0 | WinVaultKeyring 源码和最小冻结包跨进程读写/清理测试标记成功 |
| pywin32 / pywin32-ctypes | 311 / 0.2.3 | Windows 依赖与本地 SAPI 枚举/合成 |
| Pydantic | 2.11.9 | 严格 JSON 契约和未知字段拒绝 |
| imageio-ffmpeg / Pillow | 0.6.0 / 11.3.0 | bundled FFmpeg 7.1 实际解码一帧 921600 字节 |
| PyInstaller | 6.16.0 | 只验证最小凭据 onedir 产物 |

`requirements-mavis.lock.txt`、`requirements-audit.lock.txt` 是 Windows / Python 3.11 的实际带哈希解析结果，不是跨平台承诺。当前 runtime 环境 80 个发行包，audit 环境 210 个；两者 `uv pip check` 通过。审计环境多出的 SDK、开发和通信依赖不进入产品进程。详细包许可元数据在本机 `.scratch/m0-m1/evidence/runtime-dependencies.json`。

失败候选保留：sherpa-onnx 1.12.15/1.12.14 在当时 PyPI 索引不存在；第一次 tokenizer 推理缺少 sentencepiece；PySide6 6.10.2 在原聊天主题测试稳定访问冲突。6.12.0 的该单文件 20 项通过，但全量仍有进程级 Qt 原生 abort，不能宣称换版本解决了所有问题。

## 许可基线

| 内容 | 来源 / 已确认信息 | 仍需处理 |
|---|---|---|
| 桌宠代码 | 根 `LICENSE`，MIT，保留 Merzlin 署名 | 分发时保留全文 |
| Windows-Use 代码 | wheel / 仓库 MIT；源码与 wheel 分别锁定 | 不能把代码 MIT 当作沙箱保证 |
| 角色动画 | `THIRD_PARTY_NOTICES.md` 第 2 节：上善无形 OC「溟月」，社区素材，非商业限制及署名要求 | 精确素材许可版本/分发权限未独立核实，不能声称全产品可商用 |
| PySide6 | wheel 元数据 `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | 完整安装包的 Qt 合规材料留待 M6 |
| imageio-ffmpeg 包 | BSD-2-Clause | 包的许可与 bundled 二进制不同 |
| 实际 FFmpeg 二进制 | `ffmpeg -L` 返回 **GPL v3 or later**；带 `--enable-gpl --enable-version3` | 不得误记为 LGPL；发布前整理对应来源/分发义务 |
| sherpa-onnx 引擎 | Apache-2.0 | 模型权重单独记账 |
| 中文 KWS 权重 | 固定官方 release 包，包内 README 标 Apache License 2.0 | 本地测量 SHA-256；官方旧 release 未提供独立 digest |
| 中文 ASR 权重 | 固定官方 release 包，README 指向 ModelScope 作者模型 | 权重的独立许可尚未核实；不分发该模型包 |
| keyring / pypinyin / sentencepiece | 发行元数据分别 MIT / MIT / Apache-2.0 | 完整传递清单见 inventory，最终 SBOM 尚未完成 |

原始 `LICENSE`、`THIRD_PARTY_NOTICES.md` 均未改。更多依赖决策见 [ADR](adr/001-mavis-m0-baseline.md)，实测与失败见 [M0 报告](reports/M0_BASELINE_RUN.md)。
