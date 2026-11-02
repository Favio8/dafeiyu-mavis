# M5 安全、稳定性与资源记录

2026-11-03。代码基于M4 `90af76f`，安全实现冻结提交为 `91b2947`。**本轮没有降低原PRD阈值；M5 Gate未通过，不宣称DEV-039～045已全部验收完成。**

## 优先修复

- 原生UIA、焦点、逐字符SendInput放入固定的 `assistant.native_worker`。Host仍是唯一TaskService/SQLite写者，每次副作用仍须先经过ToolGateway的一次性许可。worker没有模型、数据库、shell或更改策略/审批的接口。
- 新增私有nonce绑定的Windows共享停止事件：Host先置停止事件，再终止所有自有进程；worker在最后派发点检查同一事件。低级键鼠钩子只观察，不吞用户输入；非自身标记输入、上下文/桌面丢失和时间间隙触发撤权。会话锁定/休眠通知同时急停控制与语音。
- worker PID先核对进程归属、解释器和出生时间，再持有实际进程句柄；终止/复位按实际worker退出判断，而非仅看启动壳。没有发现旧通用测试worker残留；此前“启动路径不同即已复现漏杀”的判断不成立，报告不将其算作已复现事故。
- 窗口身份加入进程出生、执行文件、窗口类和用户身份摘要；跨进程观察统一物理DPI上下文。输入草稿保存窗口/文档摘要与编辑区runtime ID，重用PID/HWND、切文档或换编辑区不能获得旧草稿权限。
- 文本读回优先使用ValuePattern，不再删除尾部换行来凑匹配；无法确定provider附加段落符时按不匹配处理。读取前后复核窗口、文档与停止状态。
- 最终Verification须匹配Goal的predicate/method；视觉或错误方法即使被标deterministic也不能冒充完成。最终验证/派发前检查预算。启动目标在自有worker清理后再次观察，避免把瞬态窗口当持久完成。
- 工具未知结果不重放输入；worker尚可响应且权限未撤销时先只读核对，证据不足保留未知，取消保持取消。实际已入队的原子包不声称已撤回。
- 修复紧邻中文的Key不被词边界匹配的问题；敏感输入/文件内容/URL在策略处拒绝。诊断仅保留固定错误码，其他错误细节默认省略。Key继续只在Windows凭据库/进程内存中使用。
- API诊断移入可终止进程；HTTP 401/429/5xx、连接失败、超时和格式失败使用独立错误码。仅对可重试模型请求有限退避+抖动，不重试Windows副作用。
- 历史成功率分母为筛选范围内全部已结束Task，取消/阻止/未验证不排除，VoiceAttempt不混入；未知usage/cost保持null。新增无分母“—”及不一致成功标记提示。

## 固定安全集与回归

| 检查 | 真实结果 | 证据 |
|---|---|---|
| M4基线Mavis | 177 passed / 1 skipped | `.scratch/m0-m1/evidence/m5-baseline.txt` |
| 固定5类×10负向集首次 | 49/50；S08的长测试路径在断言之前被严格契约拒绝，保留失败日志 | `.scratch/m0-m1/evidence/m5-negative-50.txt` |
| 修复测试写法后固定50项+10边界回归 | 60 passed；S08改为契约范围内的可执行绝对路径，仍必须在应用白名单处拒绝；门槛50/50未改变 | `.scratch/m0-m1/evidence/m5-negative-final.txt`、`.scratch/m5/security-final.xml` |
| Mavis完整运行 | 237 passed / 1 skipped | `.scratch/m0-m1/evidence/m5-complete.txt`、`.scratch/m5/complete-results.xml` |
| 后续重点进程/预算/隐私检查 | 42 passed（包含新增三次无进展澄清检查） | `.scratch/m0-m1/evidence/m5-final-focus.txt` |
| reader最终收尾与新交付报告 | 原生私有worker相关2 passed；新增报告章节/索引2 passed | `.scratch/m0-m1/evidence/m5-reader-final.txt`、`m5-docs.txt`；不是全仓再次验收 |
| 上游相关模块 | 首轮96模块95通过，application_icon的2项shell语法检查选到WSL stub失败；调整测试环境PATH使用真实Git Bash后，与补充modern-settings模块共23项通过；最终97个相关模块均有完整单模块通过结果 | `.scratch/m5/upstream/1793639408855219300/`、`.scratch/m0-m1/evidence/m5-upstream-repaired.txt` |
| 静态检查 | 全仓ruff、assistant/M5脚本compileall、diff check退出0；原window.py的4项F811通过保留兼容别名并消除导入重定义解决，无noqa或跳过 | `.scratch/m5/final-checks.json` |

固定集在 `tests/fixtures/mavis/m5-negative-cases.json`。每项记录效应陷阱、真实隔离SQLite/文件、必要私有worker和原文件oracle。50项原生效应调用均为0；R1重放测试中唯一已授权的内存计数效果单列，不能重复许可。junction逃逸使用真实Windows reparse目录；锁屏、磁盘满和网络挂起是明确的故障注入，不假称物理锁屏或填满磁盘。

Qt上游按完整模块隔离夹具生命周期，没有剔除失败模块。此结果不等于历史“所有模块同一个进程”的Qt原生abort已修复；合并进程问题继续保留。

## 急停：保留失败，不改20次门槛

专用窗口仅输入m，运行于nonce绑定的自有子进程；不是用户的记事本或文件。焦点和文本输入均经过同一网关。WM_HOTKEY采用可复现的注入消息，**不称为物理按键测试**。

- 只读native worker探针确实建立Windows lease/低级钩子/私有进程并退出；修复计时读取竞争后观测8.25ms，handler 3.59ms，无文本/鼠标注入。它不是最后一次实际文本派发的20次证明。
- 首批0/20：虚拟环境解释器路径/祖先进程验证不匹配。修复为实际base解释器与已验证Host祖先，保持所有权限制。
- 第二批15/20：工具异常场景的测量器只等消息发送线程，未等接收handler完成。修正测量方法，不将缺失计时补0。
- 第三批仍15/20：5个长输入场景被真实FOCUS_CHANGED保护拒绝，实际输入包数为0。未移除焦点检查或降低“必须实际有输入包”条件。
- 改为人工点击START的前台交接后等待600秒未收到操作，窗口已关闭；本轮没有将这次等待算通过。后续人工配合入口保留。

原始各批：`.scratch/m5/stop-stress/1793637072745931700/`、`1793637328626200300/`、`1793637533782863700/`。每项保留hotkey接收、begin/returned派发标记、worker状态、当前前台条件及失败；在途原子包不声称被撤回。仍须用当前实际PID句柄版本完成20次专项和物理按键补证。

```powershell
.venv/Scripts/python.exe scripts/mavis_stop_stress.py --wait-start
```

## 预算、资源与8小时驻留

活动/墙钟/动作/工具/模型轮数原阈值保持；3次重复无进展进入澄清。终态真实monotonic时长、实际usage、null费用和完整结束任务分母有专项检查。

| 测量 | 原始结果 | 范围 |
|---|---|---|
| 10,000条TaskService记录，100次50条分页 | 原查询P95 79.46ms；完整新统计查询P95 **147.63ms**，门槛300ms | 专用测试库，真实拒绝记录，无Computer Use；`.scratch/m5/history/1793637673134139600/`、`1793639596481560200/` |
| 20s core-only profiler | 峰值179.57MiB，观测CPU均值0.183%，心跳P95 78ms | 短时诊断，不是10min稳态，不把心跳当用户点击延迟 |
| 26s完整桌宠+静音KWS/VAD/ASR | 首次桌宠像素2.625s；峰值600.95MiB；短窗口CPU9.70%，心跳P95 140ms | CPU短样本超过5%参考值，原样保留；不是10min稳态，不据此宣称性能通过 |
| 冻结8h实例：600–1200s窗口，600样本 | 整机CPU均值**4.238%**，RSS最大**580.30MiB**，中位509.33MiB | 满足该10min窗口5%/650MiB，仍不是8h结果；合成静音，非麦克风 |

Profiler显示采样器开销和初始化/预热影响；增加逐进程CPU归因，并将记录器改为有界内存、完整原始JSONL落盘，避免测量器自身持续增长。没有降低帧率或关闭动画来降CPU。后续样本记录了预热后CPU下降，仍须用完整窗口判断。

**8小时正在运行，不提前标通过。** 从冻结提交 `91b2947` 的独立worktree启动，28800秒、600秒预热；完整上游桌宠，独立子进程使用16kHz合成静音，不打开麦克风。证据 `.scratch/m5/performance/soak-91b2947/launch.json`、`progress.json`、`samples.jsonl`；结束才生成 `result.json`。代码源固定在 `.scratch/m5/soak-source-91b2947`，后续文档编辑不改变被测代码。

上述10min快照保存在 `.scratch/m5/performance/partial-soak-91b2947-1200.json`；该窗口首/末60样本RSS中位522.86/511.46MiB，句柄中位2831/2835，最大171线程。这是动画/解码进程树在该时间窗的变化，不推断8小时无线程/句柄增长。

650MiB稳态、1536MiB峰值、KWS整机CPU5%、8小时及预热后增长10%原门槛全部保留。1秒进程/连接采样可能遗漏极短连接和已退出子进程CPU，因此“未观察到出站”不是穷尽抓包结论。真实麦克风开关循环和ASR/执行峰值矩阵仍待硬件。

## 隐私、许可与支持范围

本轮审计扫描1498个源/运行文件，使用凭据库Key在内存中比对UTF-8/UTF-16/Base64，不打印值；匹配0，诊断ZIP音频/截图附件0。安装包尚未构建，不称其已扫描。证据 `.scratch/m5/audit/1793638043749642600/inventory.json`。

收尾扩大到未跟踪源码、SQLite WAL/SHM、M5隔离数据及默认应用数据命名空间，6013文件0匹配、诊断媒体0，无>64MiB跳过；默认应用命名空间本机尚不存在。该次证据 `.scratch/m5/audit/1793641717208049100/inventory.json`。随后继续检查其他阶段隔离配置/DB/日志，最终范围与结果见 [命令记录](COMMAND_LOG.md#m5收尾2026-11-03)。扫描是时间点抽样，运行中的DB不作为一致性备份，原始测试音频/媒体fixture不冒充默认诊断附件。

最终跨阶段检查12443文件，Key匹配0、已读取的诊断包媒体0；2个上游 `test_unsupported_formats_rejec2/archive.zip` 是故意损坏的fixture，内容无法展开，审计返回非零并逐项列出，未静默忽略。证据 `.scratch/m5/audit/1793641989268056900/inventory.json`。没有大型文件/条目跳过；这仍不补足未构建的安装包与未核实权利。

[许可清单](../MAVIS_LICENSE_INVENTORY.md)保留真实wheel声明及许可文件SHA，实际FFmpeg含GPL/version3；ModelScope实查KWS与基础ASR为Apache-2.0，ONNX转换仓库License为空。角色素材非商业及来源声明继续保留，精确分发权不扩大推定。**许可/打包审计尚未闭合**。

[支持矩阵](../SUPPORT_MATRIX.md)：当前AMD64 build26200.9445、Python3.11.14、i7-10700F/8核16线程/约16GiB；浏览器/记事本版本仅检测，不等于本轮GUI验证。其他Windows构建、RDP、ARM、混合DPI、无设备的麦克风和安装版均未假称覆盖；管理员窗口拒绝。

本轮覆盖报告：行65.74%、分支46.95%、综合61.45%；原目标总体80%、关键取消/权限等90%未达到。native/voice子进程没有被当前pytest-cov采集，实际CLI运行也不能自动冒充覆盖率。报告保留缺口，不排除模块或调低阈值来过关。

## 本轮新增/修改模块

原生进程与边界：`native_worker/native_session/native_event/native_input_monitor/native_fixture`；窗口/文档观察与验证：`windows_observer/notepad_backend/verifier/service/gateway/policy`；诊断API进程与隐私：`model_probe_worker/controller/ipc/stop/provider/privacy/diagnostics`；真实统计：`storage/history_ui`；设备选择：`voice_audio/voice_worker/voice_host`；上游兼容别名：`pet/window.py`；固定50项及边界测试、实际进程退出断言；性能/支持/许可/急停脚本。

DEV-039～045的代码和测试已推进，但20次真实输入急停、8小时完成结果、覆盖率、部分许可与既有M2/M3功能缺口仍阻止M5通过。不能把本报告当发布通过声明。
