# Desktop clap → Jarvis-style welcome

Python script that listens to your default microphone and runs a **double-clap** welcome flow (Spotify, Centro de Comando Jarvis panel in Chrome, spoken welcome line, Cursor). The same sequence also fires on the global hotkey **`Ctrl+Alt+J`** (independent of the microphone) and on the offline wake word **"Ei Jarvis"** / **"Ei sistema"** (same flow, but never opens Cursor). See constants at the top of `jarvis.py` for behavior and tuning.

`jarvis_companion.py` is a separate always-on-top chat window with an animated orb (blue idle, orange + pulsing while Jarvis speaks) that talks to Claude via the `claude` CLI, routing Mania de Mulher marketing requests to the specialist agents. Run it with `python jarvis_companion.py`.

## Setup

From this project directory:

```bash
python -m pip install -r requirements.txt
```

## Environment variables

The script loads an optional **`.env` file** in the same folder as `jarvis.py` (via `python-dotenv`). You can also set variables in the shell. None are required — the welcome line uses the Windows native SAPI voice (`System.Speech`), no account or API key needed.

### Optional

| Variable | Purpose |
| -------- | ------- |
| `JARVIS_INPUT_DEVICE` | Optional mic override: **integer** index or **substring** of the device name. If unset, the script uses the Windows default; when that mic is silent, it auto-picks the loudest working input. List devices: `python -c "import sounddevice as sd; print(sd.query_devices())"`. |
| `CRM_URL` | URL opened for the Centro de Comando Jarvis panel in Chrome (default: the published panel). |
| `CHROME_NEW_WINDOW_WAIT_S` | Seconds to wait for a new Chrome window on Windows (default `25`). |
| `CHROME_WINDOW_WIDTH` / `CHROME_WINDOW_HEIGHT` | Windowed Chrome size when not fullscreen. |

## Run

```bash
python jarvis.py
```

Allow the microphone if Windows prompts you. Stop with **Ctrl+C**.

## Tuning

Edit the constants at the top of `jarvis.py`:

| Constant      | Effect                                                            |
| ------------- | ----------------------------------------------------------------- |
| `SPIKE_RATIO` | Increase if you get false triggers; decrease if claps are missed. |
| `COOLDOWN_S`  | Minimum time between two logged claps.                            |
| `BLOCK_MS`    | Larger = slightly less CPU, a bit less precise timing.            |
| `MIN_RMS`     | Floor on how loud a block must be (helps in very quiet rooms).  |
| `SAMPLE_RATE` | Try `48000` if your device does not like `44100`.                 |

## Wake word ("Ei Jarvis" / "Ei sistema")

Offline, via [Vosk](https://alphacephei.com/vosk/models) — no account, no internet needed at runtime. The small Portuguese model lives at `%LOCALAPPDATA%\JarvisWakeWord\vosk-model-small-pt-0.3` (**not** inside this project folder — Vosk's C++ loader fails on the accented "Área" in this path). Re-download from `https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip` and extract there if missing.

The small pt-BR model has no "jarvis" in its vocabulary at all (confirmed empirically — even grammar-constrained decoding drops the word). Saying "Jarvis" is consistently misheard by this model as **"árvores"** instead (tested across several phonetic variants and two TTS voices) — `WAKE_WORD_TRIGGERS` in `jarvis.py` matches on that mishearing, so "Ei Jarvis" works in practice. "Ei sistema" is a real word the model recognizes directly and is kept as a reliable fallback.

**Trade-off:** "árvores" and "sistema" are ordinary Portuguese words, so this is more prone to accidental triggers than a truly distinctive wake word — `WAKE_WORD_COOLDOWN_S` limits how often that costs anything. If your own voice gets misheard as something other than "árvores"/"sistema", set `JARVIS_LOG_LEVEL=DEBUG` in `.env` to see every recognized phrase in the log, then add it to `WAKE_WORD_TRIGGERS`.

## Troubleshooting

- **Wrong or quiet mic:** On startup the script probes your default Windows input. If it is silent, it **auto-selects** the loudest working mic. To force a specific device, set `JARVIS_INPUT_DEVICE` in `.env` (index or name substring from `sounddevice.query_devices()`). Note the default mic can change between runs (e.g. Bluetooth earbuds vs. the laptop mic) — a Bluetooth headset mic will not hear your speakers, which matters for both clap and wake-word detection.
- **PortAudio / audio errors:** Update audio drivers or try another `SAMPLE_RATE`.
- **No reaction to claps:** Lower `SPIKE_RATIO` slightly or speak/clap closer to the mic.
- **Spam logs:** Raise `SPIKE_RATIO` or `COOLDOWN_S`.
- **No welcome speech:** Native TTS only runs on Windows; check that `System.Speech` / PowerShell is available and unblocked on your machine.
- **"Ei Jarvis" / "Ei sistema" not detected:** Confirm the model folder above exists; check the startup log for `Say "Ei Jarvis" or "Ei sistema"...` — if it's missing, the model failed to load (see the WARNING line above it). If the model loads but nothing triggers, set `JARVIS_LOG_LEVEL=DEBUG` and check what the engine is actually hearing.
