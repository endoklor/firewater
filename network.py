"""
network.py — Сетевой менеджер (LAN мультиплеер через TCP-сокеты)

Протокол (простой текст):
  - Сервер шлёт клиенту номер уровня:  "LEVEL:<idx>\n"
  - Клиент подтверждает:               "READY\n"
  - Обе стороны шлют позицию:          "POS:<x>,<y>,<vx>,<vy>,<on_ground>\n"
"""

import socket
import threading
import queue
from enum import Enum

PORT    = 5555
BUFSIZE = 1024


class NetworkRole(Enum):
    SERVER = "server"
    CLIENT = "client"


class NetworkManager:
    def __init__(self, role: NetworkRole):
        self.role      = role
        self.sock      = None
        self.conn      = None   # сторона соединения (для сервера — принятый сокет)
        self._connected = False
        self._recv_q   = queue.Queue()
        self._send_q   = queue.Queue()
        self._lock     = threading.Lock()
        self._error    = None

    # ─── Сервер ─────────────────────────────────────────────
    def start_server(self, level_idx: int):
        """Создаёт сервер, ждёт клиента (блокирует до подключения)."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", PORT))
        self.sock.listen(1)
        self.sock.settimeout(60)
        conn, addr = self.sock.accept()
        self.conn = conn
        self.conn.setblocking(False)
        # Отправляем уровень
        self._raw_send(f"LEVEL:{level_idx}\n")
        # Ждём READY
        resp = self._wait_line(timeout=10)
        if resp != "READY":
            raise ConnectionError("Клиент не подтвердил уровень")
        self._connected = True
        self._start_io_threads()

    # ─── Клиент ─────────────────────────────────────────────
    def connect_to_server(self, host: str) -> int:
        """Подключается к серверу, возвращает номер уровня."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((host, PORT))
        self.conn = self.sock
        self.conn.setblocking(False)
        # Читаем уровень
        line = self._wait_line(timeout=10)
        if not line.startswith("LEVEL:"):
            raise ConnectionError(f"Неожиданный ответ: {line}")
        level_idx = int(line.split(":")[1])
        self._raw_send("READY\n")
        self._connected = True
        self._start_io_threads()
        return level_idx

    # ─── Публичный API (из основного потока) ────────────────
    def is_connected(self) -> bool:
        return self._connected

    def send_state(self, x: float, y: float, vx: float, vy: float, on_ground: bool):
        """Ставит пакет в очередь отправки."""
        og = 1 if on_ground else 0
        msg = f"POS:{x:.1f},{y:.1f},{vx:.1f},{vy:.1f},{og}\n"
        try:
            self._send_q.put_nowait(msg)
        except queue.Full:
            pass

    def recv_state(self):
        """Возвращает последнее принятое состояние или None."""
        last = None
        while not self._recv_q.empty():
            try:
                last = self._recv_q.get_nowait()
            except queue.Empty:
                break
        return last

    def close(self):
        self._connected = False
        try:
            if self.conn:
                self.conn.close()
            if self.sock and self.sock is not self.conn:
                self.sock.close()
        except Exception:
            pass

    # ─── Внутренние потоки I/O ──────────────────────────────
    def _start_io_threads(self):
        threading.Thread(target=self._send_loop, daemon=True).start()
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _send_loop(self):
        buf = b""
        while self._connected:
            try:
                msg = self._send_q.get(timeout=0.05)
                buf += msg.encode()
            except queue.Empty:
                pass
            if buf:
                try:
                    sent = self.conn.send(buf)
                    buf = buf[sent:]
                except BlockingIOError:
                    pass
                except Exception:
                    self._connected = False
                    break

    def _recv_loop(self):
        buf = ""
        while self._connected:
            try:
                data = self.conn.recv(BUFSIZE)
                if not data:
                    self._connected = False
                    break
                buf += data.decode(errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    self._process_line(line.strip())
            except BlockingIOError:
                import time; time.sleep(0.005)
            except Exception:
                self._connected = False
                break

    def _process_line(self, line: str):
        if line.startswith("POS:"):
            parts = line[4:].split(",")
            if len(parts) == 5:
                x, y, vx, vy, og = parts
                state = (float(x), float(y), float(vx), float(vy), og == "1")
                try:
                    self._recv_q.put_nowait(state)
                except queue.Full:
                    try:
                        self._recv_q.get_nowait()
                        self._recv_q.put_nowait(state)
                    except queue.Empty:
                        pass

    # ─── Вспомогательные ────────────────────────────────────
    def _raw_send(self, msg: str):
        """Синхронная отправка (только до запуска потоков)."""
        data = msg.encode()
        self.conn.setblocking(True)
        self.conn.sendall(data)
        self.conn.setblocking(False)

    def _wait_line(self, timeout: float = 10) -> str:
        """Читает одну строку синхронно (только при handshake)."""
        import time
        self.conn.setblocking(True)
        self.conn.settimeout(timeout)
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = self.conn.recv(256)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    line = buf.split(b"\n")[0].decode().strip()
                    self.conn.setblocking(False)
                    return line
            except socket.timeout:
                break
        self.conn.setblocking(False)
        raise TimeoutError("Нет ответа от партнёра")
