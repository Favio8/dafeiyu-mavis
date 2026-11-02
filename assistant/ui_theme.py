"""Mavis control center tokens: white, neutral gray, Klein blue and hairlines."""


def stylesheet(dark: bool = False) -> str:
    """Native system typography, with Chinese fallback supplied by Qt."""
    page, side, text, muted, line, hover, selected = (
        ("#202024", "#26262B", "#F0F0F5", "#ADB3C2", "#41414B", "#303039", "#243B70") if dark else
        ("#FFFFFF", "#F7F7F8", "#192130", "#657084", "#E2E4EA", "#F0F2F6", "#E9EEFB")
    )
    return f"""
QWidget#mavis {{ background:{page}; color:{text}; font-family:'Segoe UI','Microsoft YaHei UI'; font-size:13px; }}
QWidget#sidebar {{ background:{side}; border-right:1px solid {line}; }}
QWidget#pageContent, QWidget#pageWrap {{ background:{page}; }}
QWidget#toolbar {{ background:{page}; border-bottom:1px solid {line}; }}
QLabel {{ background:transparent; color:{text}; border:0; }}
QLabel[role='title'] {{ font-size:22px; font-weight:600; }}
QLabel[role='brand'] {{ font-size:19px; font-weight:600; }}
QLabel[role='muted'], QLabel#settingHint {{ color:{muted}; font-size:12px; }}
QLabel#settingLabel {{ font-weight:600; }}
QLabel[role='value'] {{ font-size:17px; font-weight:600; }}
QLabel[role='badge'] {{ background:{selected}; color:{text}; border-radius:5px; padding:5px 9px; }}
QListWidget#navigation {{ background:transparent; border:0; outline:0; padding:0; }}
QListWidget#navigation::item {{ padding:0 9px; margin:2px 0; border:1px solid transparent; border-radius:6px; color:{muted}; }}
QListWidget#navigation::item:selected {{ background:{selected}; color:{'#ADC4FF' if dark else '#002FA7'}; font-weight:600; }}
QListWidget#navigation::item:hover {{ background:{hover}; }}
QPushButton {{ background:{page}; color:{text}; border:1px solid {line}; border-radius:6px; padding:6px 10px; min-height:20px; }}
QPushButton:hover {{ background:{hover}; }}
QPushButton:pressed {{ background:{selected}; }}
QPushButton:disabled {{ background:{side}; color:{muted}; border-color:{line}; }}
QPushButton[role='primary'] {{ background:#002FA7; color:#FFFFFF; border-color:#002FA7; }}
QPushButton[role='primary']:hover {{ background:#1645BE; }}
QPushButton[role='primary']:disabled {{ background:{side}; color:{muted}; border-color:{line}; }}
QPushButton[role='stop'] {{ background:{page}; color:{'#FF9292' if dark else '#B42336'}; border-color:{'#85434B' if dark else '#E9B8C0'}; }}
QPushButton[role='stop']:hover {{ background:{'#542831' if dark else '#FFF1F3'}; }}
QLineEdit, QTextEdit, QTreeWidget {{ background:{page}; color:{text}; border:1px solid {line}; border-radius:7px; padding:7px; selection-background-color:#002FA7; selection-color:white; }}
QLineEdit {{ min-height:24px; }}
QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QTreeWidget:focus, QCheckBox:focus {{ border:1px solid #4D6BFE; }}
QListWidget#navigation::item:focus {{ border:1px solid #4D6BFE; }}
QTreeWidget::item {{ padding:8px 4px; border-bottom:1px solid {line}; }}
QTreeWidget::item:selected {{ background:{selected}; color:{text}; }}
QHeaderView::section {{ background:{side}; color:{muted}; border:0; border-bottom:1px solid {line}; padding:8px; text-align:left; }}
QScrollArea {{ border:0; background:{page}; }}
QFrame#settingsCard, QFrame#summaryCard {{ background:{page}; border:1px solid {line}; border-radius:10px; }}
QCheckBox {{ color:{text}; spacing:8px; padding:4px; }}
QCheckBox:disabled {{ color:{muted}; }}
QCheckBox::indicator:unchecked {{ width:16px; height:16px; background:{page}; border:1px solid {muted}; border-radius:4px; }}
QToolTip {{ background:{page}; color:{text}; border:1px solid {line}; padding:5px; }}
"""
