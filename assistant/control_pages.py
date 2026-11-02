"""Control-center forms backed by controller snapshots and local host commands."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QTextEdit, QFileDialog, QMessageBox,
)

from pet.settings_widgets import SettingsCard, SettingRow


def page():
    panel = QWidget()
    panel.setObjectName("pageWrap")
    root = QVBoxLayout(panel)
    root.setContentsMargins(0, 0, 0, 0)
    area = QScrollArea()
    area.setWidgetResizable(True)
    content = QWidget()
    content.setObjectName("pageContent")
    box = QVBoxLayout(content)
    box.setContentsMargins(24, 22, 24, 16)
    box.setSpacing(16)
    area.setWidget(content)
    root.addWidget(area)
    return panel, box


def action(caption, callback):
    button = QPushButton(caption)
    button.setAccessibleName(caption)
    button.clicked.connect(lambda checked=False: callback())
    return button


class ModelPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        from .ui import label
        self.controller, self.loaded = controller, False
        wrapper, layout = page()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(wrapper)
        layout.addWidget(label("DeepSeek · 配置与连接", "brand"))
        layout.addWidget(label("保存配置仅影响新任务。测试使用已保存配置，发送固定短文，可能产生 API 费用；不会操作电脑。", "muted"))
        self.endpoint = QLineEdit()
        self.model = QLineEdit()
        self.model.setMaxLength(120)
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 120)
        self.timeout.setSuffix(" 秒")
        self.retries = QSpinBox()
        self.retries.setRange(0, 2)
        layout.addWidget(SettingsCard([
            SettingRow("model_endpoint", "API 地址", "当前只支持官方 HTTPS 地址 api.deepseek.com。", self.endpoint, stacked=True),
            SettingRow("model_id", "模型 ID", "填写供应商实际支持的模型名称。", self.model, stacked=True),
            SettingRow("model_timeout", "请求超时", "10–120 秒；正在运行的任务保持原配置快照。", self.timeout),
            SettingRow("model_retries", "请求重试上限", "0–2 次；不会自动重放电脑操作。", self.retries),
        ]))
        layout.addWidget(action("保存模型配置", self._save))
        self.credential = label("正在检查本地凭据库……", "muted")
        layout.addWidget(self.credential)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setMaxLength(1024)
        self.key.setPlaceholderText("新 Key 只写入 Windows 凭据库")
        self.key.setAccessibleName("DeepSeek API Key，仅写入凭据库")
        layout.addWidget(self.key)
        keys = QHBoxLayout()
        keys.addWidget(action("保存凭据", self._save_key))
        keys.addWidget(action("删除凭据", self._delete_key))
        layout.addLayout(keys)
        self.result = label("正在读取能力状态……")
        layout.addWidget(self.result)
        tests = QHBoxLayout()
        tests.addWidget(action("测试连接", lambda: controller.submit("probe_connection")))
        tests.addWidget(action("测试工具调用", lambda: controller.submit("probe_tools")))
        layout.addLayout(tests)
        layout.addWidget(label("视觉能力以真实探针为准；当前没有接入视觉请求，状态为未验证。", "muted"))
        layout.addStretch()
        controller.signals.snapshot.connect(self.update_snapshot, Qt.ConnectionType.QueuedConnection)
        controller.signals.settings_saved.connect(self.apply_settings, Qt.ConnectionType.QueuedConnection)

    def apply_settings(self, settings):
        provider = settings["provider"]
        self.endpoint.setText(provider["base_url"])
        self.model.setText(provider["model"])
        self.timeout.setValue(provider["timeout_s"])
        self.retries.setValue(provider["retries"])
        self.loaded = True

    def update_snapshot(self, value):
        if not self.loaded and value.get("settings"):
            self.apply_settings(value["settings"])
        self.credential.setText("凭据："+value.get("credential_state", "未检查"))
        checks = value.get("provider_checks", {})
        self.result.setText("连接："+checks.get("connection", "待验证")+"　工具："+checks.get("tools", "待验证")+"　视觉："+checks.get("vision", "未验证"))

    def _save(self):
        self.controller.submit("settings_patch", {"provider": {"base_url": self.endpoint.text().strip(), "model": self.model.text().strip(), "timeout_s": self.timeout.value(), "retries": self.retries.value()}})

    def _save_key(self):
        if self.key.text().strip():
            self.controller.submit("save_key", self.key.text())
            self.key.clear()

    def _delete_key(self):
        if QMessageBox.question(self, "删除 API 凭据", "从 Windows 凭据库删除 Mavis 的 DeepSeek Key？正在运行的任务不会被重新配置。") == QMessageBox.StandardButton.Yes:
            self.controller.submit("delete_key")


class DataPage(QWidget):
    navigate = Signal(int)

    def __init__(self, controller):
        super().__init__()
        from .ui import label
        self.controller, self.loaded = controller, False
        wrapper, layout = page()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(wrapper)
        layout.addWidget(label("本机记录与隐私", "brand"))
        layout.addWidget(label("音频在本机内存中识别，默认不保存或上传原始音频；截图默认不保存。SQLite 记录未加密。API 请求按授权发送文本；诊断不自动上传。", "muted"))
        self.location = label("正在读取数据位置……", "muted")
        self.usage = label("正在读取记录统计……")
        layout.addWidget(self.location)
        layout.addWidget(self.usage)
        self.retention = QComboBox()
        for days in (7, 30, 90):
            self.retention.addItem(f"{days} 天", days)
        layout.addWidget(SettingsCard([SettingRow("record_retention", "记录保留期限", "按任务结束时间清理；活动任务保留。语音尝试按创建时间清理。下次本地定时清理生效。", self.retention, stacked=True)]))
        layout.addWidget(action("保存保留期限", lambda: controller.submit("settings_patch", {"retention_days": self.retention.currentData()})))
        layout.addWidget(action("筛选并导出任务记录", lambda: self.navigate.emit(1)))
        layout.addWidget(action("清空本地记录…", self._clear))
        layout.addWidget(label("清空会移除已结束任务、相关事件/审批/验证、语音尝试及本应用管理的诊断缓存和备份。活动任务保留；已导出的文件不删，已发送到云端的数据不会被撤回。", "muted"))
        layout.addWidget(action("生成脱敏诊断预览", lambda: controller.submit("diagnostic_preview")))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName("导出前的脱敏诊断预览")
        self.preview.setPlaceholderText("生成后可核对实际内容；默认不包含任务原文、音频、截图或 Key。")
        self.preview.setMinimumHeight(200)
        layout.addWidget(self.preview)
        self.export = action("导出预览中的诊断包", self._export)
        self.export.setEnabled(False)
        self.export.setToolTip("先生成并查看诊断预览")
        layout.addWidget(self.export)
        layout.addStretch()
        controller.signals.snapshot.connect(self.update_snapshot, Qt.ConnectionType.QueuedConnection)
        controller.signals.result.connect(self._result, Qt.ConnectionType.QueuedConnection)
        controller.signals.settings_saved.connect(lambda value: self.retention.setCurrentIndex(max(0, self.retention.findData(value["retention_days"]))), Qt.ConnectionType.QueuedConnection)

    def update_snapshot(self, value):
        if not self.loaded and value.get("settings"):
            self.retention.setCurrentIndex(max(0, self.retention.findData(value["settings"]["retention_days"])))
            self.loaded = True
        self.location.setText("数据目录："+value.get("data_dir", "读取中"))
        counts = value.get("counts", {})
        self.usage.setText(f"任务 {counts.get('tasks', 0)} 条 · 活动 {counts.get('active', 0)} 条 · 语音尝试 {counts.get('voice_attempts', 0)} 条\n记录数据库占用：{value.get('database_bytes', 0)/1024:.1f} KiB")

    def _clear(self):
        if QMessageBox.question(self, "清空本地记录", "清理已结束任务、语音尝试和应用管理的诊断/备份？活动任务和已导出文件保留，云端数据不会撤回。") == QMessageBox.StandardButton.Yes:
            self.controller.submit("clear_records")

    def _result(self, value):
        if value["kind"] == "diagnostic_preview":
            self.preview.setPlainText(json.dumps(value["data"], ensure_ascii=False, indent=2))
            self.export.setEnabled(True)
            self.export.setToolTip("导出当前已展示的内容，不添加隐藏附件")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出脱敏诊断包", "mavis-diagnostics.zip", "ZIP (*.zip)")
        if path:
            self.controller.submit("diagnostic_export", path)


class AboutPage(QWidget):
    reopen_guide = Signal()

    def __init__(self, controller):
        super().__init__()
        from .ui import label
        from . import __version__
        wrapper, layout = page()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(wrapper)
        layout.addWidget(label("DaFeiYu Mavis · "+__version__, "brand"))
        layout.addWidget(label("基于 MerZlin/dsh-pet-indesktop 增量开发\n固定上游：34d810b1eadd98d00e7cb9b3b51428a45b5bf03e", "muted"))
        self.error = label("最近错误：尚未读取")
        layout.addWidget(self.error)
        layout.addWidget(action("重新打开首次引导", self.reopen_guide.emit))
        layout.addWidget(action("检查已安装组件", lambda: controller.submit("diagnostic_preview")))
        self.components = QTextEdit()
        self.components.setReadOnly(True)
        self.components.setAccessibleName("真实组件版本和本地诊断")
        self.components.setPlaceholderText("检查后展示实际环境和依赖版本。")
        layout.addWidget(self.components)
        self.licenses = QTextEdit()
        self.licenses.setReadOnly(True)
        self.licenses.setAccessibleName("上游和第三方许可说明")
        self.licenses.setPlaceholderText("点击下面按钮读取随源码提供的许可说明。")
        layout.addWidget(action("查看随包许可说明", self._licenses))
        layout.addWidget(self.licenses)
        controller.signals.snapshot.connect(lambda value: self.error.setText("最近错误："+(value.get("last_error") or "本次运行尚无错误")), Qt.ConnectionType.QueuedConnection)
        controller.signals.result.connect(self._result, Qt.ConnectionType.QueuedConnection)

    def _licenses(self):
        root = Path(__file__).resolve().parents[1]
        parts = []
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            path = root / name
            if path.is_file():
                parts.append(name+"\n\n"+path.read_text(encoding="utf-8"))
        self.licenses.setPlainText("\n\n".join(parts) or "当前源码目录未找到许可文件，请检查安装资源。")

    def _result(self, value):
        if value["kind"] == "diagnostic_preview":
            self.components.setPlainText(json.dumps(value["data"], ensure_ascii=False, indent=2))
