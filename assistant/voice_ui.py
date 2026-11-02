"""Voice settings and calibration through the host-owned session only."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QCheckBox, QPushButton,
    QComboBox, QLineEdit, QSpinBox, QProgressBar, QFileDialog, QTreeWidget, QTreeWidgetItem,
)

from pet.settings_widgets import SettingRow, SettingsCard
from .ui import label

STATES = {"OFF": "麦克风关闭", "ARMED": "等待唤醒", "CAPTURING": "正在听，请说出完整指令", "TRANSCRIBING": "正在本地识别", "PLAYBACK_GUARD": "正在播报 · 唤醒已暂停", "LOADING": "正在加载本地模型", "ERROR": "语音暂不可用"}
ERRORS = {"MICROPHONE_UNAVAILABLE": "没有可用麦克风，请接入设备后刷新。", "MICROPHONE_OPEN_FAILED_CHECK_WINDOWS_PRIVACY": "麦克风无法打开，请检查 Windows 麦克风权限。", "MICROPHONE_DEVICE_ERROR": "麦克风设备错误，已停止采集。", "INPUT_DEVICE_CHANGED_RESELECT_AND_ENABLE": "输入设备已变化，请重新选择并开启监听。", "VOICE_MODELS_MISSING_OR_INVALID": "模型缺失或校验失败，请下载或重新导入。"}


class VoicePanel(QWidget):
    def __init__(self, host, controller):
        super().__init__()
        self.host = host
        self.setObjectName("pageWrap")
        outer = QVBoxLayout(self)
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
        self.status = label("麦克风关闭", "brand")
        self.error = label("", "muted")
        layout.addWidget(self.status)
        layout.addWidget(self.error)
        self.listen = QCheckBox("开启本地唤醒监听（本次运行）")
        self.listen.toggled.connect(host.listen)
        self.calibrate = QCheckBox("校准模式：只识别，不执行任务")
        self.calibrate.setChecked(True)
        self.calibrate.toggled.connect(self._calibrate)
        layout.addWidget(SettingsCard([
            SettingRow("voice_listen", "语音主入口", "监听仅在本地进行，关闭后释放麦克风及未提交音频。", self.listen, stacked=True),
            SettingRow("voice_test", "先核对识别文字", "关闭校准模式后，语音走现有任务、权限与结果验证；不能通过语音批准动作。", self.calibrate, stacked=True),
        ]))
        self.devices = QComboBox()
        self.devices.addItem("系统默认麦克风", "")
        self.devices.setAccessibleName("选择麦克风")
        refresh = QPushButton("刷新设备与声音")
        refresh.clicked.connect(host.refresh)
        self.word = QLineEdit(host.config["word"])
        self.word.setMaxLength(8)
        self.word.setAccessibleName("中文唤醒词")
        self.sensitivity = QComboBox()
        self.sensitivity.addItems(["严格", "标准", "灵敏"])
        self.sensitivity.setCurrentText(host.config["sensitivity"])
        self.voices = QComboBox()
        self.voices.addItem("默认本地中文声音", "")
        self.volume = QSpinBox()
        self.volume.setRange(0, 100)
        self.volume.setValue(host.config["volume"])
        self.volume.setSuffix(" %")
        layout.addWidget(SettingsCard([
            SettingRow("voice_device", "输入设备", "设备变化后会停止采集；可重新选择并开启。", self.devices, stacked=True),
            SettingRow("voice_word", "唤醒词", "2–8 个汉字，同时只启用一个词。更改后先在校准模式试说。", self.word, stacked=True),
            SettingRow("voice_sensitivity", "检测灵敏度", "绑定当前 KWS 模型：严格 0.45 / 标准 0.25 / 灵敏 0.15；灵敏档更易误触发。", self.sensitivity, stacked=True),
            SettingRow("voice_tts_voice", "本地播报声音", "播报期间进入半双工保护，结束后恢复原监听状态。", self.voices, stacked=True),
            SettingRow("voice_volume", "播报音量", "只调整助手的本地语音音量。", self.volume),
        ]))
        row = QHBoxLayout()
        row.addWidget(refresh)
        apply = QPushButton("应用语音配置")
        apply.clicked.connect(lambda: host.configure(word=self.word.text(), sensitivity=self.sensitivity.currentText(), device=self.devices.currentData(), voice=self.voices.currentData(), volume=self.volume.value()))
        row.addWidget(apply)
        layout.addLayout(row)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        self.level.setFormat("输入音量 %p%")
        self.level.setAccessibleName("真实麦克风输入音量")
        layout.addWidget(self.level)
        actions = QHBoxLayout()
        for caption, callback in [("手动录音", lambda: host.record()), ("结束录音", host.end), ("取消录音", host.cancel)]:
            button = QPushButton(caption)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.shortcut = label("Ctrl+Alt+Space 手动录音：" + ("已注册" if host.hotkey.registered else "不可用，请使用按钮"), "muted")
        layout.addWidget(self.shortcut)
        tts = QHBoxLayout()
        self.tts_enabled = QCheckBox("播报简短任务结果")
        self.tts_enabled.setChecked(host.tts_enabled)
        self.tts_enabled.toggled.connect(host.set_tts_enabled)
        tts.addWidget(self.tts_enabled)
        preview = QPushButton("试听")
        preview.clicked.connect(lambda: host.speak(host.config["word"] + "在这里。语音播报测试。"))
        mute = QPushButton("停止播报")
        mute.clicked.connect(lambda: host._send("voice_mute"))
        tts.addWidget(preview)
        tts.addWidget(mute)
        layout.addLayout(tts)
        self.text = QLineEdit()
        self.text.setAccessibleName("识别结果与修正指令")
        self.text.setPlaceholderText("最终识别文字将在这里显示")
        layout.addWidget(self.text)
        correction = QPushButton("提交修正指令")
        correction.clicked.connect(lambda: host.correct(self.text.text()))
        layout.addWidget(correction, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(label("修正后提交会建立新任务，已产生的影响保留在记录中。ASR 置信度：模型未提供。", "muted"))
        self.model_status = label("", "muted")
        layout.addWidget(self.model_status)
        model_actions = QHBoxLayout()
        self.model_buttons = []
        for caption, callback in [("下载模型", lambda: host.prepare()), ("导入模型目录", self._import), ("移除模型缓存", lambda: host.prepare(delete=True))]:
            button = QPushButton(caption)
            button.clicked.connect(callback)
            self.model_buttons.append(button)
            model_actions.addWidget(button)
        layout.addLayout(model_actions)
        layout.addWidget(label("模型使用固定版本与哈希校验。KWS：Apache-2.0；VAD：MIT；ASR 基础模型：Apache-2.0，ONNX 转换包许可尚待确认。", "muted"))
        self.attempts = QTreeWidget()
        self.attempts.setHeaderLabels(["语音尝试", "结果", "时长 ms"])
        self.attempts.setRootIsDecorated(False)
        self.attempts.setAccessibleName("最近语音尝试诊断")
        self.attempts.setMinimumHeight(130)
        layout.addWidget(self.attempts)
        layout.addStretch()
        self._last_text = ""
        host.changed.connect(self.update_state)
        controller.signals.snapshot.connect(self._attempts, Qt.ConnectionType.QueuedConnection)
        self.update_state(host.state)
        for button in self.findChildren(QPushButton):
            button.setAccessibleName(button.text())

    def _calibrate(self, enabled):
        self.host.test_mode = enabled
        self.host.epoch += 1
        self.host._send("voice_cancel")
        self.host.publish()

    def _import(self):
        path = QFileDialog.getExistingDirectory(self, "选择已解压的模型总目录")
        if path:
            self.host.prepare(path)

    def update_state(self, value):
        self.status.setText(STATES.get(value["state"], value["state"]))
        if value.get("busy") and value["state"] == "ARMED":
            self.status.setText("任务进行中 · 语音新指令不会排队")
        self.error.setText(ERRORS.get(value.get("error"), value.get("error", "")))
        self.listen.blockSignals(True)
        self.listen.setChecked(value.get("desired", False))
        self.listen.blockSignals(False)
        self.level.setValue(round(value.get("level", 0)*100))
        for combo, key, default in [(self.devices, "devices", "系统默认麦克风"), (self.voices, "voices", "默认本地中文声音")]:
            rows = value.get(key, [])
            ids = [combo.itemData(i) for i in range(1, combo.count())]
            if ids != [row["id"] for row in rows]:
                selected = combo.currentData() or self.host.config["device" if key == "devices" else "voice"]
                combo.clear()
                combo.addItem(default, "")
                for row in rows:
                    combo.addItem(row["name"], row["id"])
                combo.setCurrentIndex(max(0, combo.findData(selected)))
        if value.get("last_text") != self._last_text:
            self._last_text = value.get("last_text", "")
            self.text.setText(self._last_text)
        models = value.get("models", {})
        names = {"kws": "唤醒", "asr": "识别", "vad": "断句"}
        self.model_status.setText("　".join(names[k] + "：" + ("校验通过" if v == "ready" else "缺失或损坏") for k, v in models.items()) + "　" + value.get("models_progress", ""))
        for button in self.model_buttons:
            button.setEnabled(not value.get("models_progress") and value["state"] in {"OFF", "ERROR"})

    def _attempts(self, snapshot):
        self.attempts.clear()
        outcomes = {"command": "有效指令", "no_speech": "无有效语音", "empty": "空指令/已取消", "error": "错误", "busy_ignored": "忙碌未排队"}
        for attempt in snapshot.get("voice_attempts", []):
            self.attempts.addTopLevelItem(QTreeWidgetItem([attempt["wakeword"], outcomes[attempt["result"]], str(attempt["audio_duration_ms"])]))
