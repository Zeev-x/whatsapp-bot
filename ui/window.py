
import base64
import binascii
import json
import shutil
from collections import deque
from pathlib import Path

import requests

from PySide6.QtCore import Qt, QProcess, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QFrame, QMessageBox
)
from PySide6.QtGui import QPixmap

from config import AI_CONFIG
from core.message_processor import MessageProcessor

PROCESSING_FAILURE_REPLY = "Maaf saya tidak bisa memprosesnya."


class AIWorker(QThread):

    finished_response = Signal(str, str)
    failed = Signal(str, str)

    def __init__(
        self,
        processor,
        chat_id,
        message,
        sender_name=None,
        memory_chat_id=None,
    ):
        super().__init__()

        self.processor = processor
        self.chat_id = chat_id
        self.message = message
        self.sender_name = sender_name
        self.memory_chat_id = memory_chat_id

    def run(self):

        try:
            result = self.processor.process(
                self.chat_id,
                self.message,
                sender_name=self.sender_name,
                memory_chat_id=self.memory_chat_id,
            )

            if result:
                self.finished_response.emit(
                    self.chat_id,
                    result["response"]
                )
            else:
                self.failed.emit(
                    self.chat_id,
                    "AI tidak menghasilkan balasan."
                )

        except Exception as error:
            self.failed.emit(self.chat_id, str(error))


class ReyetteWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("Reyette WhatsApp")
        self.resize(1280, 800)
        self.setMinimumSize(980, 680)

        self.processor = MessageProcessor()
        self.pending_messages = deque()
        self.active_worker = None
        self.project_root = Path(__file__).resolve().parents[1]
        self._stdout_buffer = bytearray()

        self.init_ui()
        self.check_ollama()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget {
                color: #17231d;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QMainWindow, QWidget#appRoot {
                background: #f3f6f4;
            }
            QFrame#sessionPanel, QFrame#responseCard, QFrame#composerCard {
                background: #ffffff;
                border: 1px solid #e3eae5;
                border-radius: 16px;
            }
            QLabel#brandMark {
                color: #ffffff;
                background: #1fae69;
                border-radius: 16px;
                font-size: 22pt;
                font-weight: 700;
            }
            QLabel#pageTitle {
                font-size: 22pt;
                font-weight: 700;
                color: #17231d;
            }
            QLabel#sectionTitle {
                font-size: 12pt;
                font-weight: 650;
                color: #17231d;
            }
            QLabel#mutedText {
                color: #738078;
            }
            QLabel#qrCanvas {
                background: #f6f9f7;
                border: 1px dashed #cbd9d0;
                border-radius: 14px;
                color: #718078;
            }
            QLabel#statusBadge {
                background: #edf2ef;
                color: #526158;
                border-radius: 9px;
                padding: 7px 10px;
                font-size: 9pt;
                font-weight: 600;
            }
            QLabel#aiStatus[enabled="true"] {
                background: #e7f7ee;
                color: #13834b;
            }
            QLabel#aiStatus[enabled="false"] {
                background: #f0f1f0;
                color: #68736c;
            }
            QLabel#ollamaStatus[connected="true"],
            QLabel#whatsappStatus[connected="true"] {
                background: #e7f7ee;
                color: #13834b;
            }
            QLabel#ollamaStatus[connected="false"],
            QLabel#whatsappStatus[connected="false"] {
                background: #fff1e9;
                color: #b15a2a;
            }
            QTextEdit {
                background: #fbfcfb;
                border: 1px solid #e3eae5;
                border-radius: 10px;
                padding: 10px;
                selection-background-color: #b8edcf;
            }
            QTextEdit:focus {
                border: 1px solid #28b873;
            }
            QPushButton {
                background: #eef3f0;
                color: #26352c;
                border: 1px solid #e0e8e3;
                border-radius: 9px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #e4eee8;
            }
            QPushButton:pressed {
                background: #d7e8dd;
            }
            QPushButton#primaryButton {
                background: #1fae69;
                color: #ffffff;
                border: none;
                padding: 11px 16px;
            }
            QPushButton#primaryButton:hover {
                background: #168d53;
            }
            QPushButton#primaryButton:disabled {
                background: #a9d8bd;
                color: #f6fff9;
            }
            QPushButton#aiToggle[enabled="false"] {
                background: #1fae69;
                color: #ffffff;
                border: none;
            }
            QPushButton#dangerButton {
                background: #fff0ed;
                color: #a63e30;
                border: 1px solid #f3d4ce;
            }
            QPushButton#dangerButton:hover {
                background: #ffe4df;
            }
        """)

        self.qr_label = QLabel("Menunggu QR")
        self.qr_label.setObjectName("qrCanvas")
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(280, 280)
        self.qr_label.setMaximumSize(320, 320)

        self.qr_status = QLabel(
            "Hubungkan akun WhatsApp dengan memindai QR dari ponsel."
        )
        self.qr_status.setObjectName("mutedText")
        self.qr_status.setAlignment(Qt.AlignCenter)
        self.qr_status.setWordWrap(True)

        session_panel = QFrame()
        session_panel.setObjectName("sessionPanel")
        session_panel.setMinimumWidth(330)
        session_layout = QVBoxLayout(session_panel)
        session_layout.setContentsMargins(22, 22, 22, 22)
        session_layout.setSpacing(16)

        brand_row = QHBoxLayout()
        brand_mark = QLabel("R")
        brand_mark.setObjectName("brandMark")
        brand_mark.setFixedSize(48, 48)
        brand_mark.setAlignment(Qt.AlignCenter)

        brand_text = QVBoxLayout()
        brand_title = QLabel("Reyette")
        brand_title.setStyleSheet("font-size: 15pt; font-weight: 700;")
        brand_caption = QLabel("WhatsApp Assistant")
        brand_caption.setObjectName("mutedText")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_caption)
        brand_row.addWidget(brand_mark)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()

        session_title = QLabel("Sesi WhatsApp")
        session_title.setObjectName("sectionTitle")
        session_hint = QLabel("Pindai QR untuk menautkan akun Anda.")
        session_hint.setObjectName("mutedText")
        session_hint.setWordWrap(True)

        self.whatsapp_status = QLabel("WhatsApp - Menghubungkan")
        self.whatsapp_status.setObjectName("statusBadge")
        self.whatsapp_status.setProperty("connected", False)
        self.whatsapp_status.setAlignment(Qt.AlignCenter)

        session_layout.addLayout(brand_row)
        session_layout.addSpacing(10)
        session_layout.addWidget(session_title)
        session_layout.addWidget(session_hint)
        session_layout.addWidget(self.whatsapp_status, alignment=Qt.AlignLeft)
        session_layout.addStretch()
        session_layout.addWidget(self.qr_label, alignment=Qt.AlignHCenter)
        session_layout.addWidget(self.qr_status)
        session_layout.addStretch()

        self.ai_status = QLabel("AI - Aktif")
        self.ai_status.setObjectName("statusBadge")
        self.ai_status.setProperty("enabled", True)
        self.ai_status.setAlignment(Qt.AlignCenter)
        self.ollama_status = QLabel("Ollama - Memeriksa")
        self.ollama_status.setObjectName("statusBadge")
        self.ollama_status.setProperty("connected", False)
        self.ollama_status.setAlignment(Qt.AlignCenter)

        self.toggle_button = QPushButton("Matikan AI")
        self.toggle_button.setObjectName("aiToggle")
        self.toggle_button.setProperty("enabled", True)
        self.toggle_button.clicked.connect(
            self.toggle_ai
        )

        self.clear_button = QPushButton("Bersihkan memori")
        self.clear_button.clicked.connect(
            self.clear_memory
        )

        self.clear_session_button = QPushButton("Hapus sesi")
        self.clear_session_button.setObjectName("dangerButton")
        self.clear_session_button.clicked.connect(
            self.confirm_clear_whatsapp_session
        )

        top_bar = QHBoxLayout()
        title_block = QVBoxLayout()
        page_title = QLabel("Ruang kerja")
        page_title.setObjectName("pageTitle")
        page_subtitle = QLabel(
            "Pantau koneksi dan uji balasan asisten Anda."
        )
        page_subtitle.setObjectName("mutedText")
        title_block.addWidget(page_title)
        title_block.addWidget(page_subtitle)
        top_bar.addLayout(title_block)
        top_bar.addStretch()

        header_controls = QVBoxLayout()
        header_controls.setSpacing(10)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self.ai_status)
        status_row.addWidget(self.ollama_status)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.toggle_button)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.clear_session_button)
        header_controls.addLayout(status_row)
        header_controls.addLayout(button_row)
        top_bar.addLayout(header_controls)

        response_card = QFrame()
        response_card.setObjectName("responseCard")
        response_layout = QVBoxLayout(response_card)
        response_layout.setContentsMargins(18, 18, 18, 18)
        response_layout.setSpacing(12)
        response_heading = QHBoxLayout()
        response_title = QLabel("Aktivitas percakapan")
        response_title.setObjectName("sectionTitle")
        self.activity_hint = QLabel("Balasan AI dan pesan masuk akan muncul di sini.")
        self.activity_hint.setObjectName("mutedText")
        response_heading.addWidget(response_title)
        response_heading.addStretch()
        response_layout.addLayout(response_heading)
        response_layout.addWidget(self.activity_hint)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText(
            "Belum ada aktivitas. Pesan masuk dan balasan bot akan tampil di sini."
        )
        response_layout.addWidget(self.output)

        composer_card = QFrame()
        composer_card.setObjectName("composerCard")
        composer_layout = QVBoxLayout(composer_card)
        composer_layout.setContentsMargins(18, 16, 18, 16)
        composer_layout.setSpacing(10)
        composer_title = QLabel("Coba balasan AI")
        composer_title.setObjectName("sectionTitle")
        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText(
            "Tulis pesan untuk menguji AI secara manual..."
        )
        self.chat_input.setFixedHeight(82)

        self.send_button = QPushButton(
            "Buat balasan"
        )
        self.send_button.setObjectName("primaryButton")
        self.send_button.setMinimumWidth(150)

        self.send_button.clicked.connect(
            self.generate_reply
        )

        composer_actions = QHBoxLayout()
        composer_note = QLabel("Pesan ini hanya untuk menguji AI.")
        composer_note.setObjectName("mutedText")
        composer_actions.addWidget(composer_note)
        composer_actions.addStretch()
        composer_actions.addWidget(self.send_button)
        composer_layout.addWidget(composer_title)
        composer_layout.addWidget(self.chat_input)
        composer_layout.addLayout(composer_actions)

        work_panel = QWidget()
        work_layout = QVBoxLayout(work_panel)
        work_layout.setContentsMargins(0, 0, 0, 0)
        work_layout.setSpacing(18)
        work_layout.addLayout(top_bar)
        work_layout.addWidget(response_card, stretch=1)
        work_layout.addWidget(composer_card)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(22, 20, 22, 20)
        root_layout.setSpacing(18)
        root_layout.addWidget(session_panel)
        root_layout.addWidget(work_panel, stretch=1)

        self.setCentralWidget(root)

    @staticmethod
    def _refresh_style(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _set_connection_status(self, label, text, connected):
        label.setText(text)
        label.setProperty("connected", connected)
        self._refresh_style(label)

    def start_whatsapp_bot(self):
        script = self.project_root / "services" / "whatsapp.js"
        if not script.is_file():
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Service tidak ditemukan",
                False,
            )
            self.qr_status.setText(str(script))
            return

        self.bot_process = QProcess(self)
        self.bot_process.setWorkingDirectory(str(self.project_root))
        self.bot_process.readyReadStandardOutput.connect(
            self.handle_bot_output
        )
        self.bot_process.readyReadStandardError.connect(
            self.handle_bot_error_output
        )
        self.bot_process.errorOccurred.connect(
            self.handle_bot_process_error
        )
        self.bot_process.finished.connect(
            self.handle_bot_finished
        )

        auth_path = self.project_root / "data" / "whatsapp_auth"
        try:
            auth_path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Sesi gagal disiapkan",
                False,
            )
            self.qr_status.setText(
                f"Tidak dapat membuat folder autentikasi: {error}"
            )
            return

        self.bot_process.start(
            "node",
            [str(script), str(auth_path)]
        )

    def handle_bot_output(self):
        self._stdout_buffer.extend(
            bytes(self.bot_process.readAllStandardOutput())
        )

        while b"\n" in self._stdout_buffer:
            line, _, remaining = self._stdout_buffer.partition(b"\n")
            self._stdout_buffer = bytearray(remaining)
            if not line:
                continue
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                self.qr_status.setText(
                    f"Respons service WhatsApp tidak valid: {error}"
                )
                continue
            self.handle_bot_event(event)

    def handle_bot_event(self, event):
        event_type = event.get("type")

        if event_type == "qr":
            try:
                image_data = event["image"].split(",", 1)[1]
                image = QPixmap()
                if not image.loadFromData(base64.b64decode(image_data)):
                    raise ValueError("Gambar QR tidak dapat dibaca.")
            except (
                KeyError,
                IndexError,
                ValueError,
                binascii.Error
            ) as error:
                self.qr_status.setText(f"Gagal menampilkan QR: {error}")
                return

            self.qr_label.setPixmap(
                image.scaled(
                    320,
                    320,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )
            self.qr_status.setText(
                "WhatsApp > Perangkat tertaut > Tautkan perangkat, "
                "lalu pindai QR ini."
            )
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Menunggu scan",
                False,
            )
        elif event_type == "connected":
            self.qr_label.setPixmap(QPixmap())
            self.qr_label.setText("✓")
            self.qr_status.setText(
                "Akun berhasil ditautkan. Sesi tersimpan dengan aman di "
                "komputer ini."
            )
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Terhubung",
                True,
            )
        elif event_type == "disconnected":
            self.qr_label.setPixmap(QPixmap())
            self.qr_label.setText("Koneksi terputus")
            self.qr_status.setText(
                event.get("message", "Koneksi terputus; mencoba menyambung ulang.")
            )
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Menyambungkan ulang",
                False,
            )
        elif event_type == "message":
            self.handle_incoming_message(
                event.get("chat_id", ""),
                event.get("text", ""),
                event.get("sender_name", ""),
                event.get("sender_id", ""),
                event.get("is_group", False),
            )
        elif event_type == "deleted":
            self.qr_status.setText(
                f"Pesan bot berhasil dihapus dari {event.get('chat_id', 'chat')}."
            )
        elif event_type == "error":
            message = event.get("message", "Kesalahan service WhatsApp.")
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Perlu perhatian",
                False,
            )
            self.qr_status.setText(message)

    def handle_bot_error_output(self):
        error = bytes(self.bot_process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        ).strip()
        if error:
            self.qr_status.setText(f"WhatsApp service: {error[-1000:]}")

    def handle_bot_process_error(self, error):
        if error == QProcess.FailedToStart:
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Node.js tidak ditemukan",
                False,
            )
            self.qr_status.setText(
                "Pastikan Node.js tersedia dan jalankan `npm install`."
            )

    def handle_bot_finished(self, exit_code):
        if exit_code != 0:
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Service berhenti",
                False,
            )
            self.qr_status.setText(
                f"Service WhatsApp berhenti (kode {exit_code})."
            )

    def send_bot_command(self, command):
        if (
            not hasattr(self, "bot_process")
            or self.bot_process.state() != QProcess.Running
        ):
            self.qr_status.setText(
                "Service WhatsApp tidak berjalan; balasan tidak terkirim."
            )
            return False

        payload = json.dumps(command, ensure_ascii=False) + "\n"
        written = self.bot_process.write(payload.encode("utf-8"))
        if written < 0:
            self.qr_status.setText(
                "Gagal mengirim balasan ke service WhatsApp."
            )
            return False
        return True

    def handle_incoming_message(
        self,
        chat_id,
        message,
        sender_name="",
        sender_id="",
        is_group=False,
    ):
        if not chat_id or not message:
            return
        if not self.processor.enabled:
            return

        display_name = sender_name or sender_id or chat_id
        self.output.setPlainText(
            f"Pesan masuk dari {display_name}:\n"
            f"{message}\n\nMemproses balasan..."
        )
        self.activity_hint.setText(
            f"Sedang menyiapkan balasan untuk {display_name}."
        )
        memory_chat_id = (
            f"{chat_id}|{sender_id}"
            if is_group and sender_id
            else chat_id
        )
        self.start_ai_reply(
            chat_id,
            message,
            sender_name=sender_name,
            memory_chat_id=memory_chat_id,
        )

    def check_ollama(self):
        ollama_online = False
        model_installed = False
        error_message = ""
        try:
            response = requests.get(
                self._ollama_tags_url(),
                timeout=3
            )
            response.raise_for_status()
            ollama_online = True
            models = response.json().get("models", [])
            model_name = AI_CONFIG["model"]
            model_installed = any(
                isinstance(model, dict)
                and model.get("name") == model_name
                for model in models
            )
        except requests.RequestException as error:
            error_message = str(error)
        except (ValueError, TypeError, AttributeError) as error:
            error_message = f"Respons Ollama tidak valid: {error}"

        if ollama_online and model_installed:
            self._set_connection_status(
                self.ollama_status,
                "Ollama - Siap",
                True,
            )
            self.qr_status.setText(
                f"Ollama aktif dan model {AI_CONFIG['model']} tersedia."
            )
            self.start_whatsapp_bot()
            return

        if ollama_online:
            reason = f"Model {AI_CONFIG['model']} belum terpasang."
            self._set_connection_status(
                self.ollama_status,
                "Ollama - Model belum ada",
                False,
            )
        else:
            reason = "Ollama belum berjalan atau belum terpasang."
            if error_message:
                reason = f"{reason} {error_message}"
            self._set_connection_status(
                self.ollama_status,
                "Ollama - Tidak tersedia",
                False,
            )

        self.start_ollama_installer(reason)

    def _ollama_tags_url(self):
        endpoint = AI_CONFIG["endpoint"].rstrip("/")
        if endpoint.endswith("/api/chat"):
            return f"{endpoint[:-len('/chat')]}/tags"
        return "http://127.0.0.1:11434/api/tags"

    def start_ollama_installer(self, reason):
        installer = self.project_root / "install.ps1"
        if not installer.is_file():
            self.qr_status.setText(
                f"{reason} File install.ps1 tidak ditemukan."
            )
            return

        self.qr_status.setText(
            f"{reason} Menjalankan instalasi otomatis..."
        )
        self.install_output = []
        self.setup_verification_attempts = 0
        self.setup_process = QProcess(self)
        self.setup_process.setWorkingDirectory(str(self.project_root))
        self.setup_process.readyReadStandardOutput.connect(
            self.handle_install_output
        )
        self.setup_process.readyReadStandardError.connect(
            self.handle_install_error_output
        )
        self.setup_process.errorOccurred.connect(
            self.handle_install_process_error
        )
        self.setup_process.finished.connect(
            self.handle_install_finished
        )
        self.setup_process.start(
            "powershell.exe",
            [
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(installer),
                "-Model",
                AI_CONFIG["model"],
            ],
        )

    def handle_install_output(self):
        output = bytes(self.setup_process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        ).strip()
        if output:
            self.install_output.append(output)
            self.install_output = self.install_output[-20:]
            self.qr_status.setText(output[-500:])

    def handle_install_error_output(self):
        output = bytes(self.setup_process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        ).strip()
        if output:
            self.install_output.append(output)
            self.install_output = self.install_output[-20:]
            self.qr_status.setText(output[-500:])

    def handle_install_process_error(self, error):
        if error == QProcess.FailedToStart:
            self._set_connection_status(
                self.ollama_status,
                "Ollama - Instalasi gagal",
                False,
            )
            self.qr_status.setText(
                "Tidak dapat menjalankan PowerShell. Pastikan Windows "
                "PowerShell tersedia dan coba jalankan install.ps1 manual."
            )

    def handle_install_finished(self, exit_code, exit_status):
        self.handle_install_output()
        self.handle_install_error_output()
        if exit_code != 0 or exit_status != QProcess.NormalExit:
            self._set_connection_status(
                self.ollama_status,
                "Ollama - Instalasi gagal",
                False,
            )
            details = "\n".join(self.install_output[-5:])
            self.qr_status.setText(
                "Instalasi Ollama/model gagal. Periksa PowerShell:\n"
                f"{details[-1200:]}"
            )
            return

        self.setup_verification_attempts = 0
        self.qr_status.setText(
            "Instalasi selesai. Memverifikasi Ollama dan model..."
        )
        QTimer.singleShot(1000, self.verify_ollama_setup)

    def verify_ollama_setup(self):
        self.setup_verification_attempts += 1
        try:
            response = requests.get(self._ollama_tags_url(), timeout=3)
            response.raise_for_status()
            models = response.json().get("models", [])
            model_installed = any(
                isinstance(model, dict)
                and model.get("name") == AI_CONFIG["model"]
                for model in models
            )
        except (
            requests.RequestException,
            ValueError,
            TypeError,
            AttributeError,
        ) as error:
            model_installed = False
            verification_error = str(error)
        else:
            verification_error = ""

        if model_installed:
            self._set_connection_status(
                self.ollama_status,
                "Ollama - Siap",
                True,
            )
            self.qr_status.setText(
                f"Ollama aktif dan model {AI_CONFIG['model']} tersedia."
            )
            self.start_whatsapp_bot()
            return

        if self.setup_verification_attempts < 10:
            QTimer.singleShot(1500, self.verify_ollama_setup)
            return

        self._set_connection_status(
            self.ollama_status,
            "Ollama - Belum siap",
            False,
        )
        self.qr_status.setText(
            f"Instalasi selesai, tetapi Ollama/model {AI_CONFIG['model']} "
            "belum terdeteksi. Pastikan Ollama berjalan, lalu mulai ulang "
            f"aplikasi. {verification_error}"
        )

    def toggle_ai(self):

        enabled = not self.processor.enabled

        self.processor.set_enabled(enabled)

        self.ai_status.setText(
            "AI - Aktif" if enabled else "AI - Nonaktif"
        )
        self.ai_status.setProperty("enabled", enabled)
        self._refresh_style(self.ai_status)

        self.toggle_button.setText(
            "Matikan AI" if enabled else "Aktifkan AI"
        )
        self.toggle_button.setProperty("enabled", enabled)
        self._refresh_style(self.toggle_button)

    def clear_memory(self):

        self.processor.clear_memory()

        self.output.setPlainText(
            "Memori percakapan sementara sudah dibersihkan."
        )
        self.activity_hint.setText("Memori percakapan sudah dibersihkan.")

    def confirm_clear_whatsapp_session(self):
        answer = QMessageBox.warning(
            self,
            "Hapus sesi WhatsApp?",
            "Sesi tertaut akan dihapus dari komputer ini. "
            "Anda perlu memindai QR lagi untuk menghubungkan WhatsApp.\n\n"
            "Lanjutkan?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.clear_whatsapp_session()

    def clear_whatsapp_session(self):
        auth_path = self.project_root / "data" / "whatsapp_auth"
        expected_path = (
            self.project_root.resolve() / "data" / "whatsapp_auth"
        )

        if auth_path.resolve() != expected_path:
            self.qr_status.setText(
                "Lokasi sesi tidak sesuai; sesi tidak dihapus."
            )
            return

        if (
            hasattr(self, "bot_process")
            and self.bot_process.state() != QProcess.NotRunning
        ):
            self.send_bot_command({"type": "close"})
            if not self.bot_process.waitForFinished(4000):
                self.bot_process.terminate()
                if not self.bot_process.waitForFinished(2000):
                    self._set_connection_status(
                        self.whatsapp_status,
                        "WhatsApp - Service belum berhenti",
                        False,
                    )
                    self.qr_status.setText(
                        "Service WhatsApp masih berjalan. Sesi tidak dihapus; "
                        "tutup aplikasi lalu coba lagi."
                    )
                    return

        try:
            if auth_path.exists():
                shutil.rmtree(expected_path)
        except OSError as error:
            self._set_connection_status(
                self.whatsapp_status,
                "WhatsApp - Sesi gagal dihapus",
                False,
            )
            self.qr_status.setText(f"Tidak dapat menghapus sesi WhatsApp: {error}")
            return

        self.qr_label.setPixmap(QPixmap())
        self.qr_label.setText("Menunggu QR")
        self.qr_status.setText(
            "Sesi dihapus. Service sedang dimulai ulang untuk membuat QR baru."
        )
        self._set_connection_status(
            self.whatsapp_status,
            "WhatsApp - Memulai sesi baru",
            False,
        )
        self.start_whatsapp_bot()

    def generate_reply(self):

        message = self.chat_input.toPlainText().strip()

        if not message:
            return

        if not self.processor.enabled:
            self.output.setPlainText(
                "AI sedang dinonaktifkan."
            )
            return

        self.output.setPlainText("Reyette sedang berpikir...")
        self.activity_hint.setText("AI sedang menyusun balasan...")
        self.start_ai_reply("test_contact", message)

    def start_ai_reply(
        self,
        chat_id,
        message,
        sender_name=None,
        memory_chat_id=None,
    ):
        self.pending_messages.append(
            (chat_id, message, sender_name, memory_chat_id)
        )
        self.send_button.setEnabled(False)
        if self.active_worker is None:
            self.start_next_ai_reply()

    def start_next_ai_reply(self):
        chat_id, message, sender_name, memory_chat_id = (
            self.pending_messages.popleft()
        )
        worker = AIWorker(
            self.processor,
            chat_id,
            message,
            sender_name,
            memory_chat_id,
        )

        worker.finished_response.connect(
            self.show_response
        )

        worker.failed.connect(
            self.show_error
        )

        worker.finished.connect(
            lambda worker=worker: self.finish_worker(worker)
        )

        self.active_worker = worker
        worker.start()

    def finish_worker(self, worker):
        if self.active_worker is worker:
            self.active_worker = None
        worker.deleteLater()

        if self.pending_messages:
            self.start_next_ai_reply()
        else:
            self.send_button.setEnabled(True)

    def show_response(self, chat_id, response):
        if chat_id != "test_contact":
            self.send_bot_command({
                "type": "send",
                "chat_id": chat_id,
                "text": response
            })
            self.output.setPlainText(
                f"Balasan terkirim ke {chat_id}:\n{response}"
            )
            self.activity_hint.setText(
                f"Balasan berhasil dikirim ke {chat_id}."
            )
            return

        self.output.setPlainText(response)
        self.activity_hint.setText("Balasan uji berhasil dibuat.")

    def show_error(self, chat_id, error):
        if chat_id != "test_contact":
            self.qr_status.setText(
                f"Gagal memproses pesan dari {chat_id}: {error}"
            )
            if self.send_bot_command({
                "type": "send",
                "chat_id": chat_id,
                "text": PROCESSING_FAILURE_REPLY
            }):
                self.output.setPlainText(PROCESSING_FAILURE_REPLY)
                self.activity_hint.setText(
                    f"AI tidak dapat memproses pesan dari {chat_id}."
                )
            else:
                self.output.setPlainText(
                    "Pemrosesan gagal dan pesan maaf tidak dapat dikirim."
                )
                self.activity_hint.setText(
                    "Periksa koneksi WhatsApp untuk mengirim balasan."
                )
            return

        self.output.setPlainText(error)
        self.activity_hint.setText("AI tidak dapat memproses pesan uji.")

    def closeEvent(self, event):

        # Temporary memory dihapus saat aplikasi ditutup.
        self.processor.clear_memory()

        if hasattr(self, "bot_process") and (
            self.bot_process.state() != QProcess.NotRunning
        ):
            self.send_bot_command({"type": "close"})
            if not self.bot_process.waitForFinished(3000):
                self.bot_process.terminate()
                self.bot_process.waitForFinished(2000)

        super().closeEvent(event)
