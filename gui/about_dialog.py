"""About Dialog for VFX Review Player matching Nuke / VFX studio aesthetics."""

import os
import sys
from PyQt6 import QtWidgets, QtGui, QtCore


class AboutDialog(QtWidgets.QDialog):
    """Modal About dialog designed with dark studio aesthetics."""

    def __init__(self, parent=None, version: str = "1.1.3"):
        super().__init__(parent)
        self.setWindowTitle("About VFX Review Player")
        self.setFixedSize(450, 580)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)

        # Base paths
        if getattr(sys, 'frozen', False):
            app_root = os.path.dirname(sys.executable)
        else:
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Read version file if available
        version_file = os.path.join(app_root, "VERSION")
        if os.path.exists(version_file):
            try:
                with open(version_file, "r", encoding="utf-8") as f:
                    ver_str = f.read().strip()
                    if ver_str:
                        version = ver_str
            except Exception:
                pass

        # Set Window Icon
        icon_path = os.path.join(app_root, "logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
        elif os.path.exists(os.path.join(app_root, "logo.ico")):
            self.setWindowIcon(QtGui.QIcon(os.path.join(app_root, "logo.ico")))

        # Overall Dialog Styling
        self.setStyleSheet("""
            QDialog {
                background-color: #141416;
                color: #e5e5ea;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "SF Pro Text", sans-serif;
            }
            QLabel {
                color: #e5e5ea;
            }
            QPushButton {
                background-color: #222226;
                color: #f0f0f3;
                border: 1px solid #36363a;
                border-radius: 6px;
                padding: 7px 18px;
                font-size: 12px;
                font-weight: 600;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #2c2c32;
                border-color: #0a84ff;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0a84ff;
                border-color: #0a84ff;
                color: #ffffff;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(12)

        # 1. Logo Display Container
        logo_container = QtWidgets.QFrame()
        logo_container.setFixedHeight(145)
        logo_container.setStyleSheet("""
            QFrame {
                background-color: #101012;
                border: 1px solid #222226;
                border-radius: 10px;
            }
        """)
        logo_layout = QtWidgets.QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        logo_label = QtWidgets.QLabel()
        logo_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            pixmap = QtGui.QPixmap(icon_path)
            scaled = pixmap.scaled(
                130, 130,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(scaled)
        else:
            logo_label.setText("VFX PLAYER")
            logo_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #0a84ff;")

        logo_layout.addWidget(logo_label)
        layout.addWidget(logo_container)

        # 2. Application Title
        title_label = QtWidgets.QLabel("VFX Review Player")
        title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: 800; color: #ffffff; letter-spacing: 0.5px; margin-top: 4px;")
        layout.addWidget(title_label)

        # 3. Version Subtitle (Amber accent)
        version_label = QtWidgets.QLabel(f"Version v{version}")
        version_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #ff9f0a; margin-bottom: 2px;")
        layout.addWidget(version_label)

        # 4. Subtle Divider
        divider = QtWidgets.QFrame()
        divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        divider.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        divider.setStyleSheet("background-color: #26262a; max-height: 1px; margin: 4px 0px;")
        layout.addWidget(divider)

        # 5. Product Description
        desc_label = QtWidgets.QLabel(
            "VFX Review Player is a powerful, production-grade visual effects review and playback platform "
            "designed for VFX professionals. It seamlessly bridges high-dynamic-range sequence inspection, "
            "OpenColorIO/ACES color management, real-time comparison, and studio review workflows."
        )
        desc_label.setWordWrap(True)
        desc_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: #9c9ca4; font-size: 11.5px; line-height: 1.4; padding: 0 4px;")
        layout.addWidget(desc_label)

        # 6. Developer Credit Box
        credit_card = QtWidgets.QFrame()
        credit_card.setStyleSheet("""
            QFrame {
                background-color: #1a1a1e;
                border: 1px solid #28282d;
                border-radius: 8px;
            }
        """)
        credit_layout = QtWidgets.QVBoxLayout(credit_card)
        credit_layout.setContentsMargins(16, 12, 16, 12)
        credit_layout.setSpacing(4)
        credit_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        dev_label = QtWidgets.QLabel(
            "<span style='color: #8e8e93; font-weight: 600;'>Developed By:</span> "
            "<span style='color: #ffffff; font-weight: 700;'>Azhaguraj Pandian</span>"
        )
        dev_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        dev_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        dev_label.setStyleSheet("font-size: 12px;")
        credit_layout.addWidget(dev_label)

        gh_label = QtWidgets.QLabel(
            "<span style='color: #8e8e93; font-weight: 600;'>GitHub:</span> "
            "<a href='https://github.com/azhagurajpandians' style='color: #0a84ff; text-decoration: none; font-weight: 600;'>"
            "@azhagurajpandians</a>"
        )
        gh_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        gh_label.setOpenExternalLinks(True)
        gh_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        gh_label.setStyleSheet("font-size: 12px;")
        credit_layout.addWidget(gh_label)

        layout.addWidget(credit_card)

        layout.addSpacing(6)

        # 7. Button Row
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(14)
        btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.btn_github = QtWidgets.QPushButton("Visit GitHub")
        self.btn_github.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_github.clicked.connect(self._open_github)
        btn_layout.addWidget(self.btn_github)

        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _open_github(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/azhagurajpandians/vfx-player"))
