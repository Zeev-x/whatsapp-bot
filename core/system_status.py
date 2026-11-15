import csv
import io
import json
import logging
import re
import shutil
import subprocess
import time
from datetime import datetime

import psutil


logger = logging.getLogger(__name__)

_SYSTEM_STATUS_TERMS = re.compile(
    r"\b(?:sistem(?:nya)?|system(?:nya)?|komputer(?:nya)?|pc|cpu|gpu|"
    r"penyimpanan|storage|disk|drive\s*[cd])\b",
    re.IGNORECASE,
)
_STATUS_REQUEST_TERMS = re.compile(
    r"\b(?:status|suhu|temperatur|temperature|berapa|sisa|tersisa|"
    r"free|kapasitas|capacity)\b",
    re.IGNORECASE,
)
_LIBRE_HARDWARE_MONITOR_COMMAND = """
$sensors = foreach ($namespace in @(
  'root/LibreHardwareMonitor',
  'root/OpenHardwareMonitor'
)) {
  Get-CimInstance -Namespace $namespace -ClassName Sensor `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.SensorType -eq 'Temperature' } |
    Select-Object Name, Value
}
if ($sensors) { @($sensors) | ConvertTo-Json -Compress }
"""


def is_system_status_request(message):
    return bool(
        _SYSTEM_STATUS_TERMS.search(message)
        and _STATUS_REQUEST_TERMS.search(message)
    )


def _read_hardware_monitor_sensors():
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _LIBRE_HARDWARE_MONITOR_COMMAND,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.info("Hardware Monitor sensors unavailable: %s", error)
        return []

    if not result.stdout.strip():
        return []

    try:
        sensors = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        logger.warning("Could not parse Hardware Monitor sensors: %s", error)
        return []

    if isinstance(sensors, dict):
        return [sensors]
    if isinstance(sensors, list):
        return sensors
    logger.warning("Hardware Monitor returned an unexpected sensor format.")
    return []


def _read_nvidia_gpu_temperatures():
    if shutil.which("nvidia-smi") is None:
        return []

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.info("NVIDIA GPU temperature unavailable: %s", error)
        return []

    readings = []
    for row in csv.reader(io.StringIO(result.stdout)):
        if len(row) < 2:
            continue
        try:
            temperature = float(row[1].strip())
        except ValueError:
            logger.warning("Invalid NVIDIA GPU temperature value: %r", row[1])
            continue
        readings.append((row[0].strip(), temperature))
    return readings


def _format_temperature(value):
    return f"{value:.0f} °C"


def _cpu_temperature(sensors):
    candidates = []
    for sensor in sensors:
        name = str(sensor.get("Name", ""))
        if not re.search(
            r"CPU\s*(?:Package|Core|Die|CCD)|Tctl/Tdie",
            name,
            re.IGNORECASE,
        ):
            continue
        try:
            temperature = float(sensor["Value"])
        except (KeyError, TypeError, ValueError):
            continue
        candidates.append((name, temperature))

    if not candidates:
        return (
            "Tidak tersedia (sensor CPU tidak terdeteksi; "
            "jalankan LibreHardwareMonitor untuk membaca suhu CPU)"
        )

    candidates.sort(
        key=lambda item: (
            "package" not in item[0].lower(),
            item[0].lower(),
        )
    )
    name, temperature = candidates[0]
    return f"{_format_temperature(temperature)} ({name})"


def _gpu_temperature(sensors):
    for sensor in sensors:
        name = str(sensor.get("Name", ""))
        if not re.search(r"\bGPU\b|Graphics", name, re.IGNORECASE):
            continue
        try:
            temperature = float(sensor["Value"])
        except (KeyError, TypeError, ValueError):
            continue
        return f"{_format_temperature(temperature)} ({name})"

    readings = _read_nvidia_gpu_temperatures()
    if readings:
        return "; ".join(
            f"{name}: {_format_temperature(temperature)}"
            for name, temperature in readings
        )
    return (
        "Tidak tersedia (sensor GPU tidak terdeteksi; "
        "GPU NVIDIA memerlukan driver NVIDIA)"
    )


def _drive_status(drive):
    try:
        usage = shutil.disk_usage(f"{drive}:\\")
    except OSError as error:
        logger.info("Drive %s status unavailable: %s", drive, error)
        return "Tidak tersedia (drive tidak ditemukan atau tidak dapat dibaca)"

    free_percent = usage.free / usage.total * 100 if usage.total else 0
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    return f"sisa {free_percent:.1f}% ({free_gb:.1f} GB / {total_gb:.1f} GB)"


def _resource_usage():
    try:
        memory = psutil.virtual_memory()
        memory_status = (
            f"{memory.percent:.1f}% digunakan "
            f"({memory.used / (1024 ** 3):.1f} GB / "
            f"{memory.total / (1024 ** 3):.1f} GB)"
        )
    except (OSError, psutil.Error) as error:
        logger.warning("Could not read memory usage: %s", error)
        memory_status = "Tidak tersedia"

    try:
        disk_before = psutil.disk_io_counters()
        start = time.monotonic()
        cpu_percent = psutil.cpu_percent(interval=1)
        elapsed = time.monotonic() - start
        disk_after = psutil.disk_io_counters()
        cpu_status = f"{cpu_percent:.1f}% digunakan"

        if disk_before is None or disk_after is None or elapsed <= 0:
            disk_status = "Tidak tersedia"
        else:
            read_rate = max(
                0,
                disk_after.read_bytes - disk_before.read_bytes
            ) / elapsed
            write_rate = max(
                0,
                disk_after.write_bytes - disk_before.write_bytes
            ) / elapsed
            disk_status = (
                f"Baca {read_rate / (1024 ** 2):.2f} MB/s, "
                f"tulis {write_rate / (1024 ** 2):.2f} MB/s"
            )
    except (OSError, psutil.Error) as error:
        logger.warning("Could not read CPU or disk activity: %s", error)
        cpu_status = "Tidak tersedia"
        disk_status = "Tidak tersedia"

    return cpu_status, memory_status, disk_status


def get_system_status():
    sensors = _read_hardware_monitor_sensors()
    cpu_usage, memory_usage, disk_activity = _resource_usage()
    timestamp = datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S")
    return "\n".join(
        (
            f"Status komputer saat ini ({timestamp}):",
            f"- CPU: {_cpu_temperature(sensors)}",
            f"- Penggunaan CPU: {cpu_usage}",
            f"- GPU: {_gpu_temperature(sensors)}",
            f"- RAM: {memory_usage}",
            f"- Aktivitas disk: {disk_activity}",
            f"- Penyimpanan C: {_drive_status('C')}",
            f"- Penyimpanan D: {_drive_status('D')}",
        )
    )
