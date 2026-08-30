#!/usr/bin/env python3
"""
Jarvis Companion: a small always-on-top chat window with an animated orb
(blue idle, orange + pulsing while Jarvis speaks) that talks to Claude via
the `claude` CLI in print mode, routing marketing requests to the
agencia-mania-de-mulher specialist agents through --append-system-prompt.

Run:
  python jarvis_companion.py
"""

from __future__ import annotations

import base64
import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import uuid
import wave
from tkinter import scrolledtext

import numpy as np
import sounddevice as sd

BG = "#0a0e15"
PANEL = "#10151f"
LINE = "#232c3d"
TEXT = "#e7ebf3"
TEXT_DIM = "#98a3b8"
BLUE = (0x5B, 0x8D, 0xEF)
ORANGE = (0xFF, 0x8F, 0x4D)

SYSTEM_PROMPT = (
    "Voce e o Jarvis, assistente pessoal do Rafael, rodando como um app local de chat. "
    "Para qualquer pedido relacionado a Mania de Mulher (marketing, campanhas, dados, "
    "criativos, CRM, precificacao, performance, afiliadas), use a skill "
    "reuniao-estrategica-especialistas ou acione diretamente o agente especialista mais "
    "adequado do plugin agencia-mania-de-mulher. Para o resto, responda direto, curto e "
    "em portugues do Brasil."
)

N_POINTS = 240
EDGE_NEIGHBORS = 3
FPS_MS = 33


def fibonacci_sphere(n: int) -> list[tuple[float, float, float]]:
    pts = []
    golden_angle = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - (i / float(n - 1)) * 2
        radius = math.sqrt(max(0.0, 1 - y * y))
        theta = golden_angle * i
        pts.append((math.cos(theta) * radius, y, math.sin(theta) * radius))
    return pts


def build_edges(points: list[tuple[float, float, float]], k: int) -> list[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for i, p in enumerate(points):
        dists = []
        for j, q in enumerate(points):
            if i == j:
                continue
            d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
            dists.append((d, j))
        dists.sort(key=lambda t: t[0])
        for _, j in dists[:k]:
            edges.add((min(i, j), max(i, j)))
    return list(edges)


def lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> str:
    t = max(0.0, min(1.0, t))
    r = round(c1[0] + (c2[0] - c1[0]) * t)
    g = round(c1[1] + (c2[1] - c1[1]) * t)
    b = round(c1[2] + (c2[2] - c1[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class Orb:
    def __init__(self, canvas: tk.Canvas, size: int):
        self.canvas = canvas
        self.size = size
        self.points = fibonacci_sphere(N_POINTS)
        self.edges = build_edges(self.points, EDGE_NEIGHBORS)
        self.angle_y = 0.0
        self.angle_x = 0.0
        self.state = "idle"  # idle | thinking | speaking
        self.envelope: list[float] = []
        self.envelope_hop_s = 0.04
        self.speak_started_at = 0.0
        self.speak_duration = 0.0
        self._ids: list[int] = []

    def start_speaking(self, envelope: list[float], hop_s: float, duration_s: float) -> None:
        self.envelope = envelope
        self.envelope_hop_s = hop_s
        self.speak_duration = duration_s
        self.speak_started_at = time.monotonic()
        self.state = "speaking"

    def stop_speaking(self) -> None:
        self.state = "idle"

    def set_thinking(self, on: bool) -> None:
        self.state = "thinking" if on else "idle"

    def _current_level(self) -> float:
        if self.state != "speaking" or not self.envelope:
            return 0.0
        elapsed = time.monotonic() - self.speak_started_at
        if elapsed >= self.speak_duration:
            self.state = "idle"
            return 0.0
        idx = int(elapsed / self.envelope_hop_s)
        if idx < 0 or idx >= len(self.envelope):
            return 0.0
        return self.envelope[idx]

    def tick(self) -> None:
        for i in self._ids:
            self.canvas.delete(i)
        self._ids = []

        level = self._current_level()
        speaking = self.state == "speaking"
        thinking = self.state == "thinking"

        self.angle_y += 0.012 + (0.02 if speaking else 0.0)
        self.angle_x = 0.15 * math.sin(time.monotonic() * 0.5)

        pulse = 0.0
        if speaking:
            pulse = level * 0.22
        elif thinking:
            pulse = 0.05 + 0.04 * math.sin(time.monotonic() * 3.0)

        scale = self.size * 0.34 * (1.0 + pulse)
        cx = cy = self.size / 2
        cos_y, sin_y = math.cos(self.angle_y), math.sin(self.angle_y)
        cos_x, sin_x = math.cos(self.angle_x), math.sin(self.angle_x)

        proj: list[tuple[float, float, float]] = []
        for (x, y, z) in self.points:
            x1 = x * cos_y - z * sin_y
            z1 = x * sin_y + z * cos_y
            y2 = y * cos_x - z1 * sin_x
            z2 = y * sin_x + z1 * cos_x
            depth = z2 + 2.4
            f = 2.4 / depth
            px = cx + x1 * scale * f
            py = cy + y2 * scale * f
            proj.append((px, py, z2))

        color = lerp_color(BLUE, ORANGE, 1.0 if speaking else 0.0)
        if speaking:
            color = lerp_color(BLUE, ORANGE, 0.55 + 0.45 * level)

        for a, b in self.edges:
            xa, ya, za = proj[a]
            xb, yb, zb = proj[b]
            if za < -1.6 and zb < -1.6:
                continue
            width = 1
            self._ids.append(
                self.canvas.create_line(xa, ya, xb, yb, fill=color, width=width)
            )

        for (px, py, pz) in proj:
            if pz < -1.7:
                continue
            r = 1.6 if pz > 0 else 1.1
            self._ids.append(
                self.canvas.create_oval(px - r, py - r, px + r, py + r, fill=color, outline="")
            )


def render_tts_wav(text: str, wav_path: str) -> None:
    b64 = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
    safe_path = wav_path.replace("'", "''")
    ps_cmd = (
        "Add-Type -AssemblyName System.Speech; "
        f"$t = [System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{b64}')); "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{safe_path}'); "
        "$s.Speak($t); "
        "$s.Dispose()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )


def load_envelope(wav_path: str, hop_s: float = 0.04) -> tuple[list[float], float, int, np.ndarray]:
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)
    pcm_f = pcm.astype(np.float32) / 32768.0
    hop = max(1, int(rate * hop_s))
    n_chunks = max(1, len(pcm_f) // hop)
    levels = []
    for i in range(n_chunks):
        chunk = pcm_f[i * hop:(i + 1) * hop]
        levels.append(float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0)
    peak = max(levels) if levels else 0.0
    if peak > 1e-6:
        levels = [min(1.0, v / peak) for v in levels]
    duration = len(pcm_f) / rate if rate else 0.0
    return levels, duration, rate, pcm_f


def call_claude(message: str, session_id: str, is_first: bool) -> dict:
    args = [
        "claude", "-p", message,
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--append-system-prompt", SYSTEM_PROMPT,
    ]
    args += ["--session-id", session_id] if is_first else ["--resume", session_id]
    proc = subprocess.run(
        args,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        return {"is_error": True, "result": proc.stderr.strip() or "Falha ao chamar o Claude."}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"is_error": True, "result": proc.stdout.strip() or "Resposta ilegivel do Claude."}


class JarvisCompanion:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Jarvis")
        self.root.configure(bg=BG)
        self.root.geometry("420x600")
        self.root.attributes("-topmost", True)

        self.session_id = str(uuid.uuid4())
        self.first_message_sent = False
        self.busy = False
        self.events: queue.Queue = queue.Queue()

        orb_size = 220
        self.canvas = tk.Canvas(root, width=orb_size, height=orb_size, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(14, 6))
        self.orb = Orb(self.canvas, orb_size)

        self.log = scrolledtext.ScrolledText(
            root, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", wrap="word", state="disabled", font=("Segoe UI", 10),
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.log.tag_config("user", foreground=TEXT, justify="right")
        self.log.tag_config("jarvis", foreground=TEXT)
        self.log.tag_config("meta", foreground=TEXT_DIM, font=("Consolas", 8))
        self.log.tag_config("error", foreground="#f87171")

        bottom = tk.Frame(root, bg=BG)
        bottom.pack(fill="x", padx=12, pady=(0, 14))

        self.entry = tk.Entry(bottom, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self.send())

        self.send_btn = tk.Button(
            bottom, text="Enviar", command=self.send, bg="#5b8def", fg="#0a0e15",
            relief="flat", font=("Segoe UI", 10, "bold"), activebackground="#4a76c9",
        )
        self.send_btn.pack(side="right")

        self._append("Jarvis pronto. Digite uma mensagem abaixo.", "meta")
        self._animate()
        self._poll_events()

    def _append(self, text: str, tag: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.configure(state="disabled")
        self.log.see("end")

    def _animate(self) -> None:
        self.orb.tick()
        self.root.after(FPS_MS, self._animate)

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "response":
                    text, cost = payload
                    self._append(text, "jarvis")
                    self._append(f"custo: ${cost:.4f}", "meta")
                elif kind == "error":
                    self._append(payload, "error")
                elif kind == "done":
                    self.busy = False
                    self.send_btn.configure(state="normal")
        except queue.Empty:
            pass
        self.root.after(80, self._poll_events)

    def send(self) -> None:
        if self.busy:
            return
        message = self.entry.get().strip()
        if not message:
            return
        self.entry.delete(0, "end")
        self._append(message, "user")
        self.busy = True
        self.send_btn.configure(state="disabled")
        self.orb.set_thinking(True)
        threading.Thread(target=self._worker, args=(message,), daemon=True).start()

    def _worker(self, message: str) -> None:
        is_first = not self.first_message_sent
        self.first_message_sent = True
        result = call_claude(message, self.session_id, is_first)

        self.orb.set_thinking(False)

        if result.get("is_error"):
            self.events.put(("error", str(result.get("result", "Erro desconhecido."))))
            self.events.put(("done", None))
            return

        text = str(result.get("result", "")).strip() or "(sem resposta)"
        cost = float(result.get("total_cost_usd") or 0.0)
        self.events.put(("response", (text, cost)))

        try:
            wav_path = os.path.join(tempfile.gettempdir(), f"jarvis_companion_{uuid.uuid4().hex}.wav")
            render_tts_wav(text, wav_path)
            levels, duration, rate, pcm_f = load_envelope(wav_path)
            self.orb.start_speaking(levels, 0.04, duration)
            sd.play(pcm_f, rate)
            sd.wait()
            self.orb.stop_speaking()
            os.remove(wav_path)
        except Exception:
            self.orb.stop_speaking()

        self.events.put(("done", None))


def main() -> int:
    root = tk.Tk()
    JarvisCompanion(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
