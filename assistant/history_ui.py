"""Live database-backed task search, details and local record actions."""
from __future__ import annotations


from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QTreeWidget, QTreeWidgetItem, QTextEdit, QTabWidget, QFileDialog,
    QMessageBox, QApplication, QSplitter, QCheckBox,
)

from .contracts import TERMINAL
from .history import HistoryQuery


def duration(record):
    value = record["duration_ms"]
    return (f"{value} ms" if value<1000 else f"{value/1000:.1f} 秒") if value is not None else "计时中" if record["status"] not in TERMINAL else "未提供"


def detail_text(value, technical=False):
    from .ui import LABELS
    task = value["task"]
    lines = [f"{task['title']} · {LABELS.get(task['status'], task['status'])}", f"任务 ID：{task['id']}",
        f"来源：{ {'voice': '语音', 'text': '文字', 'manual_record': '手动记录'}[task['source']]}　总时长：{duration(task)}", f"创建（UTC）：{task['created_at']}　结束（UTC）：{task['finished_at'] or '尚未结束'}",
        f"模型配置快照：{task['provider']['model']}　实际模型轮数：{task['llm_round_count']}",
        f"操作：{task['action_count']}　工具调用：{task['tool_call_count']}",
        "输入/输出 Tokens：" + str(task['input_tokens'] if task['input_tokens'] is not None else '未提供') + " / " + str(task['output_tokens'] if task['output_tokens'] is not None else '未提供'),
        "费用：" + (str(task['cost_estimate']) if task['cost_estimate'] is not None else "未提供"),
        "\n原始指令\n"+task['original_text'], "\n最终指令\n"+task['final_text'], "\n目标"]
    lines.extend(f"{g['id']} · {g['description']} · {g['predicate']}" for g in task['goals'])
    if task.get("parent_task_id"):
        lines.append("重新运行自："+task["parent_task_id"])
    lines.append("\n实际副作用")
    lines.extend(task["effects"] or ["没有已记录的副作用；不代表未知效果已撤销。"])
    lines.append("\n验证与证据 · "+task["verification_status"])
    for result in value["verifications"]:
        lines.append(f"{result['goal_id']} · {result['method']} · {result['result']}\n{result['evidence']}")
    if not value["verifications"]:
        lines.append("没有验证记录。")
    if task["error_code"]:
        lines.append("\n错误\n"+task["error_code"])
    lines.append("\n事件时间线")
    event_labels = {"task.created": "建立任务", "task.configuration": "配置快照", "task.state_changed": "状态变化", "task.finished": "任务结束", "task.route": "指令分流", "tool.proposed": "提出动作", "tool.started": "开始动作", "tool.finished": "工具返回", "verification.finished": "验证完成", "approval.decided": "审批决定", "approval.expired": "审批过期", "native.error": "操作错误"}
    lines.extend(f"{e['seq']}. {e['timestamp_utc']} · {event_labels.get(e['type'], e['type'])}"+("\n"+e['payload_redacted'] if technical else "") for e in value['events'])
    lines.append("\n工具与脱敏参数")
    lines.extend(f"{s['seq']}. {s['tool_name']} · {s['status']} · {s['risk']}"+("\n"+s['args_redacted'] if technical else "") for s in value['steps'])
    lines.append("\n审批")
    approval_labels = {"pending": "等待审批", "approved": "已批准", "denied": "已拒绝", "expired": "已过期", "consumed": "已消耗", "revoked": "已撤销"}
    lines.extend(f"{a['id']} · {approval_labels[a['status']]} / {a['decision_source'] or '未决定'}\n动作 {a['tool_call_id']} · 到期 {a['expires_at']}" for a in value['approvals'])
    return "\n\n".join(lines)


class HistoryPanel(QWidget):
    def __init__(self, controller):
        super().__init__()
        from .ui import LABELS
        self.controller = controller
        self.page, self.version = 0, 0
        self._inflight = False
        self._dirty = True
        self._stamp = None
        self.rows = {}
        self.selected_details = None
        self.setObjectName("pageContent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 16)
        filters = QGridLayout()
        self.keyword = QLineEdit()
        self.keyword.setMaxLength(200)
        self.keyword.setPlaceholderText("搜索指令、步骤与验证证据")
        self.keyword.setAccessibleName("全文搜索任务记录")
        filters.addWidget(self.keyword, 0, 0, 1, 3)
        self.status = QComboBox()
        self.status.addItem("全部状态", None)
        for code, caption in LABELS.items():
            self.status.addItem(caption, code)
        self.source = QComboBox()
        for caption, value in [("全部来源", None), ("语音", "voice"), ("文字", "text"), ("手动记录", "manual_record")]:
            self.source.addItem(caption, value)
        self.days = QComboBox()
        for days in (7, 30, 90, 0):
            self.days.addItem(f"近 {days} 天" if days else "全部时间", days)
        for column, (name, widget) in enumerate([("按任务状态筛选", self.status), ("按任务来源筛选", self.source), ("按时间范围筛选", self.days)]):
            widget.setAccessibleName(name)
            filters.addWidget(widget, 1, column)
            widget.currentIndexChanged.connect(self._filters_changed)
        self.keyword.textChanged.connect(self._filters_changed)
        layout.addLayout(filters)
        self.counter = QLabel("正在读取本地数据库……")
        self.counter.setWordWrap(True)
        layout.addWidget(self.counter)
        self.technical = QCheckBox("展开工具参数与完整事件")
        self.technical.setAccessibleName("展开任务技术详情，默认折叠")
        self.technical.toggled.connect(lambda enabled: self.detail.setPlainText(detail_text(self.selected_details, enabled)) if self.selected_details else None)
        layout.addWidget(self.technical)
        self.tabs = QTabWidget()
        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.history = QTreeWidget()
        self.history.setHeaderLabels(["指令", "状态", "来源", "总时长", "任务 ID", "模型", "操作"])
        self.history.setRootIsDecorated(False)
        self.history.setAccessibleName("任务记录列表")
        self.history.itemSelectionChanged.connect(self._selection)
        self.history.setMinimumHeight(120)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setAccessibleName("任务详情、事件、审批与验证证据")
        self.detail.setPlaceholderText("选择一条真实记录，查看指令、步骤、审批与验证。")
        splitter.addWidget(self.history)
        splitter.addWidget(self.detail)
        splitter.setSizes([240, 240])
        task_layout.addWidget(splitter)
        self.tabs.addTab(task_page, "任务")
        self.voice_attempts = QTreeWidget()
        self.voice_attempts.setHeaderLabels(["唤醒词", "结果", "时长 ms"])
        self.voice_attempts.setRootIsDecorated(False)
        self.voice_attempts.setAccessibleName("语音尝试记录，单独统计")
        self.tabs.addTab(self.voice_attempts, "语音尝试")
        self.tabs.currentChanged.connect(self._switch_kind)
        self.voice_attempts.itemSelectionChanged.connect(self._selection)
        layout.addWidget(self.tabs, 1)
        pagination = QHBoxLayout()
        self.previous = QPushButton("上一页")
        self.next = QPushButton("下一页")
        self.previous.clicked.connect(lambda: self._page(-1))
        self.next.clicked.connect(lambda: self._page(1))
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        pagination.addWidget(self.previous)
        pagination.addWidget(self.next)
        pagination.addWidget(refresh)
        pagination.addStretch()
        layout.addLayout(pagination)
        actions = QGridLayout()
        self.rerun = QPushButton("重新运行")
        self.rerun.clicked.connect(self._rerun)
        copy = QPushButton("复制最终指令")
        copy.clicked.connect(self._copy)
        export = QPushButton("导出当前页")
        export.clicked.connect(self._export)
        self.delete = QPushButton("删除选中记录")
        self.delete.clicked.connect(self._delete)
        for index, button in enumerate((self.rerun, copy, export, self.delete)):
            actions.addWidget(button, index//2, index%2)
        layout.addLayout(actions)
        for button in self.findChildren(QPushButton):
            button.setAccessibleName(button.text())
        self.rerun.setEnabled(False)
        self.delete.setEnabled(False)
        controller.signals.history.connect(self.update_history, Qt.ConnectionType.QueuedConnection)
        controller.signals.details.connect(self.update_details, Qt.ConnectionType.QueuedConnection)
        controller.signals.snapshot.connect(self.update_live, Qt.ConnectionType.QueuedConnection)
        controller.signals.result.connect(self._result, Qt.ConnectionType.QueuedConnection)
        controller.signals.error.connect(self._error, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._query)
        self.timer.start()

    def query(self):
        return HistoryQuery.from_mapping({"kind": "voice" if self.tabs.currentIndex() else "task", "keyword": self.keyword.text().strip(), "status": self.status.currentData(), "source": self.source.currentData(), "days": self.days.currentData(), "page": self.page, "request": self.version}).model_dump(mode="json")

    def _switch_kind(self, index):
        from .ui import LABELS
        self.status.blockSignals(True)
        self.status.clear()
        self.status.addItem("全部结果" if index else "全部状态", None)
        labels = {"command": "有效指令", "no_speech": "无有效语音", "empty": "空指令/取消", "error": "错误", "busy_ignored": "忙碌未排队"} if index else LABELS
        for code, caption in labels.items():
            self.status.addItem(caption, code)
        self.status.blockSignals(False)
        self.source.setCurrentIndex(0)
        self.source.setEnabled(not index)
        self._filters_changed()
        self._selection()

    def _filters_changed(self, *_):
        self.page = 0
        self.version += 1
        self._dirty = True
        self.counter.setText("正在按当前条件查询……")

    def refresh(self):
        self.version += 1
        self._dirty = True

    def _page(self, offset):
        self.page = max(0, self.page+offset)
        self.refresh()

    def _query(self):
        if self._dirty and not self._inflight and not self.controller.closed.is_set():
            self._dirty, self._inflight = False, True
            self.controller.submit("query_history", self.query())

    def update_history(self, result):
        self._inflight = False
        if result["request"] != self.version:
            return
        if result.get("error"):
            self.counter.setText("查询失败："+result["error"]+"；可刷新重试。")
            return
        total = result["total"]
        if self.page and self.page*50 >= total:
            self.page = max(0, (total-1)//50)
            self.refresh()
            return
        if result.get("kind") == "voice":
            self.voice_attempts.blockSignals(True)
            self.voice_attempts.clear()
            labels = {"command": "有效指令", "no_speech": "无有效语音", "empty": "空指令/取消", "error": "错误", "busy_ignored": "忙碌未排队"}
            for attempt in result["rows"]:
                item = QTreeWidgetItem([attempt["wakeword"], labels[attempt["result"]], str(attempt["audio_duration_ms"])])
                item.setData(0, Qt.ItemDataRole.UserRole, attempt["id"])
                item.setToolTip(0, attempt["id"]+"\n"+attempt["started_at"])
                self.voice_attempts.addTopLevelItem(item)
            self.voice_attempts.blockSignals(False)
            self.counter.setText(f"{total} 条语音尝试 · 第 {self.page+1} 页 · 不计入任务成功率" if total else "当前条件下尚无语音尝试。")
            self.previous.setEnabled(self.page>0)
            self.next.setEnabled((self.page+1)*50<total)
            self._selection()
            return
        selected = self.selected_id()
        self.rows = {r["id"]: r for r in result["rows"]}
        self.history.blockSignals(True)
        self.history.clear()
        from .ui import LABELS
        from PySide6.QtGui import QColor, QPalette
        dark = self.palette().color(QPalette.ColorRole.WindowText).lightness()>128
        for record in result["rows"]:
            source = {"voice": "语音", "text": "文字", "manual_record": "手动记录"}[record["source"]]
            item = QTreeWidgetItem([("[测试] " if record["mode"] == "test" else "")+record["title"], LABELS.get(record["status"], record["status"]), source, duration(record), record["id"], record["provider"]["model"], str(record["action_count"])])
            item.setData(0, Qt.ItemDataRole.UserRole, record["id"])
            item.setToolTip(0, record["final_text"])
            color = ("#6FD3A0" if dark else "#18794E") if record["status"] == "SUCCEEDED" and record["verification_status"] == "passed" else ("#FF9A9A" if dark else "#B42336") if record["status"] in {"FAILED", "BLOCKED"} else ("#ADB3C2" if dark else "#657084")
            item.setForeground(1, QColor(color))
            self.history.addTopLevelItem(item)
            if record["id"] == selected:
                self.history.setCurrentItem(item)
        self.history.blockSignals(False)
        self.counter.setText(f"{total} 条匹配任务 · 第 {self.page+1} 页 · 每页 50 条" if total else "当前筛选条件没有匹配任务。" if self.keyword.text().strip() or self.status.currentData() or self.source.currentData() else "当前时间范围尚无任务，完成一次指令后会出现在这里。")
        self.previous.setEnabled(self.page>0)
        self.next.setEnabled((self.page+1)*50 < total)
        if selected not in self.rows:
            self.selected_details = None
            self.detail.clear()
        self._selection()

    def selected_id(self):
        items = self.history.selectedItems()
        return items[0].data(0, Qt.ItemDataRole.UserRole) if items else None

    def _selection(self, *_):
        if self.tabs.currentIndex() == 1:
            self.rerun.setEnabled(False)
            self.delete.setEnabled(bool(self.voice_attempts.selectedItems()))
            return
        record = self.rows.get(self.selected_id())
        ended = bool(record and record["status"] in TERMINAL)
        self.rerun.setEnabled(ended)
        self.delete.setEnabled(bool(self.voice_attempts.selectedItems()) if self.tabs.currentIndex() == 1 else ended)
        self.delete.setToolTip("活动任务不能直接删除" if record and not ended else "只删除本地记录，不撤销实际操作")
        if record:
            self.controller.submit("details", record["id"])

    def update_details(self, details):
        if details["task"]["id"] == self.selected_id():
            self.selected_details = details
            self.detail.setPlainText(detail_text(details, self.technical.isChecked()))

    def update_live(self, snapshot):
        task = snapshot["task"]
        stamp = (task["id"], task["status"], task["action_count"], task["tool_call_count"]) if task else None
        stamp = (stamp, snapshot.get("counts", {}), len(snapshot.get("voice_attempts", [])))
        if stamp != self._stamp:
            self._stamp = stamp
            self._dirty = True

    def _rerun(self):
        record = self.rows.get(self.selected_id())
        if record and record["status"] in TERMINAL:
            self.controller.submit("rerun", record["id"])

    def _copy(self):
        record = self.rows.get(self.selected_id())
        if record:
            QApplication.clipboard().setText(record["final_text"])

    def _delete(self):
        kind = "voice" if self.tabs.currentIndex() == 1 else "task"
        items = self.voice_attempts.selectedItems() if kind == "voice" else self.history.selectedItems()
        if items and QMessageBox.question(self, "删除本地记录", "删除选中的本地记录及关联信息？实际电脑操作的影响不会撤销。") == QMessageBox.StandardButton.Yes:
            self.controller.submit("delete_record", {"id": items[0].data(0, Qt.ItemDataRole.UserRole), "kind": kind})

    def _export(self):
        path, selected = QFileDialog.getSaveFileName(self, "导出当前筛选页，最多50条", "mavis-records.json", "JSON (*.json);;Markdown (*.md)")
        if path:
            self.controller.submit("export_history", {"path": path, "format": "markdown" if "Markdown" in selected else "json", "query": self.query()})

    def _result(self, result):
        if result["kind"] in {"delete_record", "clear_records"}:
            self.refresh()

    def _error(self, message):
        if self._inflight or message.startswith("控制器已停止"):
            self._inflight = False
            self.counter.setText("记录暂未更新："+message)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        for column in (4, 5, 6):
            self.history.setColumnHidden(column, self.width()<850)
        self.history.setColumnWidth(0, max(130, self.width()//3))
