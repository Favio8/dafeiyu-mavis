# M1 工具与许可契约

M2 增量见 [M2 报告](reports/M2_DESKTOP_E2E.md)：在明确的本机运行期授权、热键和 lease 下，仅固定 Notepad launch、`desktop.focus_window`、`desktop.focus_control`、单 BMP 字符 `desktop.type_text` 有受限原生实现。其余工具仍没有真实后端。下表是 M1 历史基线，不代表已扩大到通用电脑操作。

2026-11-02。实际代码为 `assistant/contracts.py`、`actions.py`、`policy.py`、`gateway.py`；与 [架构](ARCHITECTURE.md) 和 [审计](WINDOWS_USE_ADAPTER_AUDIT.md) 一起阅读。

## 契约和实际注册范围

下表前七项是已验证的参数/策略 Schema，**没有对应的真实执行后端**。只有最后一项在显式 `--test-mode` 中可派发。

| tool | 受约束参数 | 本地策略 | M1 执行 |
|---|---|---|---|
| `system.open_url` | HTTPS URL ≤2048；禁止凭据、控制字符、危险协议/端口 | 精确规范化域名，不放行任意子域 | 禁用 |
| `system.launch_app` | 已登记 app_id，非路径/命令字符串 | 本地应用范围，禁止终端等 | 禁用 |
| `file.create_new` | 绝对路径、内容≤4000 | 现有授权父目录、路径/重解析点/ADS/设备名检查、不覆盖，R1 | 禁用 |
| `desktop.click` | control_id | Host 观察中的明确安全控件，拒绝 RU | 禁用 |
| `desktop.type_text` | control_id、单块≤80字符 | 本任务草稿、无控制字符、目标一致 | 禁用 |
| `desktop.scroll` | up/down，1–3 tick | 当前明确安全控件 | 禁用 |
| `desktop.shortcut` | 规范化固定快捷键 | 仅草稿中的 Ctrl+A/Ctrl+F/Escape；不放行 Win+R/Enter/保存/粘贴 | 禁用 |
| `fixture.increment` | amount 1–3 | mode=test + host fixture context，固定 R1 | 只改本进程内存计数器 |

动作均绑定 `tool_call_id + task_id + generation`。Unknown tool、额外 `risk/approved/command` 字段在 JSON schema 层拒绝。网页、截图和模型响应不能提供 Scope 或本机审批 authority。

## 许可生命周期

`propose → persisted Step/Observation/Approval → local_ui decide → Permit → revalidate → consume → persisted tool.started → backend → ToolResult → independent Verification`。

默认审批 60 秒。每次使用核验具体参数、当前上下文摘要、任务代数和策略版本；观察最大年龄默认 2 秒。允许审批等待时刷新同一环境的观察，但上下文改变会暂停并撤销许可。批准后改参数、过期、重放、取消、焦点改变、撤销电脑权限、数据库错误均不得执行。

常见稳定拒绝码包括 `LOCAL_UI_REQUIRED`、`APPROVAL_EXPIRED`、`PERMIT_UNKNOWN_OR_CONSUMED`、`PERMIT_BINDING_MISMATCH`、`PERMIT_REVOKED`、`STALE_OBSERVATION`、`SELF_OPERATION`、`UNTRUSTED_WINDOW`、`COMPUTER_CONTROL_DISABLED`、`REAL_BACKEND_NOT_CONNECTED`。

M2 的真实路径还必须重新从 OS 验 HWND/PID/完整性/前台控件及文件目标，并用独立后置断言确认用户目标。这里的 Path 预检查不是抗同用户竞态的原子文件沙箱，不能直接拿它包装覆盖写入。
