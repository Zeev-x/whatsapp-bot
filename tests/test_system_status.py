import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.system_status import (
    _cpu_temperature,
    _drive_status,
    _gpu_temperature,
    _resource_usage,
    get_system_status,
    is_system_status_request,
)


class SystemStatusTests(unittest.TestCase):

    def test_detects_system_status_questions(self):
        self.assertTrue(is_system_status_request("Berapa suhu CPU komputer?"))
        self.assertTrue(is_system_status_request("Systemnya berapa suhu CPU?"))
        self.assertTrue(is_system_status_request("Cek sisa penyimpanan di drive D"))
        self.assertFalse(is_system_status_request("Apa itu sistem operasi?"))

    def test_uses_cpu_package_sensor(self):
        sensors = [
            {"Name": "CPU Core #1", "Value": 42.0},
            {"Name": "CPU Package", "Value": 48.5},
        ]
        self.assertEqual(
            _cpu_temperature(sensors),
            "48 °C (CPU Package)",
        )

    def test_reports_unavailable_cpu_sensor_explicitly(self):
        self.assertIn("Tidak tersedia", _cpu_temperature([]))

    @patch("core.system_status._read_nvidia_gpu_temperatures")
    def test_uses_nvidia_temperature_if_hardware_monitor_is_unavailable(
        self,
        read_nvidia_temperatures,
    ):
        read_nvidia_temperatures.return_value = [
            ("NVIDIA Test GPU", 43.0)
        ]
        self.assertEqual(
            _gpu_temperature([]),
            "NVIDIA Test GPU: 43 °C",
        )

    @patch("core.system_status.shutil.disk_usage")
    def test_reports_remaining_drive_capacity(self, disk_usage):
        disk_usage.return_value = SimpleNamespace(
            total=1024 ** 3,
            used=3 * 1024 ** 3 // 4,
            free=1024 ** 3 // 4,
        )
        self.assertEqual(
            _drive_status("C"),
            "sisa 25.0% (0.2 GB / 1.0 GB)",
        )
        disk_usage.assert_called_once_with("C:\\")

    @patch("core.system_status.time.monotonic", side_effect=[10.0, 12.0])
    @patch("core.system_status.psutil.disk_io_counters")
    @patch("core.system_status.psutil.cpu_percent", return_value=37.5)
    @patch("core.system_status.psutil.virtual_memory")
    def test_reads_cpu_ram_and_disk_activity(
        self,
        virtual_memory,
        cpu_percent,
        disk_io_counters,
        monotonic,
    ):
        virtual_memory.return_value = SimpleNamespace(
            percent=62.0,
            used=8 * 1024 ** 3,
            total=16 * 1024 ** 3,
        )
        disk_io_counters.side_effect = [
            SimpleNamespace(read_bytes=1024 ** 2, write_bytes=2 * 1024 ** 2),
            SimpleNamespace(read_bytes=5 * 1024 ** 2, write_bytes=6 * 1024 ** 2),
        ]

        usage = _resource_usage()

        self.assertEqual(usage[0], "37.5% digunakan")
        self.assertEqual(usage[1], "62.0% digunakan (8.0 GB / 16.0 GB)")
        self.assertEqual(usage[2], "Baca 2.00 MB/s, tulis 2.00 MB/s")
        cpu_percent.assert_called_once_with(interval=1)
        self.assertEqual(monotonic.call_count, 2)

    @patch("core.system_status._read_hardware_monitor_sensors")
    @patch("core.system_status._resource_usage")
    @patch("core.system_status._drive_status")
    def test_builds_current_status_report(
        self,
        drive_status,
        resource_usage,
        read_sensors,
    ):
        read_sensors.return_value = [
            {"Name": "CPU Package", "Value": 50},
            {"Name": "GPU Core", "Value": 45},
        ]
        resource_usage.return_value = (
            "25.0% digunakan",
            "50.0% digunakan (8.0 GB / 16.0 GB)",
            "Baca 1.00 MB/s, tulis 2.00 MB/s",
        )
        drive_status.side_effect = ["sisa 50.0%", "sisa 25.0%"]

        report = get_system_status()

        self.assertIn("- CPU: 50 °C (CPU Package)", report)
        self.assertIn("- Penggunaan CPU: 25.0% digunakan", report)
        self.assertIn("- GPU: 45 °C (GPU Core)", report)
        self.assertIn("- RAM: 50.0% digunakan (8.0 GB / 16.0 GB)", report)
        self.assertIn(
            "- Aktivitas disk: Baca 1.00 MB/s, tulis 2.00 MB/s",
            report,
        )
        self.assertIn("- Penyimpanan C: sisa 50.0%", report)
        self.assertIn("- Penyimpanan D: sisa 25.0%", report)
        self.assertEqual(drive_status.call_args_list[0].args, ("C",))
        self.assertEqual(drive_status.call_args_list[1].args, ("D",))

    @patch("core.ai_engine.get_system_status")
    @patch("core.ai_engine.requests.post")
    def test_system_question_returns_live_status_without_calling_ai(
        self,
        post,
        get_status,
    ):
        from core.ai_engine import AIEngine

        get_status.return_value = "Status komputer saat ini"
        engine = AIEngine()

        answer = engine.generate("chat", "Berapa suhu CPU komputer?")

        self.assertEqual(answer, "Status komputer saat ini")
        get_status.assert_called_once_with()
        post.assert_not_called()

    @patch("core.ai_engine.get_system_status")
    @patch("core.ai_engine.requests.post")
    def test_group_system_status_request_is_not_answered(
        self,
        post,
        get_status,
    ):
        from core.ai_engine import AIEngine

        engine = AIEngine()

        answer = engine.generate(
            "123456789-123456@g.us",
            "Berapa suhu CPU komputer?",
        )

        self.assertIsNone(answer)
        get_status.assert_not_called()
        post.assert_not_called()

    @patch("core.ai_engine.requests.post")
    def test_ai_receives_sender_name_as_context(self, post):
        from core.ai_engine import AIEngine

        response = post.return_value
        response.json.return_value = {
            "message": {"content": "Halo, Rani!"}
        }
        engine = AIEngine()

        answer = engine.generate(
            "12345@g.us",
            "Bisa bantu?",
            sender_name="  Rani  ",
            memory_chat_id="12345@g.us|628123456789",
        )

        self.assertEqual(answer, "Halo, Rani!")
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(
            messages[-1]["content"],
            "Nama WhatsApp pengirim: Rani\nPesan: Bisa bantu?",
        )
        self.assertIn("12345@g.us|628123456789", engine.memory.get_contacts())


if __name__ == "__main__":
    unittest.main()
