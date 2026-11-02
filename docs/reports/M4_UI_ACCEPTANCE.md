# M4 控制中心与记录实现

2026-11-02，基于 `b3fbb41`，开发分支 `codex/m4-control-center`。

按用户要求，本轮开发优先，**未运行pytest或功能回归套件**。只进行静态检查和两次原生窗口查看；业务行为、动画与DPI矩阵留到最后统一验收。本报告不将“已实现”写成“已验收通过”。

## DEV-032～038

| DEV | 已实现 | 统一验收/依赖 |
|---|---|---|
| 032 | 八页原生Qt；保留已确认的蓝白/矢量图标；窄于860逻辑像素侧栏收为64px，菜单保留完整导航；停止入口独立于内容滚动 | 系统100/125/150/200%、混合DPI、键盘与长文案 |
| 033 | 健康卡、当前任务、数据库最近5条、文字备用/录音入口；模型/语音/权限分别跳过；继续桌宠模式停止助手；首次隐藏用托盘提示当前监听状态 | 跳过/恢复引导、隐藏与缺失能力组合 |
| 034 | SQLite全文检索指令/事件/步骤/验证，状态/来源/7/30/90天或全部时间，倒序50条分页；Task和VoiceAttempt独立结果集 | 多页、组合筛选、刷新/失败；不向正式页面填入样本记录 |
| 035 | 原始/最终指令、目标、事件、脱敏参数、审批状态/期限、独立证据、错误、副作用、真实usage；技术信息默认折叠；重跑创建新Task并链接原Task | 终态、审批过期/已消耗、重跑新许可、数据库对照 |
| 036 | 模型参数保存、凭据库入口、连接/工具探针状态、语音参数后端校验、可替换热键、Notepad范围撤销、原生外观入口；普通设置只影响后续Task快照 | 网页/目录范围、视觉能力等依赖未完成M2，当前明确不可配置；其余设置行为统一测试 |
| 037 | Task/VoiceAttempt当前页导出JSON/Markdown、单删/清空、7/30/90天保留调度、活动任务保护；诊断预览后导出ZIP，无音频/截图/任务正文及静默上传 | CRUD/保留/脱敏/缓存与备份/文件错误 |
| 038 | 按角色实际分类选择现有动画ID，缺失回待机；测试任务不庆祝；独立临时抑制位让sprite退出绘制/命中，保留用户显隐与clip状态 | 原动画/拖动/多宠/显隐、legacy窗口、工作让路和DPI/可访问性 |

## 数据、配置与复用

查询路径为 `HistoryQuery → Controller → Store.history/details → queued Qt signal → HistoryPanel`。表格、时间线、审批和验证来自原SQLite表；不存在正式页面种子数据。未知usage/费用显示“未提供”，只有SUCCEEDED且独立验证passed使用成功色。

新任务沿用provider字段，并增加 `task.configuration` 事件保留当时非秘密Provider参数；设置保存不修改历史快照。`assistant-settings.json`仅保存非秘密设置，API Key仍只经原Credentials接口进入Windows凭据库，输入框提交后清空。模型ID拒绝Key样式内容，校验错误不回显输入值。语音偏好由既有VoiceHost拥有；角色/大小/透明度等由上游设置拥有，不复制第二份状态。

删除结束Task时先清除关联VoiceAttempt，再由外键级联清理子记录；拒绝删除活动Task。记录保留在启动后及每小时检查，按结束时间清理Task、按创建时间清理语音尝试；设置损坏时不按回退值自动清理。清空保留活动任务，并处理Mavis专用diagnostics/backups中的mavis-*缓存与固定schema迁移备份名，不删除用户已导出文件，不声称撤回云端文本；文件清理失败报告部分缓存未移除。

诊断使用字段白名单：版本、OS/依赖、非秘密模型参数、实际注册/语音状态、计数和脱敏错误。ZIP只写已预览的 `diagnostics.json`，不遍历目录添加附件，也没有上传接口。

复用 `SettingRow`、`SettingsCard`、`vector_widget_icon`，无Web/Electron。外观通过已查证的 `OverlayShell.open_settings_for()` / `PetInstance.open_modern_settings()` 打开。动画请求从实际cats分类选ID，经 `request_link_anim/request_link_idle` 衔接；没有改名或新增素材。

`PetSprite`仅新增 `_assistant_suppressed` 和 `set_assistant_suppressed()`：默认False、与用户_visible独立，沿用脏矩形更新。legacy窗口临时调整透明度/穿透，结束按当前用户配置恢复。播放器、物理、拖动与多屏渲染没有重写；兼容性留到统一验收。

## 本轮实际运行

| 操作 | 结果 | 证据 |
|---|---|---|
| 增量ruff | 通过；首次4条未使用导入已清理 | `.scratch/m4/final-checks.txt` |
| compileall/AST | 通过 | 同上及变更扫描 |
| git diff --check | 通过 | 同上 |
| `scripts/mavis_m4_preview.py --capture` | Windows原生真实空库0条；1100/720/560宽，侧栏200/64/64；停止可见、内容滚动 | `.scratch/m4/1793630972217944300/preview.json` 和PNG |
| 同脚本 `--capture --test-mode --database .scratch/m3/evidence/1793628506737725100/profile/state-test.db` | 只读复制原库到隔离库；显示3条此前真实ASR形成的“权限关闭”失败任务，显式标记测试，并可读详情；未改动原证据库 | `.scratch/m4/1793632248853967900/preview.json`、`history.png` |

这些是页面装配查看，不是分页/删除/导出/热键/动画的功能验收。本轮无付费API调用、麦克风采集或Windows键鼠注入。运行资料留在忽略的`.scratch`。

## 最后统一验收

```powershell
# 完整桌宠与控制中心
.venv/Scripts/python.exe -m assistant

# 隔离空库，未自动录音/授权；可正常交互
.venv/Scripts/python.exe scripts/mavis_m4_preview.py

# 可选只读复制已有真实库用于页面查看，正式程序不种子填充记录
.venv/Scripts/python.exe scripts/mavis_m4_preview.py --capture
```

统一检查以下行为，不在开发中反复运行相同验收：

1. 隔离测试库通过TaskService形成超过50条真实测试轨迹，检查分页、组合筛选、Task/VoiceAttempt独立统计；不在正式库植入“成功样本”。
2. 成功、失败、取消、未验证和待审批逐项与DB对照；检查原始/修正指令、副作用/证据、未知usage、重跑新ID及新许可。
3. 活动Task不能删除；清空保留活动Task；撤权实时阻止新派发。导出当前筛选页，核对JSON/Markdown和脱敏。
4. 修改模型/超时/保留期限/语音设备，核对新旧Task快照和失败反馈；冲突热键保留原组合，急停无效时不能开启电脑操作。
5. 预览后导出ZIP，确认只有展示过的diagnostics.json；检查清空的DB关联、缓存/备份范围、用户导出文件保留和无上传。
6. 分别跳过模型/语音/权限、继续桌宠模式、恢复引导及隐藏窗口，检查监听状态说明真实。
7. 完整桌宠下检查工作让路/恢复、用户显隐/换角色/多宠、缺素材回退、测试不庆祝，以及100/125/150/200%和混合DPI、Tab/焦点/读屏名称。

## 本轮修改文件

| 模块 | 文件 |
|---|---|
| 记录查询与展示 | `assistant/history.py`、`history_ui.py`、`storage.py` |
| 模型/数据/诊断页 | `assistant/control_pages.py`、`diagnostics.py` |
| 配置与快照 | `assistant/settings.py`、`controller.py`、`service.py`、`native_tasks.py`、`__init__.py` |
| UI与事件桥 | `assistant/ui.py`、`pet_bridge.py`、`voice_host.py`、`stop.py` |
| 动画与临时让路 | `assistant/pet_presentation.py`、`pet/pet_sprite.py` |
| 后续验收适配 | `scripts/mavis_m4_preview.py`、`scripts/mavis_ui_smoke.py`、`tests/mavis/test_ui.py`、`test_bridge.py`（本轮未执行测试） |
| 文档 | 实施状态、数据契约、架构、限制、Windows步骤、索引、变更清单与本报告 |

原始AGENTS、README、PRD/清单与用户数据未修改。M2/M3缺口保留，M4不标记Gate已通过。
