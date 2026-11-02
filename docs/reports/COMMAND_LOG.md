# M0/M1 实际执行命令与证据索引

2026-11-02。工作目录均为仓库根，Shell 为 PowerShell；Python 命令明确使用 `.venv` 或 `.venv-audit`。本表记录有实质验证结果的命令；只读 `rg/Get-Content` 源码检查未逐条重复列出。原始日志在 `.scratch/m0-m1/evidence/`。参见 [状态](../IMPLEMENTATION_STATUS.md)、[复现步骤](../SETUP_WINDOWS.md)。

| 命令 / 操作 | 真实结果 | 证据 |
|---|---|---|
| `git status --short; git log -5 --oneline; git remote -v` | 初始无提交/remote，只有用户文档 | `UPSTREAM_BASELINE.md` 初始文件哈希 |
| 根目录 `Get-Content PRD.md` / `CODEX_EXECUTION_CHECKLIST.md` | 各退出 1；实际文件在 docs/product，随后完整读取 | 会话原始工具结果；文档路径未搬动 |
| GitHub tools get_repo/fetch/fetch_file | 读取两项目、commit、tree、规范/源码/依赖/许可 | 上游 snapshot、基线与适配审计 |
| `git remote add upstream https://github.com/MerZlin/dsh-pet-indesktop.git` | 本地 remote 建立，无远程写入 | `git remote -v` |
| `git fetch --depth 1 upstream 34d810b1eadd98d00e7cb9b3b51428a45b5bf03e` | 退出 0 | Git 对象与 HEAD |
| `git branch codex/m0-m1 <SHA>`、`git symbolic-ref HEAD refs/heads/codex/m0-m1`、`git read-tree <SHA>`、`git checkout-index --all` | 建立固定基线；非强制 checkout 拒绝覆盖既有 AGENTS/README，其余导入 | 基线、保留文件 SHA、git status |
| `uv python install 3.11.14` / `uv venv --python 3.11.14 .venv` | 退出 0 | 实际解释器与 `.python-version` |
| 初次 `uv pip install ... sherpa-onnx==1.12.15 ...` | 退出 1，版本不存在；1.12.14 元数据查询亦 404 | 会话工具结果，基线“失败候选” |
| `uv pip compile requirements-mavis.in ... --generate-hashes --output-file requirements-mavis.lock.txt` / `uv pip sync ...` | 成功；最终固定 Qt6.12.0，tokenizer 补齐 | `resolve-runtime*.txt`, `install-runtime.txt`, `install-tokenizers.txt`, `qt-612-candidate.txt` |
| `uv pip compile requirements-audit.in ...` / `uv pip sync --python .venv-audit/Scripts/python.exe ...` | 成功；修正 mistralai 3.7.0 不兼容为 1.9.11 | `resolve-audit*.txt`, `install-audit*.txt`, `windows-use-sdk-fix.txt` |
| `uv pip check --python .venv/Scripts/python.exe`、audit 同命令 | 两者退出 0 | `pip-check-runtime.txt`, `pip-check-audit.txt` |
| `.venv/Scripts/python.exe -m pytest tests/mavis/test_core.py -q`（实现前） | 退出 2，ModuleNotFoundError，预期 red | `core-red.txt` |
| `scripts/mavis_tests.py --name namespace-red tests/mavis/test_namespace.py -q --tb=short` | 1 failed / 1 passed，确认误迁移缺陷 | `namespace-red.txt` |
| 相同 namespace 用例修复后 | 2 passed，退出 0 | `namespace-green.txt` |
| `scripts/mavis_tests.py --name upstream-baseline --timeout 1500 tests --ignore=tests/mavis -q` | Qt6.10.2 原生访问冲突，退出 3221225477 | `upstream-baseline.txt` |
| `scripts/mavis_tests.py --name qt612-chat tests/test_chat_themes.py -q --tb=short` | 20 passed，退出 0 | `qt612-chat.txt` |
| `scripts/mavis_tests.py --name upstream-qt612-final --timeout 1500 tests --ignore=tests/mavis -q --tb=short` | fatal abort 后未完成，超时 124 | `upstream-qt612-final.txt` + diagnostic 目录 |
| 上游 affected 命令，完整参数见 IMPLEMENTATION_STATUS | 先 257 passed / 2 failed；更正测试用 bash 选择后 259 passed，退出 0 | `upstream-affected*.txt` |
| `scripts/mavis_tests.py --name m1-complete tests/mavis -q --cov=assistant --cov-branch --cov-report=term-missing --cov-report=json:.scratch/m0-m1/evidence/coverage-final.json` | 126 passed / 1 skipped，退出 0 | `m1-complete.txt`, `coverage-final.json` |
| `scripts/mavis_core_probe.py` | 100 fixture、20 挂起 worker；退出 0 | `core-probe.json`, `core-probe-run.txt` |
| `scripts/mavis_ui_smoke.py --baseline` | 成功/首帧失败样本均保留；静态窗存在不等于动画通过 | `baseline-*.txt` 和分次 result.json |
| `scripts/mavis_ui_smoke.py`（退出修复前） | 退出被 hide-on-close 否决，探针超时；一个诊断进程只在核实 PID/命令行/父子关系后被终止 | `mavis-native-*.txt`、SQLite 真实取消时间、M1 报告 |
| `scripts/mavis_ui_smoke.py`（修复后） | 退出 0；125ms 可见取消 | `mavis-native-quit-fixed.txt` |
| `scripts/mavis_ui_smoke.py --scale 1.5 --profile-label '中文 路径 '` | 退出 0；187ms 可见取消，路径与界面检查通过 | `mavis-native-150-final.txt` |
| `.venv-audit/Scripts/python.exe scripts/mavis_audit_windows_use.py` | 首次 Mistral import 失败；版本修正后保护下导入/UIA/遥测检查退出 0 | `windows-use-audit-run.txt`, `windows-use-audit-final.txt/json` |
| `scripts/mavis_voice_spike.py --download` | 下载固定两个模型、校验大小、安全解包/哈希，退出 0 | `model-download.txt`, `models/model-manifest.json` |
| `scripts/mavis_voice_spike.py --infer` | 首次缺 sentencepiece；补依赖后真实 ASR/KWS 推理退出 0 | `voice-infer-first.txt`, `voice-spike.json` |
| `scripts/mavis_voice_spike.py --tts-smoke` | 本地声音枚举/合成，两关键词命中，退出 0 | `tts-kws-spike.json` |
| `scripts/mavis_credential_probe.py` | WinVaultKeyring 源码跨进程往返及清理通过 | `credential-source.txt` |
| PyInstaller 凭据探针构建及 exe（完整参数见 SETUP_WINDOWS） | 构建 0、运行 0；frozen=true，跨进程及清理 true | `credential-build.txt`, `credential-frozen.txt` |
| `scripts/mavis_inventory.py` | 80 个运行包元数据、实际 FFmpeg 许可/哈希，退出 0 | `inventory-run.txt`, `runtime-dependencies.json`, `ffmpeg-license.txt` |
| 增量 `ruff check`、`compileall`、`git diff --check` | 通过；全仓 ruff 仍有 4 条既有 F811 | `ruff-incremental.txt`, `ruff.txt`、最终检查输出 |
| `scripts/mavis_tests.py --name documentation-check tests/test_pr_report_discipline.py -q --tb=short` | 230 passed / 1 failed；失败为保留的用户空 AGENTS 不含上游规范文本；新增报告的章节/索引检查通过 | `documentation-check.txt` |

不把候选失败输出抹掉，也不把这里的测试命令当作真实 Agent 已操作用户应用。没有执行 B01–B30、完整语音/负向/性能发布基准。
