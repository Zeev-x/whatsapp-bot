import os
import unittest
from unittest.mock import Mock, patch

import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QProcess
from PySide6.QtWidgets import QApplication

from config import AI_CONFIG
from ui.window import ReyetteWindow


class OllamaStartupTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def create_window(self, models=None):
        response = Mock()
        response.json.return_value = {"models": models or []}
        with (
            patch("ui.window.requests.get", return_value=response),
            patch.object(ReyetteWindow, "start_whatsapp_bot") as start_bot,
            patch.object(
                ReyetteWindow, "start_ollama_installer"
            ) as start_installer,
        ):
            window = ReyetteWindow()
        self.addCleanup(window.close)
        return window, start_bot, start_installer

    def test_available_model_starts_whatsapp_without_installing(self):
        window, start_bot, start_installer = self.create_window(
            [{"name": AI_CONFIG["model"]}]
        )

        start_bot.assert_called_once_with()
        start_installer.assert_not_called()
        self.assertEqual(window.ollama_status.text(), "Ollama - Siap")

    def test_missing_model_starts_installer_without_whatsapp(self):
        window, start_bot, start_installer = self.create_window(
            [{"name": "another-model:latest"}]
        )

        start_bot.assert_not_called()
        start_installer.assert_called_once()
        self.assertIn(AI_CONFIG["model"], start_installer.call_args.args[0])
        self.assertEqual(
            window.ollama_status.text(),
            "Ollama - Model belum ada",
        )

    def test_offline_server_starts_installer(self):
        with (
            patch(
                "ui.window.requests.get",
                side_effect=requests.ConnectionError("offline"),
            ),
            patch.object(ReyetteWindow, "start_whatsapp_bot") as start_bot,
            patch.object(
                ReyetteWindow, "start_ollama_installer"
            ) as start_installer,
        ):
            window = ReyetteWindow()
        self.addCleanup(window.close)

        start_bot.assert_not_called()
        start_installer.assert_called_once()
        self.assertEqual(
            window.ollama_status.text(),
            "Ollama - Tidak tersedia",
        )

    def test_installer_failure_is_reported(self):
        window, _, _ = self.create_window([{"name": AI_CONFIG["model"]}])
        window.install_output = ["model download failed"]
        window.setup_process = Mock()
        window.setup_process.readAllStandardOutput.return_value = QByteArray()
        window.setup_process.readAllStandardError.return_value = QByteArray()

        window.handle_install_finished(1, QProcess.CrashExit)

        self.assertEqual(
            window.ollama_status.text(),
            "Ollama - Instalasi gagal",
        )
        self.assertIn("model download failed", window.qr_status.text())


if __name__ == "__main__":
    unittest.main()
