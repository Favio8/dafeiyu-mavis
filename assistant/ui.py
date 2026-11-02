"""Minimal readable Qt control centre: real records, local approval, persistent stop."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Slot, QSize, Signal
from PySide6.QtGui import QPalette, QColor, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea,
    QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QCheckBox,
    QListWidgetItem, QFrame, QGridLayout, QMenu,
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
    avoid_changed = Signal(bool)
    hotkeys_requested = Signal(str, str)
    pet_action = Signal(str)
    hide_notice = Signal(str)
    manual_record_requested = Signal()

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
        self._settings_loaded = False
        self._close_notice_sent = False
        self._manual_collapsed = False
        self._voice_status = "未挂载"
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        self.sidebar = sidebar
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
        self.brand_name = identity.itemAt(1).widget()
        identity.addStretch()
        side.addLayout(identity)
        self.side_subtitle = label("大肥鱼 · 桌面助手", "muted")
        side.addWidget(self.side_subtitle)
        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setAccessibleName("功能导航")
        self.nav.setIconSize(QSize(18, 18))
        names = ["助手概览", "任务记录", "语音与唤醒", "模型与连接", "电脑操作权限", "桌宠外观", "数据与隐私", "关于与诊断"]
        self.nav_names = names
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
            item.setToolTip(name)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, name)
            self.nav.addItem(item)
        side.addWidget(self.nav, 1)
        self.side_footer = label("本地任务记录", "muted")
        side.addWidget(self.side_footer)
        root.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        top = QHBoxLayout(toolbar)
        top.setContentsMargins(24, 14, 24, 14)
        self.nav_toggle = QPushButton()
        self.nav_toggle.setIcon(vector_widget_icon(self, "sidebar", 18))
        self.nav_toggle.setAccessibleName("展开或收起功能导航")
        self.nav_toggle.setToolTip("功能导航")
        self.nav_toggle.clicked.connect(self._toggle_nav)
        top.addWidget(self.nav_toggle)
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
        from .control_pages import ModelPage, DataPage, AboutPage
        voice_placeholder, voice_layout = self._page("语音与唤醒")
        voice_layout.addWidget(label("正在挂载语音组件；麦克风保持关闭。", "muted"))
        voice_layout.addStretch()
        self.stack.addWidget(voice_placeholder)
        self.model_page = ModelPage(controller)
        self.model_result = self.model_page.result
        self.stack.addWidget(self.model_page)
        self._permissions()
        self._appearance()
        self.data_page = DataPage(controller)
        self.data_page.navigate.connect(self.nav.setCurrentRow)
        self.stack.addWidget(self.data_page)
        self.about_page = AboutPage(controller)
        self.about_page.reopen_guide.connect(self._reopen_guide)
        self.stack.addWidget(self.about_page)
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
        controller.signals.settings_saved.connect(self._apply_settings, Qt.ConnectionType.QueuedConnection)
        controller.signals.result.connect(self._local_result, Qt.ConnectionType.QueuedConnection)
        self.stop_timer = QTimer(self)
        self.stop_timer.setInterval(100)
        self.stop_timer.timeout.connect(self._reflect_stop)
        self.stop_timer.start()
        self.setMinimumWidth(min(560, available.width()))
        self._layout_nav()

    def _button_icons(self):
        icons = {"立即停止": "stop", "发送指令": "send", "批准这一次": "thumbs_up", "拒绝": "thumbs_down", "暂停": "pause", "重新观察后恢复": "play", "复位急停": "retry", "测试连接": "web", "测试工具调用": "tools", "预览流光 · 4 秒": "appearance", "开始审批演练": "play", "挂起 worker 测急停": "stop"}
        icons.update({"配置": "settings", "稍后": "more", "开始录音": "sound", "刷新": "retry", "上一页": "back", "下一页": "play",
            "重新运行": "retry", "复制最终指令": "copy", "导出当前页": "download", "删除选中记录": "clear",
            "保存模型配置": "save", "保存凭据": "save", "删除凭据": "clear", "保存并注册快捷键": "save",
            "打开桌宠原生设置": "settings", "显示桌宠": "pet", "隐藏桌宠": "hide", "保存保留期限": "save",
            "筛选并导出任务记录": "file", "清空本地记录…": "clear", "生成脱敏诊断预览": "info", "导出预览中的诊断包": "download",
            "重新打开首次引导": "info", "检查已安装组件": "tools", "查看随包许可说明": "file"})
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

    def install_voice(self, host):
        from .voice_ui import VoicePanel
        old = self.stack.widget(2)
        self.stack.removeWidget(old)
        old.deleteLater()
        self.voice_panel = VoicePanel(host, self.controller)
        self.stack.insertWidget(2, self.voice_panel)
        host.changed.connect(self._voice_health)
        self.manual_record_requested.connect(lambda: host.record("button"))
        self._voice_health(host.state)
        self.summary_values[2].setText("已关闭")
        self._button_icons()

    def _voice_health(self, value):
        self._voice_status = {"OFF": "已关闭", "ARMED": "等待唤醒", "CAPTURING": "录音中", "TRANSCRIBING": "识别中", "PLAYBACK_GUARD": "播报保护", "ERROR": "不可用", "LOADING": "加载中"}.get(value["state"], value["state"])
        self.summary_values[2].setText(self._voice_status)
        models_ready = bool(value.get("models")) and all(s == "ready" for s in value["models"].values())
        ready = bool(value.get("devices")) and models_ready
        self.record_button.setEnabled(ready)
        self.record_button.setToolTip("开始本地录音" if ready else "请在语音页连接麦克风并准备模型")
        prefix = "已跳过 · " if self.latest and "voice" in self.latest.get("settings", {}).get("skipped", []) else ""
        self.guide_status["voice"].setText(prefix+("可校准" if ready else "未发现麦克风" if value.get("devices_checked") and not value.get("devices") else "语音模型或设备未就绪"))

    def _toggle_nav(self):
        if self.width() < 860:
            menu = QMenu(self)
            for index, name in enumerate(self.nav_names):
                entry = menu.addAction(self.nav.item(index).icon(), name)
                entry.triggered.connect(lambda checked=False, i=index: self.nav.setCurrentRow(i))
            menu.exec(self.nav_toggle.mapToGlobal(self.nav_toggle.rect().bottomLeft()))
        else:
            self._manual_collapsed = not self._manual_collapsed
            self._layout_nav()

    def _layout_nav(self):
        compact = self.width() < 860 or self._manual_collapsed
        self.sidebar.setFixedWidth(64 if compact else 200)
        self.sidebar.layout().setContentsMargins(8 if compact else 12, 20, 8 if compact else 12, 16)
        for widget in (self.brand_name, self.side_subtitle, self.side_footer):
            widget.setVisible(not compact)
        for index, name in enumerate(self.nav_names):
            self.nav.item(index).setText("" if compact else name)
            self.nav.item(index).setSizeHint(QSize(40 if compact else 168, 40))

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "nav_names"):
            self._layout_nav()

    def _permissions(self):
        from .control_pages import action
        panel, layout = self._page("电脑操作权限")
        layout.addWidget(label("操作范围与急停", "brand"))
        self.native_scope = QCheckBox("允许本次运行的记事本操作")
        self.native_scope.setEnabled(not self.controller.test_mode)
        self.native_scope.toggled.connect(self._native_scope_changed)
        self.native_scope.setToolTip("首次开启先物理测试急停并复位；撤销立即停止新动作")
        layout.addWidget(SettingsCard([SettingRow("native_scope", "受控电脑操作", "当前执行器仅支持启动记事本、在本次新开的空白草稿中输入最多16个单行字符。不保存文件；其他窗口、shell、管理员窗口不在支持范围。", self.native_scope, stacked=True)]))
        layout.addWidget(label("网页域名与文件目录工具尚未接入，当前不能配置或授权这些范围。", "muted"))
        self.emergency_edit = QLineEdit()
        self.recording_edit = QLineEdit()
        layout.addWidget(SettingsCard([
            SettingRow("emergency_shortcut", "急停快捷键", "Ctrl+Alt+F1～F12、字母或 Space。任务结束后可更换；新组合须实际注册成功。", self.emergency_edit, stacked=True),
            SettingRow("recording_shortcut", "录音快捷键", "录音快捷键冲突时可使用录音按钮，不会静默抢占。", self.recording_edit, stacked=True),
        ]))
        layout.addWidget(action("保存并注册快捷键", lambda: self.hotkeys_requested.emit(self.emergency_edit.text().strip(), self.recording_edit.text().strip())))
        self.hotkey_state = label("正在读取热键状态……", "muted")
        layout.addWidget(self.hotkey_state)
        layout.addStretch()
        self.stack.addWidget(panel)

    def _appearance(self):
        from .control_pages import action
        panel, layout = self._page("桌宠外观")
        self.pet_summary = label("正在挂载桌宠宿主……", "brand")
        layout.addWidget(self.pet_summary)
        layout.addWidget(label("角色、大小、透明度、位置、漫游与动作预览由桌宠原有设置管理。", "muted"))
        self.pet_buttons = []
        for caption, command in [("打开桌宠原生设置", "settings"), ("显示桌宠", "show"), ("隐藏桌宠", "hide")]:
            button = action(caption, lambda checked=False, cmd=command: self.pet_action.emit(cmd))
            button.setEnabled(False)
            self.pet_buttons.append(button)
            layout.addWidget(button)
        self.glow_toggle = QCheckBox("显示操作边缘流光")
        self.glow_toggle.setChecked(True)
        self.glow_toggle.toggled.connect(self.glow_changed.emit)
        self.glow_toggle.toggled.connect(lambda enabled: self.controller.submit("settings_patch", {"execution_glow": enabled}))
        self.avoid_toggle = QCheckBox("执行电脑操作时临时让出桌面")
        self.avoid_toggle.setChecked(True)
        self.avoid_toggle.toggled.connect(self.avoid_changed.emit)
        self.avoid_toggle.toggled.connect(lambda enabled: self.controller.submit("settings_patch", {"avoid_target": enabled}))
        layout.addWidget(SettingsCard([
            SettingRow("execution_glow", "操作边缘提示", "真实派发动作后显示；中央透明，急停时隐藏。", self.glow_toggle, stacked=True),
            SettingRow("avoid_target", "工作时让路", "仅临时抑制桌宠的绘制和命中，不修改角色、位置或动画资源。", self.avoid_toggle, stacked=True),
        ]))
        self.preview_button = action("预览流光 · 4 秒", self._preview_glow)
        layout.addWidget(self.preview_button)
        self.preview_note = label("预览只展示效果，不操作电脑。", "muted")
        layout.addWidget(self.preview_note)
        layout.addStretch()
        self.stack.addWidget(panel)

    def update_pet(self, info):
        available = info.get("available", False)
        self.pet_summary.setText(info.get("summary", "仅运行控制中心，桌宠宿主未启动"))
        for button in self.pet_buttons:
            button.setEnabled(available)
            button.setToolTip("使用原桌宠交互与配置" if available else "以完整桌宠模式启动后可用")

    def _apply_settings(self, settings):
        for key, widget in [("execution_glow", self.glow_toggle), ("avoid_target", self.avoid_toggle)]:
            widget.blockSignals(True)
            widget.setChecked(settings[key])
            widget.blockSignals(False)
        self.glow_changed.emit(settings["execution_glow"])
        self.avoid_changed.emit(settings["avoid_target"])
        self.emergency_edit.setText(settings["emergency_shortcut"])
        self.recording_edit.setText(settings["recording_shortcut"])
        self.guide.setVisible(not settings["onboarding_done"])
        self._settings_loaded = True

    def _skip_guide(self, key):
        if self.latest:
            skipped = set(self.latest["settings"]["skipped"])
            skipped.add(key)
            self.controller.submit("settings_patch", {"skipped": sorted(skipped)})

    def _reopen_guide(self):
        self.nav.setCurrentRow(0)
        self.controller.submit("settings_patch", {"onboarding_done": False})

    def _local_result(self, value):
        if value.get("message"):
            self.notice.setText(value["message"])

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
        for column, (caption, value) in enumerate([("模型连接", "待验证"), ("电脑权限", "未授权"), ("语音唤醒", "未检查")]):
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
        guide_content = QWidget()
        guide_box = QVBoxLayout(guide_content)
        guide_box.setContentsMargins(16, 14, 16, 14)
        guide_box.addWidget(label("开始使用", "brand"))
        guide_box.addWidget(label("模型、语音和操作权限可分别跳过，桌宠可以独立使用。", "muted"))
        self.guide_status = {}
        for key, caption, page_index in [("model", "模型与凭据", 3), ("voice", "语音设备与模型", 2), ("permissions", "电脑操作授权", 4)]:
            row = QGridLayout()
            row.addWidget(label(caption), 0, 0)
            state = label("正在检查……", "muted")
            self.guide_status[key] = state
            row.addWidget(state, 1, 0)
            configure = QPushButton("配置")
            configure.clicked.connect(lambda checked=False, i=page_index: self.nav.setCurrentRow(i))
            skip = QPushButton("稍后")
            skip.clicked.connect(lambda checked=False, k=key: self._skip_guide(k))
            row.addWidget(configure, 0, 1, 2, 1)
            row.addWidget(skip, 0, 2, 2, 1)
            guide_box.addLayout(row)
        continue_pet = QPushButton("暂以桌宠模式继续")
        continue_pet.clicked.connect(self._continue_pet)
        guide_box.addWidget(continue_pet)
        self.guide = SettingsCard([guide_content])
        layout.addWidget(self.guide)
        mode = "测试模式 · 仅验证核心，不操作电脑" if self.controller.test_mode else "受限指令：打开记事本 / 输入：<单行文字>"
        layout.addWidget(label(mode))
        self.record_button = QPushButton("开始录音")
        self.record_button.setEnabled(False)
        self.record_button.setToolTip("等待语音组件挂载和麦克风就绪")
        self.record_button.clicked.connect(lambda: self.manual_record_requested.emit())
        layout.addWidget(self.record_button, alignment=Qt.AlignmentFlag.AlignLeft)
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
        layout.addWidget(label("最近记录", "brand"))
        self.recent_records = QTreeWidget()
        self.recent_records.setHeaderLabels(["指令", "状态", "来源"])
        self.recent_records.setRootIsDecorated(False)
        self.recent_records.setAccessibleName("最近五条真实任务记录")
        self.recent_records.setMaximumHeight(160)
        self.recent_records.itemActivated.connect(lambda item, column: self.nav.setCurrentRow(1))
        layout.addWidget(self.recent_records)
        layout.addStretch()
        self.stack.addWidget(panel)

    def _history(self) -> None:
        from .history_ui import HistoryPanel
        self.history_panel = HistoryPanel(self.controller)
        self.history = self.history_panel.history
        self.detail = self.history_panel.detail
        self.voice_attempts = self.history_panel.voice_attempts
        self.history_tabs = self.history_panel.tabs
        self.stack.addWidget(self.history_panel)

    def _selection(self) -> None:
        items = self.history.selectedItems()
        if items:
            self.controller.submit("details", items[0].data(0, Qt.ItemDataRole.UserRole))

    @Slot(object)
    def update_snapshot(self, snapshot: dict) -> None:
        """Render committed state only; never invent progress, successes or measurements."""
        self.latest = snapshot
        if not self._settings_loaded and snapshot.get("settings"):
            self._apply_settings(snapshot["settings"])
        self.native_scope.blockSignals(True)
        self.native_scope.setChecked(snapshot.get("native_enabled",False))
        self.native_scope.blockSignals(False)
        checks = snapshot.get("provider_checks", {})
        self.summary_values[0].setText(checks.get("connection", "待验证"))
        self.summary_values[1].setText("已授权" if snapshot.get("native_enabled") else "未授权")
        task, approval = snapshot["task"], snapshot["approval"]
        status = LABELS.get(task["status"], task["status"]) if task else "受限指令就绪" if snapshot.get("native_enabled") else "桌宠模式" if snapshot.get("settings", {}).get("onboarding_done") else "待配置"
        if task and task["mode"] == "live" and task["status"] == "EXECUTING" and snapshot.get("native_enabled"):
            status = "正在操作：记事本"
        self.state.setText("急停已锁定" if snapshot["stopped"] else status)
        self.approval_id = approval["id"] if approval else None
        self.allow.setEnabled(bool(approval) and not self.stop.event.is_set())
        self.deny.setEnabled(bool(approval) and not self.stop.event.is_set())
        expiry = datetime.fromisoformat(approval["expires_at"]).astimezone().strftime("%H:%M:%S") if approval else ""
        step = snapshot.get("approval_step")
        self.approval_text.setText(("操作："+step["tool_name"]+" · "+step["risk"]+"\n脱敏参数："+step["args_redacted"]+"\n有效至 "+expiry+"（本机时间）") if step else "有待审批操作，正在读取动作详情。" if approval else "没有待审批操作。")
        if task:
            prefix = "测试记录 · " if task["mode"] == "test" else ""
            explanation = "\n电脑操作未授权，本条未执行。" if task["error_code"] == "COMPUTER_CONTROL_DISABLED" else ""
            if task["error_code"] and not explanation:
                explanation = "\n" + task["error_code"]
            self.outcome.setText(prefix + status + explanation + ("\n" + "\n".join(task["effects"]) if task["effects"] else ""))
        self._update_overview(snapshot)
        self._reflect_stop()

    def _update_overview(self, snapshot):
        task = snapshot["task"]
        if task:
            from .history_ui import duration
            self.outcome.setText("当前任务："+task["title"]+"\n"+LABELS.get(task["status"], task["status"])+" · "+duration(task)+f" · 操作 {task['action_count']} 次 · 验证 {task['verification_status']}"+("\n"+"\n".join(task["effects"]) if task["effects"] else "")+("\n"+task["error_code"] if task["error_code"] else ""))
            if task["error_code"] == "COMPUTER_CONTROL_DISABLED":
                self.outcome.setText(self.outcome.text()+"\n电脑操作未授权，本条未执行。请先在权限页配置。")
        else:
            self.outcome.setText("当前没有任务。开始一次指令后，执行和验证状态会在这里显示。")
        settings = snapshot.get("settings", {})
        skipped = settings.get("skipped", [])
        self.guide_status["model"].setText(("已跳过 · " if "model" in skipped else "")+snapshot.get("credential_state", "未检查")+" · "+snapshot.get("provider_checks", {}).get("connection", "待验证"))
        self.guide_status["permissions"].setText(("已跳过 · " if "permissions" in skipped else "")+("本次已授权" if snapshot.get("native_enabled") else "未授权"))
        if "voice" in skipped and not self.guide_status["voice"].text().startswith("已跳过"):
            self.guide_status["voice"].setText("已跳过 · "+self.guide_status["voice"].text())
        self.recent_records.clear()
        for record in snapshot["tasks"][:5]:
            self.recent_records.addTopLevelItem(QTreeWidgetItem([record["title"], LABELS.get(record["status"], record["status"]), {"voice": "语音", "text": "文字", "manual_record": "手动"}[record["source"]]]))

    def _continue_pet(self):
        self.stop.trip()
        if not self.controller.test_mode:
            self.controller.submit("native_scope", False)
        self.controller.submit("settings_patch", {"onboarding_done": True})

    @Slot(object)
    def update_details(self, details: dict) -> None:
        """Display untrusted text as plain text, with no links or executable markup."""
        self.history_panel.update_details(details)

    @Slot(str)
    def show_error(self, message: str) -> None:
        """Expose safe controller errors without a modal dialog blocking the stop button."""
        self.notice.setText(message)
        if message.startswith("控制器已停止"):
            self.state.setText("核心不可用")
            self.data_page.usage.setText("记录读取未完成；请检查数据目录权限后重启。")

    def closeEvent(self, event) -> None:  # noqa: N802
        """Closing hides the control centre; the tray and stop hotkey remain available."""
        if self.exiting:
            event.accept()
        else:
            if not self._close_notice_sent and not (self.latest and self.latest.get("settings", {}).get("close_notice_seen")):
                self._close_notice_sent = True
                self.hide_notice.emit("控制中心已隐藏，桌宠继续运行。麦克风状态："+self._voice_status+"。可从托盘重新打开；关闭窗口不会关闭已开启的监听。")
                self.controller.submit("settings_patch", {"close_notice_seen": True})
            self.hide()
            event.ignore()
