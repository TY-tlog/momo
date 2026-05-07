"""Hardware sampler for the desktop pet.

Wraps psutil to provide periodic snapshots with delta-based I/O rates.
All sampling is local (OS syscalls); no network access.

Optional: spawns `macmon pipe` as a subprocess for Apple Silicon
temperature/power readings (no sudo required).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

import psutil


@dataclass
class HwSnapshot:
    cpu: float           # percent, 0..100
    memory: float        # percent, 0..100
    disk_read_mbps: float
    disk_write_mbps: float
    net_recv_mbps: float
    net_sent_mbps: float
    per_core: list[float]  # percent per logical core, 0..100
    timestamp: float


@dataclass
class CoreLayout:
    n_p: int           # performance cores (or all cores on non-Apple-Silicon)
    n_e: int           # efficiency cores (0 on non-Apple-Silicon)
    is_apple_silicon: bool

    def label(self, idx: int) -> str:
        if not self.is_apple_silicon:
            return f"C{idx}"
        if idx < self.n_p:
            return f"P{idx}"
        return f"E{idx - self.n_p}"


def detect_core_layout() -> CoreLayout:
    """Read perflevel{0,1}.logicalcpu via sysctl. Falls back to flat layout."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.perflevel0.logicalcpu", "hw.perflevel1.logicalcpu"],
            capture_output=True, text=True, timeout=2.0,
        )
        if out.returncode == 0:
            parts = out.stdout.strip().split()
            if len(parts) == 2:
                n_p, n_e = int(parts[0]), int(parts[1])
                return CoreLayout(n_p=n_p, n_e=n_e, is_apple_silicon=True)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    n = psutil.cpu_count(logical=True) or 1
    return CoreLayout(n_p=n, n_e=0, is_apple_silicon=False)


@dataclass
class ProcEntry:
    pid: int
    name: str
    cpu: float        # percent of total system CPU (normalized by core count)
    mem_mb: float


@dataclass
class TempSnapshot:
    cpu_temp_c: Optional[float]
    gpu_temp_c: Optional[float]
    cpu_power_w: Optional[float]
    gpu_power_w: Optional[float]
    timestamp: float


_MACMON_CANDIDATES = (
    "macmon",
    "/opt/homebrew/bin/macmon",
    "/usr/local/bin/macmon",
)


def _find_macmon() -> Optional[str]:
    for cand in _MACMON_CANDIDATES:
        path = shutil.which(cand) if "/" not in cand else (cand if shutil.os.path.exists(cand) else None)
        if path:
            return path
    return None


class MacmonReader:
    """Background reader for `macmon pipe` JSON output.

    macmon (Apple Silicon, sudoless) emits one JSON object per interval on
    stdout. We spawn it once, read in a daemon thread, and expose the latest
    parsed snapshot. If macmon is not installed, latest() returns None.
    """

    def __init__(self, interval_ms: int = 1500) -> None:
        self._latest: Optional[TempSnapshot] = None
        self._stop = threading.Event()
        self._proc: Optional[subprocess.Popen] = None
        self._available = _find_macmon() is not None
        if self._available:
            self._thread = threading.Thread(
                target=self._run, args=(interval_ms,), daemon=True
            )
            self._thread.start()

    @property
    def available(self) -> bool:
        return self._available

    def _run(self, interval_ms: int) -> None:
        binary = _find_macmon()
        if binary is None:
            return
        try:
            self._proc = subprocess.Popen(
                [binary, "pipe", "-i", str(interval_ms)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except (FileNotFoundError, OSError):
            return

        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if self._stop.is_set():
                break
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            temp = data.get("temp", {}) or {}
            self._latest = TempSnapshot(
                cpu_temp_c=temp.get("cpu_temp_avg"),
                gpu_temp_c=temp.get("gpu_temp_avg"),
                cpu_power_w=data.get("cpu_power"),
                gpu_power_w=data.get("gpu_power"),
                timestamp=time.time(),
            )

    def latest(self) -> Optional[TempSnapshot]:
        return self._latest

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass


class HwMonitor:
    def __init__(self) -> None:
        self._last_disk = psutil.disk_io_counters()
        self._last_net = psutil.net_io_counters()
        self._last_time = time.time()
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

    def sample(self) -> HwSnapshot:
        now = time.time()
        dt = max(now - self._last_time, 1e-3)

        cpu = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        mem = psutil.virtual_memory().percent

        d = psutil.disk_io_counters()
        n = psutil.net_io_counters()

        disk_r = (d.read_bytes - self._last_disk.read_bytes) / dt / 1e6
        disk_w = (d.write_bytes - self._last_disk.write_bytes) / dt / 1e6
        net_r = (n.bytes_recv - self._last_net.bytes_recv) / dt / 1e6
        net_s = (n.bytes_sent - self._last_net.bytes_sent) / dt / 1e6

        self._last_disk = d
        self._last_net = n
        self._last_time = now

        return HwSnapshot(
            cpu=cpu,
            memory=mem,
            disk_read_mbps=max(disk_r, 0.0),
            disk_write_mbps=max(disk_w, 0.0),
            net_recv_mbps=max(net_r, 0.0),
            net_sent_mbps=max(net_s, 0.0),
            per_core=per_core,
            timestamp=now,
        )


class ProcessTracker:
    """Tracks per-process CPU/memory.

    cpu_percent(interval=None) gives the percent since the last call FOR THAT
    process. We prime once on init, then re-sample periodically (call sample()
    from the same timer that drives HwMonitor). On macOS a single process can
    report >100% CPU when it uses multiple cores, so we normalize by core count
    to match the system-wide CPU% shown elsewhere.
    """

    def __init__(self) -> None:
        self._n_cpus = max(psutil.cpu_count(logical=True) or 1, 1)
        self._top_cpu: list[ProcEntry] = []
        self._top_mem: list[ProcEntry] = []
        self._prime()

    def _prime(self) -> None:
        for p in psutil.process_iter(["pid"]):
            try:
                p.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def sample(self, top_n: int = 3) -> None:
        cpu_list: list[ProcEntry] = []
        mem_list: list[ProcEntry] = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                cpu_raw = p.cpu_percent(interval=None)
                mem_info = p.memory_info()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            name = p.info.get("name") or f"pid {p.info['pid']}"
            entry = ProcEntry(
                pid=p.info["pid"],
                name=name,
                cpu=cpu_raw / self._n_cpus,
                mem_mb=mem_info.rss / (1024 * 1024),
            )
            cpu_list.append(entry)
            mem_list.append(entry)
        cpu_list.sort(key=lambda e: e.cpu, reverse=True)
        mem_list.sort(key=lambda e: e.mem_mb, reverse=True)
        self._top_cpu = cpu_list[:top_n]
        self._top_mem = mem_list[:top_n]

    @property
    def top_cpu(self) -> list[ProcEntry]:
        return list(self._top_cpu)

    @property
    def top_mem(self) -> list[ProcEntry]:
        return list(self._top_mem)
