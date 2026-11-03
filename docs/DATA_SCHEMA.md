# M1 数据与恢复

本机run.bat便携入口将同样的数据格式放在项目 `.mavis-local/DaFeiYuMavis/`，Git忽略该目录；通用CLI不传data-home时默认命名空间不变。没有移动、合并或覆盖已有用户库，凭据仍由Windows凭据库管理。

M5补充（2026-11-03）：Observation JSON增加默认空字符串的identity_digest/document_digest，用于进程/窗口与草稿身份绑定，旧记录可继续读取，SQLite版本未变。明文窗口标题与文档名不作为该摘要来源的旁路字段入库；Key继续集中脱敏，诊断只输出固定错误码。历史统计使用相同筛选范围内全部已结束Task为分母，VoiceAttempt独立；无分母显示空值，未知费用不估算。最新验证与限制见 [M5报告](reports/M5_SAFETY_STABILITY.md)。

**M4 增量：** SQLite版本仍为1，无结构迁移。既有表新增查询/删除接口，Task与VoiceAttempt独立筛选并50条分页；UI删除事务先清理关联语音尝试，再级联删除结束Task，拒绝删除活动Task。7/30/90天保留启动后及每小时调度，配置损坏时暂停自动清理。`assistant-settings.json`仅保存非秘密配置，新Task通过provider字段和`task.configuration`事件保留当时参数，`parent_task_id`关联显式重跑。CRUD与保留已实现，统一验收待做；下文保留M1历史快照。

2026-11-02，schema_version/user_version = 1。代码 `assistant/contracts.py`、`storage.py`、`service.py`；参见 [架构](ARCHITECTURE.md)。

| 表 | 主键 / 约束 | 内容 |
|---|---|---|
| tasks | UUID；`one_active` 部分唯一索引；mode/created 索引 | 严格 Task JSON、状态、起止时间、模式；未知 usage/cost/duration 为 null |
| events | event_id；UNIQUE(task_id,seq)；任务外键 cascade | 有序 TaskEvent，提交后才向 UI 发布 |
| steps | id；UNIQUE(task_id,seq)、UNIQUE(task_id,tool_call_id)；外键 | 动作摘要、脱敏参数、风险、观察、执行状态、耗时、retry_safe |
| approvals | id；任务外键 | pending/approved/denied/expired/consumed/revoked、本地决定来源；不包含可恢复的执行能力 |
| observations | id；任务外键 | Host 观察版本、上下文摘要和必要窗口字段；不存截图 |
| verifications | id；任务外键 | 目标、方法、结果、证据、强度、generation |
| voice_attempts | id；可空 task_id，删除任务时 set null | 语音元数据；无有效命令不能保留环境转写；无音频 blob |

Task、Step、Observation、Verification、Approval、VoiceAttempt、TaskEvent、ToolResult 使用 Pydantic strict/extra=forbid/frozen；有界字段和预算双向约束。真实原始 API Key 不在契约中，ProviderSnapshot 只有凭据引用。存储再统一脱敏常见 `sk-`、Bearer、password/token/API key 赋值。

每次任务快照、对应事件和相关记录同一事务提交；foreign_keys=ON、WAL、synchronous=FULL、短 busy timeout。单写者线程约束加上应用单实例锁防止多个控制器同时操作。DB 锁定/磁盘错误先停止新动作，不能无审计继续。测试注入了写入错误、锁竞争、重复事件/半事务失败。

启动扫描全部非终态任务，改为 INTERRUPTED、递增 generation、撤销遗留审批，绝不重放动作。挂起/取消时，尚未派发的步骤标 cancelled，无法确认结果的运行中步骤标 unknown。迟到回调只有审计权限。

新库从 version 0 建立 version 1。已有未知 version 0 数据先做 SQLite 一致备份，然后拒绝自动迁移；未知高版本原样拒绝。**尚无 v1→v2 迁移**，将来要增加真实迁移和备份保留策略，不把“拒绝不认识的库”称为升级迁移完成。

默认目录 `%LOCALAPPDATA%/DaFeiYuMavis`；`--data-home` 只改变其父目录，测试统一 `.scratch/m0-m1/profiles/`。`state.db` 与 `state-test.db` 分开。无上游数据自动迁移。SQLite 不加密；保留清理 API 只删除终态记录，当前尚未接入自动 30 天调度、导出/删除 UI 和备份自动清理（M4/M5）。
