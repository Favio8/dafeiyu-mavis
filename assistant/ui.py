"""Minimal readable Qt control centre: real records, local approval, persistent stop."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Slot, QSize, Signal
from PySide6.QtGui import QPalette, QColor, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea,
    QStackedWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QCheckBox,
    QListWidgetItem, QFrame, QGridLayout,
)

from pet.settings_widgets import SettingRow, SettingsCard
from pet.context_menus.icons import vector_widget_icon
from .branding import application_icon
from .ui_theme import stylesheet

LABELS = {
    "CREATED": "已建立", "INTERPRETING": "正在理解", "EXECUTING": "执行中",
    "WAITING_APPROVAL": "等待界面审批", "WAITING_CLARIFICATION": "等待澄清", "WAITING_USER": "等待接管",
    "VERIFYING": "正在验证", "PAUSING": "正在暂停", "PAUSED": "已暂停", "CANCEL_REQUESTED": "正在停止",
    "SUCCEEDED": "验证通过", "PARTIAL": "部分完成", "FAILED": "失败", "UNVERIFIED": "未验证",
    "CANCELLED": "已取消", "TIMED_OUT": "已超时", "INTERRUPTED": "已中断", "BLOCKED": "已阻止",
}


def label(text: str, role: str = "") -> QLabel:
    """Create wrapping, selectable, plain text; tool content is never interpreted as HTML."""
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    widget.setProperty("role", role)
    return widget


class ControlCenter(QWidget):
    """UI displays snapshots only; the controller thread owns all business state."""
    preview_requested = Signal()
    glow_changed = Signal(bool)

    def __init__(self, controller, stop, hotkey, *, dark=False):
        super().__init__()
        self.controller, self.stop, self.hotkey = controller, stop, hotkey
        self.dark = dark
        self.setObjectName("mavis")
        self.setWindowTitle("DaFeiYu Mavis · 控制中心")
        self.setStyleSheet(stylesheet(dark))
        self.setWindowIcon(application_icon())
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ADB3C2" if dark else "#657084"))
        self.setPalette(palette)
        available = self.screen().availableGeometry()
        self.setMinimumSize(min(720, available.width()), min(500, available.height()))
        self.resize(min(1040, int(available.width() * .9)), min(720, int(available.height() * .9)))
        self.approval_id = None
        self.latest = None
        self.exiting = False
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 20, 12, 16)
        side.setSpacing(16)
        identity = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(application_icon().pixmap(QSize(34, 34), self.devicePixelRatioF()))
        mark.setFixedSize(36, 36)
        identity.addWidget(mark)
        identity.addWidget(label("Mavis", "brand"))
        identity.addStretch()
        side.addLayout(identity)
        side.addWidget(label("大肥鱼 · 桌面助手", "muted"))
        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setAccessibleName("功能导航")
        self.nav.setIconSize(QSize(18, 18))
        names = ["助手概览", "任务记录", "语音与唤醒", "模型与连接", "电脑操作权限", "桌宠外观", "数据与隐私", "关于与诊断"]
        icons = ["application", "todo", "sound", "harness", "screen", "appearance", "file", "info"]
        for name, icon in zip(names, icons):
            rendered = vector_widget_icon(self, icon)
            accent_palette = self.palette()
            accent_palette.setColor(QPalette.ColorRole.WindowText, QColor("#ADC4FF" if dark else "#002FA7"))
            self.setPalette(accent_palette)
            selected = vector_widget_icon(self, icon)
            rendered.addPixmap(selected.pixmap(QSize(18, 18), self.devicePixelRatioF()), QIcon.Mode.Selected)
            self.setPalette(palette)
            item = QListWidgetItem(rendered, name)
            item.setSizeHint(QSize(168, 40))
            self.nav.addItem(item)
        side.addWidget(self.nav, 1)
        side.addWidget(label("本地任务记录\nCtrl+Alt+F12 急停", "muted"))
        root.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        top = QHBoxLayout(toolbar)
        top.setContentsMargins(24, 14, 24, 14)
        self.page_title = label(names[0], "brand")
        top.addWidget(self.page_title)
        top.addStretch(1)
        self.state = label("正在启动核心")
        self.state.setProperty("role", "badge")
        top.addWidget(self.state)
        self.stop_button = QPushButton("立即停止")
        self.stop_button.setProperty("role", "stop")
        self.stop_button.setAccessibleName("立即停止所有助手任务")
        self.stop_button.clicked.connect(self._stop_now)
        top.addWidget(self.stop_button)
        main.addWidget(toolbar)
        self.stack = QStackedWidget()
        main.addWidget(self.stack, 1)
        root.addLayout(main, 1)
        self._overview()
        self._history()
        notes = [
            ("语音与唤醒", "麦克风关闭。语音唤醒尚未接入。", "首版必须包含本地唤醒、VAD 与 ASR；当前文字入口只用于阶段调试。"),
            ("模型与连接", "默认供应商：DeepSeek", "连接和工具能力分别验证。测试只发送固定测试文本，可能产生 API 费用，不操作电脑。Key 通过本地凭据工具安全配置。"),
            ("电脑操作权限", "受限记事本操作 · 默认关闭", "只支持启动记事本，以及在本次助手新开的空白草稿中输入最多16个单行字符。不保存文件。其他窗口、删除、覆盖、shell 和管理员窗口均不支持。"),
            ("桌宠外观", "你的桌面伙伴", "右键桌宠可调整角色与外观。任务状态会通过桌宠气泡提示。"),
            ("数据与隐私", "任务记录只保存在本机", "SQLite 未加密；测试库与正式库分开。当前不采集音频、不保存截图、不发送遥测。API Key 只允许凭据库保存。"),
            ("关于与诊断", "开发阶段：M2 受限试验", "仅有受限记事本原生路径。完整 Windows-Use、网页、保存、视觉与语音端到端验收尚未通过。"),
        ]
        for title, status, description in notes:
            panel, layout = self._page(title)
            info = QWidget()
            info_box = QVBoxLayout(info)
            info_box.setContentsMargins(18, 16, 18, 16)
            info_box.addWidget(label(status, "brand"))
            info_box.addWidget(label(description, "muted"))
            layout.addWidget(SettingsCard([info]))
            if title == "模型与连接":
                self.model_result = label("连接认证：待验证　·　工具能力：待验证")
                layout.addWidget(self.model_result)
                buttons = QHBoxLayout()
                for caption, command in [("测试连接", "probe_connection"), ("测试工具调用", "probe_tools")]:
                    button = QPushButton(caption)
                    button.clicked.connect(lambda checked=False, cmd=command: self.controller.submit(cmd))
                    buttons.addWidget(button)
                layout.addLayout(buttons)
            if title == "电脑操作权限":
                self.native_scope = QCheckBox("允许上述记事本操作（仅本次运行）")
                self.native_scope.setEnabled(not controller.test_mode)
                self.native_scope.toggled.connect(self._native_scope_changed)
                layout.addWidget(SettingsCard([SettingRow("native_scope", "电脑操作授权", "首次开启先按 Ctrl+Alt+F12 测试，再在概览复位。撤销立即急停，不会恢复旧任务。", self.native_scope, stacked=True)]))
            if title == "桌宠外观":
                self.glow_toggle = QCheckBox("显示操作边缘流光（仅本次运行）")
                self.glow_toggle.setChecked(True)
                self.glow_toggle.toggled.connect(self.glow_changed.emit)
                layout.addWidget(SettingsCard([SettingRow("execution_glow", "操作提示", "真实动作执行时，屏幕四周呈现蓝、青、紫流光，中央透明。跟随 Windows 动画设置；急停时隐藏。", self.glow_toggle, stacked=True)]))
                self.preview_button = QPushButton("预览流光 · 4 秒")
                self.preview_button.clicked.connect(self._preview_glow)
                layout.addWidget(self.preview_button, alignment=Qt.AlignmentFlag.AlignLeft)
                self.preview_note = label("预览只展示效果，不操作电脑。", "muted")
                layout.addWidget(self.preview_note)
            layout.addStretch()
            self.stack.addWidget(panel)
        self.notice = label("Ctrl+Alt+F12：" + ("已注册" if hotkey.registered else "不可用（" + str(hotkey.error) + "）"), "muted")
        self.notice.setContentsMargins(24, 8, 24, 12)
        main.addWidget(self.notice)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(lambda index: self.page_title.setText(names[index]))
        self.nav.setCurrentRow(0)
        self._button_icons()
        controller.signals.snapshot.connect(self.update_snapshot, Qt.ConnectionType.QueuedConnection)
        controller.signals.details.connect(self.update_details, Qt.ConnectionType.QueuedConnection)
        controller.signals.error.connect(self.show_error, Qt.ConnectionType.QueuedConnection)
        self.stop_timer = QTimer(self)
        self.stop_timer.setInterval(100)
        self.stop_timer.timeout.connect(self._reflect_stop)
        self.stop_timer.start()

    def _button_icons(self):
        icons = {"立即停止": "stop", "发送指令": "send", "批准这一次": "thumbs_up", "拒绝": "thumbs_down", "暂停": "pause", "重新观察后恢复": "play", "复位急停": "retry", "测试连接": "web", "测试工具调用": "tools", "预览流光 · 4 秒": "appearance", "开始审批演练": "play", "挂起 worker 测急停": "stop"}
        for button in self.findChildren(QPushButton):
            if button.text() in icons:
                # Shared vectors use the palette; primary buttons need white strokes.
                palette = button.palette()
                palette.setColor(QPalette.ColorRole.WindowText, QColor("#FFFFFF" if button.property("role") == "primary" else "#ADB3C2" if self.dark else "#657084"))
                palette.setColor(QPalette.ColorRole.ButtonText, palette.color(QPalette.ColorRole.WindowText))
                button.setPalette(palette)
                button.setIcon(vector_widget_icon(button, icons[button.text()], 16))
                button.setIconSize(QSize(16, 16))
            if not button.accessibleName():
                button.setAccessibleName(button.text())

    def _preview_glow(self):
        if self.stop.event.is_set():
            self.preview_note.setText("急停已锁定；复位后可预览。")
            return
        if not self.glow_toggle.isChecked():
            self.preview_note.setText("先开启本次运行的边缘流光。")
            return
        self.preview_note.setText("正在预览 · 不操作电脑")
        self.preview_requested.emit()
        QTimer.singleShot(4100, self, lambda: self.preview_note.setText("预览结束；实际操作时自动显示。"))

    def _stop_now(self) -> None:
        self.stop.trip()
        self._reflect_stop()

    def _native_scope_changed(self, enabled: bool) -> None:
        if not enabled:
            self.stop.trip()
        self.controller.submit("native_scope", enabled)

    def _reflect_stop(self) -> None:
        if self.stop.event.is_set():
            self.state.setText("急停已锁定")
            self.allow.setEnabled(False)
            self.deny.setEnabled(False)

    def _page(self, title: str):
        wrapper = QWidget()
        wrapper.setObjectName("pageWrap")
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("pageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 16)
        layout.setSpacing(16)
        area.setWidget(content)
        outer.addWidget(area)
        return wrapper, layout

    def _overview(self) -> None:
        panel, layout = self._page("助手概览")
        summary = QGridLayout()
        summary.setSpacing(12)
        self.summary_values = []
        for column, (caption, value) in enumerate([("模型连接", "待验证"), ("电脑权限", "未授权"), ("语音唤醒", "未接入")]):
            card = QFrame()
            card.setObjectName("summaryCard")
            box = QVBoxLayout(card)
            box.setContentsMargins(14, 12, 14, 12)
            box.addWidget(label(caption, "muted"))
            item = label(value, "value")
            box.addWidget(item)
            self.summary_values.append(item)
            summary.addWidget(card, 0, column)
            summary.setColumnStretch(column, 1)
        layout.addLayout(summary)
        mode = "测试模式 · 仅验证核心，不操作电脑" if self.controller.test_mode else "受限指令：打开记事本 / 输入：<单行文字>"
        layout.addWidget(label(mode))
        layout.addWidget(label("文字备用入口", "brand"))
        self.input = QLineEdit()
        self.input.setMaxLength(4000)
        self.input.setPlaceholderText("文字备用入口；操作范围以权限页为准")
        self.input.setAccessibleName("文字备用指令")
        send = QPushButton("发送指令")
        send.setProperty("role", "primary")
        send.clicked.connect(lambda: self.controller.submit("record", self.input.text()))
        self.input.returnPressed.connect(send.click)
        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addWidget(send)
        layout.addLayout(row)
        if self.controller.test_mode:
            controls = QHBoxLayout()
            self.exercise = QPushButton("开始审批演练")
            self.exercise.clicked.connect(lambda: self.controller.submit("exercise"))
            self.exercise.setProperty("role", "primary")
            hang = QPushButton("挂起 worker 测急停")
            hang.clicked.connect(lambda: self.controller.submit("hang"))
            controls.addWidget(self.exercise)
            controls.addWidget(hang)
            layout.addLayout(controls)
        self.approval_text = label("没有待审批操作。")
        layout.addWidget(SettingsCard([SettingRow("mavis_approval", "动作审批", "只允许本机界面一次性批准；默认 60 秒。", self.approval_text, stacked=True)]))
        approval_buttons = QHBoxLayout()
        self.allow = QPushButton("批准这一次")
        self.allow.setProperty("role", "primary")
        self.deny = QPushButton("拒绝")
        for button, command in [(self.allow, "approve"), (self.deny, "deny")]:
            button.setEnabled(False)
            button.clicked.connect(lambda checked=False, cmd=command: self.controller.submit(cmd, self.approval_id))
            approval_buttons.addWidget(button)
        approval_buttons.addStretch()
        layout.addLayout(approval_buttons)
        controls = QHBoxLayout()
        for title, command in [("暂停", "pause"), ("重新观察后恢复", "resume"), ("复位急停", "reset")]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, cmd=command: self.controller.submit(cmd))
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.outcome = label("尚无任务。停止后，已经产生的影响会保留在记录中。", "muted")
        layout.addWidget(self.outcome)
        layout.addStretch()
        self.stack.addWidget(panel)

    def _history(self) -> None:
        panel, layout = self._page("任务记录")
        layout.addWidget(label("显示当前模式最近 50 条真实记录；点击查看有序事件与审批。", "muted"))
        self.history = QTreeWidget()
        self.history.setHeaderLabels(["指令", "状态", "来源"])
        self.history.setRootIsDecorated(False)
        self.history.setMinimumHeight(160)
        self.history.setAccessibleName("任务记录列表")
        self.history.itemSelectionChanged.connect(self._selection)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setAccessibleName("任务事件与审批详情")
        self.detail.setPlaceholderText("选择一条任务，查看执行、审批与验证详情。")
        layout.addWidget(self.history)
        layout.addWidget(self.detail)
        self.stack.addWidget(panel)

    def _selection(self) -> None:
        items = self.history.selectedItems()
        if items:
            self.controller.submit("details", items[0].data(0, Qt.ItemDataRole.UserRole))

    @Slot(object)
    def update_snapshot(self, snapshot: dict) -> None:
        """Render committed state only; never invent progress, successes or measurements."""
        self.latest = snapshot
        self.native_scope.blockSignals(True)
        self.native_scope.setChecked(snapshot.get("native_enabled",False))
        self.native_scope.blockSignals(False)
        checks = snapshot.get("provider_checks", {})
        self.model_result.setText("连接认证：" + checks.get("connection", "待验证") + "　·　工具能力：" + checks.get("tools", "待验证"))
        self.summary_values[0].setText(checks.get("connection", "待验证"))
        self.summary_values[1].setText("已授权" if snapshot.get("native_enabled") else "未授权")
        task, approval = snapshot["task"], snapshot["approval"]
        status = LABELS.get(task["status"], task["status"]) if task else "就绪"
        if task and task["mode"] == "live" and task["status"] == "EXECUTING" and snapshot.get("native_enabled"):
            status = "正在操作：记事本"
        self.state.setText("急停已锁定" if snapshot["stopped"] else status)
        self.approval_id = approval["id"] if approval else None
        self.allow.setEnabled(bool(approval) and not self.stop.event.is_set())
        self.deny.setEnabled(bool(approval) and not self.stop.event.is_set())
        expiry = datetime.fromisoformat(approval["expires_at"]).astimezone().strftime("%H:%M:%S") if approval else ""
        self.approval_text.setText("将把测试计数器增加 1。无文件、键鼠或网络副作用。\n有效至 " + expiry + "（本机时间）" if approval else "没有待审批操作。")
        if task:
            prefix = "测试记录 · " if task["mode"] == "test" else ""
            explanation = "\n电脑操作未授权，本条未执行。" if task["error_code"] == "COMPUTER_CONTROL_DISABLED" else ""
            if task["error_code"] and not explanation:
                explanation = "\n" + task["error_code"]
            self.outcome.setText(prefix + status + explanation + ("\n" + "\n".join(task["effects"]) if task["effects"] else ""))
        self.history.blockSignals(True)
        selected = self.history.selectedItems()
        selected_id = selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else None
        scroll = self.history.verticalScrollBar().value()
        self.history.clear()
        for record in snapshot["tasks"]:
            prefix = "[测试] " if record["mode"] == "test" else ""
            source = {"voice": "语音", "text": "文字", "manual_record": "手动记录"}.get(record["source"], record["source"])
            item = QTreeWidgetItem([prefix + record["title"], LABELS.get(record["status"], record["status"]), source])
            item.setData(0, Qt.ItemDataRole.UserRole, record["id"])
            item.setToolTip(0, record["final_text"])
            self.history.addTopLevelItem(item)
            if record["id"] == selected_id:
                self.history.setCurrentItem(item)
        self.history.setColumnWidth(0, max(180, self.history.width() - 220))
        self.history.verticalScrollBar().setValue(scroll)
        self.history.blockSignals(False)
        self._reflect_stop()

    @Slot(object)
    def update_details(self, details: dict) -> None:
        """Display untrusted text as plain text, with no links or executable markup."""
        lines = [f'{e["seq"]}. {e["type"]}\n{e["payload_redacted"]}' for e in details["events"]]
        lines.extend(f'审批：{a["status"]} / {a["decision_source"] or "未决定"}' for a in details["approvals"])
        self.detail.setPlainText("\n\n".join(lines))

    @Slot(str)
    def show_error(self, message: str) -> None:
        """Expose safe controller errors without a modal dialog blocking the stop button."""
        self.notice.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        """Closing hides the control centre; the tray and stop hotkey remain available."""
        if self.exiting:
            event.accept()
        else:
            self.hide()
            event.ignore()
