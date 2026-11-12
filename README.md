# M.O.S.E.S
### Modular Omniscient System for Enhanced Services

A voice-activated AI desktop assistant powered by **Google Gemini Live** — with two personalities, **Moses** and **Mina**, sharing one memory of you. Moses listens for his name, understands natural speech, and can control your computer, search the web, manage files, play videos, send messages, write code, and more — all through conversation.

---

## Features

- 🎙 **Always-on voice** — wake word activated (`Moses`)
- 👥 **Moses & Mina** — switch by voice, the MOSES | MINA buttons, or **F6**; each has their own voice, face, colours and conversation style, and both share the same memory
- 🗣 **Natural turn-taking** — talk over him and he stops mid-sentence (barge-in, tuned for speakers without echo cancellation); conversations survive Gemini's session limits without losing the thread
- 🎭 **Talking-face HUD** — portrait plays a talking video while the persona is speaking
- 🖥 **Full desktop control** — apps, windows, volume, brightness, screenshots
- 🌐 **Browser automation** — Chrome, Firefox, Edge, Brave via Playwright
- 🔍 **Web search** — DuckDuckGo + Google
- 📁 **File management** — create, move, read, organize
- 🎬 **YouTube** — play, summarize, trending
- ☁️ **Weather, flights, reminders**
- 💻 **Code helper & dev agent** — writes, runs, and fixes code
- 📸 **Screen vision** — analyzes what's on screen or webcam
- 👁 **Vision-driven control** — sees the screen and operates the GUI step by step
- 📂 **Document search** — answers questions from your own files (Documents/Desktop/Downloads)
- 🧠 **Long-term + episodic memory** — remembers your preferences *and* what you did together, and recalls it on topic — by meaning, not just keywords
- 🔒 **Memory you can trust** — identity, health and relationship facts are never trimmed; "forget that" really deletes (and he says so only if it did); nothing said mid-conversation is lost if the app closes
- 🔔 **Proactive** — gives spoken heads-ups before your reminders in his own voice
- 🎮 **Game updater** — Steam & Epic Games

---

## Requirements

- **Linux:** Ubuntu / Debian-based (20.04+), Python 3.10 or higher
- **Windows:** Windows 10 or 11 — the installer finds Python 3.12+ or offers to install it
- A free **Google Gemini API key** — get one at https://aistudio.google.com/app/apikey
- Microphone and speakers
- Internet connection

---

## Installation

### Linux — one-command install

```bash
git clone https://github.com/contact219/moses-ai.git
cd moses-ai
chmod +x install.sh
./install.sh
```

The installer will:
1. Install all system dependencies via `apt`
2. Create a Python virtual environment
3. Install all Python packages
4. Install Playwright (Chromium browser automation)
5. Create `config/api_keys.json` from the template
6. Create a **Moses** desktop icon

### Windows

1. Download the repo (**Code → Download ZIP** and unzip it, or `git clone https://github.com/contact219/moses-ai.git`).
2. Double-click **`install.bat`**.

The installer will:
1. Find Python 3.12+ (or offer to install Python 3.13 with `winget`)
2. Create a Python virtual environment in `env\`
3. Install the Windows packages from `requirements.txt`
4. Install Playwright's Chromium browser
5. Set up `config\api_keys.json` for Windows and ask for your Gemini API key
6. Create a **Moses** shortcut on the Desktop and in the Start Menu

The shortcut starts Moses without a console window and writes his log to `logs\moses.log`. To watch the log live (handy when something's wrong), run **`start_moses.bat`** instead.

---

## Configuration

After install, open `config/api_keys.json`:

```json
{
    "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
    "os_system": "linux"
}
```

Replace `YOUR_GEMINI_API_KEY_HERE` with your Gemini API key.  
Leave `os_system` as `linux`.

> Get a free Gemini API key at **https://aistudio.google.com/app/apikey**

---

## Running Moses

**Double-click the Moses icon** on your Desktop (Windows: also in the Start Menu).

Or from terminal:

```bash
cd /path/to/moses-ai
./start_jarvis.sh
```

Launching a second time brings the running Moses forward instead of starting another.

### The orb, the tray icon and keyboard shortcuts

Closing the window does **not** quit Moses. He stays on the desktop as a small orb (always on top, drag it anywhere) and a tray icon, still listening.

| On the orb | Does |
|---|---|
| Click | Open / hide the HUD |
| Middle-click | Mute / unmute |
| Right-click | Menu: open, look at my screen, recent notes, mute, wake word, switch persona, hide the orb, **quit** |

The orb moves with the audio: his colour while he speaks, white while he hears you, two amber arcs while he thinks, struck through when muted.

To reach him from any app, `mosesctl.py` sends a command to the running Moses, and your desktop's keyboard settings run it:

```bash
env/bin/python mosesctl.py --install-shortcuts   # GNOME: Ctrl+Alt+M show/hide, Ctrl+Alt+Space mute, Ctrl+Alt+L look at my screen
env/bin/python mosesctl.py --remove-shortcuts
env/bin/python mosesctl.py toggle|look|notes|mute|talk|quiet|wake|persona|orb|show|hide|quit
```

On another desktop, bind any key to `mosesctl.py toggle` in its shortcut settings.

### "Look at this"

Press **Ctrl+Alt+L** (or *Look at my screen* in the orb menu) and Moses sees what is on your screen and responds to it — an error message, a chart, a page you are reading. A thumbnail beside the orb shows exactly what he was given; the orb steps out of the way for the capture. It also wakes him if the wake word is on.

On Wayland the picture is taken through the desktop's screenshot portal; GNOME asks once whether to allow it. (The older capture returned an all-black image under Wayland, so his *what's on my screen?* tool now uses the same route.) Each capture is read and deleted from `~/Pictures` straight away.

### Note cards

When something is better read or copied than heard — an address, a phone number, a list, a confirmation code, a text to send, or the exact line to say — Moses puts it on screen as a card beside the orb, and says so briefly instead of reading it all out. Each card has **Copy** (lines to say get *Copy line*), can be dragged anywhere, and stays until you close it (× or Esc). Up to four are shown at once; every note is also saved to `memory/notes.json`, and *Show recent notes* in the orb menu (or `mosesctl.py notes`) brings the last three back.

### Wake word (optional)

By default Moses is always listening: the microphone is streamed to Google whenever he is not speaking, and his instructions tell him to answer only when addressed. With the wake word on, a small recogniser on this machine listens instead, and **nothing leaves the computer until you say "Moses" or "Mina"**. He then stays with you for the conversation — you do not repeat his name each turn — and goes quiet again about ten seconds after it ends. The HUD shows `SAY "MOSES"` and the orb dims while he is not listening.

```bash
env/bin/python -m core.wake_word --install   # once: fetches the model (about 17 MB) into ~/.moses/models/kws
env/bin/python -m core.wake_word --test      # 20 seconds: say the names a few times and see what it hears
env/bin/python mosesctl.py wake              # switch it on or off (also in the orb / tray menu)
env/bin/python mosesctl.py talk              # wake him without saying his name (worth binding to a key)
```

It is off until you switch it on, because only your voice on your microphone shows whether it hears you. Typing a line, or `mosesctl.py talk`, wakes him too.

| Setting (environment variable) | Effect |
|---|---|
| `MOSES_HUD=classic` | The original painted HUD instead of the GPU scene |
| `MOSES_ORB=0` | No orb (closing the window then quits, unless there is a tray icon) |
| `MOSES_AEC=0` | No echo cancellation |
| `MOSES_WAKE=1` / `MOSES_WAKE=0` | Force the wake word on or off for one run |
| `QT_QPA_PLATFORM=wayland` | Native Wayland. On GNOME the orb then cannot stay on top or remember its place; by default Moses runs through X compatibility for that reason |

---

## First Launch

The first time Moses starts, a setup dialog will appear asking for your Gemini API key and OS. If you already edited `config/api_keys.json`, it will skip straight to the main interface.

Once the HUD appears and shows **LISTENING**, say:

> **"Moses"** — then give your command

---

## Updating

```bash
cd moses-ai
git pull
source env/bin/activate
pip install -r requirements-linux.txt --quiet
```

---

## Troubleshooting

**Desktop icon does nothing on GNOME:**
Right-click the icon → *Allow Launching*

**`sounddevice` error / no audio:**
```bash
sudo apt-get install portaudio19-dev
source env/bin/activate && pip install sounddevice
```

**PyQt6 crashes on launch:**
```bash
sudo apt-get install libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0
```

**Playwright browser not found:**
```bash
source env/bin/activate
playwright install chromium
playwright install-deps chromium
```

---

## Project Structure

```
moses-ai/
├── main.py               # Entry point — Gemini Live session manager
├── ui.py                 # PyQt6 HUD interface
├── start_jarvis.sh       # Launch script (activates venv + runs main.py)
├── install.sh            # One-shot Linux installer
├── requirements-linux.txt
├── core/
│   ├── prompt.txt        # Moses personality & conversation rules
│   ├── prompt-mina.txt   # Mina personality & conversation rules
│   ├── personas.py       # Moses/Mina: voice, face, palette, prompt
│   └── turn_taking.py    # Barge-in detector + turn latency timing
├── assets/               # moses-/mina-face .jpg portraits + .mp4 talking faces
├── config/
│   ├── api_keys.template.json
│   └── api_keys.json     # ← YOU CREATE THIS (gitignored)
├── memory/
│   ├── memory_manager.py # Facts, episodes, forgetting, crash-safe pending turns
│   ├── semantic.py       # Meaning-based recall (Gemini embeddings)
│   └── long_term.json    # ← auto-generated, gitignored (also episodes, embeddings, latency)
├── tests/                # Unit tests: turn-taking + memory
├── agent/                # Task queue & planner
├── actions/              # Tool implementations
│   ├── browser_control.py
│   ├── code_helper.py
│   ├── computer_control.py
│   ├── desktop.py
│   ├── dev_agent.py
│   ├── file_controller.py
│   ├── file_processor.py
│   ├── flight_finder.py
│   ├── game_updater.py
│   ├── open_app.py
│   ├── reminder.py
│   ├── screen_processor.py
│   ├── send_message.py
│   ├── weather_report.py
│   ├── web_search.py
│   └── youtube_video.py
└── jarvis_monitor.py     # Optional system monitor widget
```

---

## Voice Commands (Examples)

| Say... | What happens |
|--------|-------------|
| `Moses, open Chrome` | Launches Chrome |
| `Moses, search for Python tutorials` | Web search |
| `Moses, what's on my screen?` | Analyzes screen with vision |
| `Moses, play lo-fi music on YouTube` | Plays on YouTube |
| `Moses, set a reminder for 3pm` | Creates a reminder |
| `Moses, write me a Python script that...` | Generates and saves code |
| `Moses, what's the weather in Houston?` | Opens weather search |
| `Moses, take a screenshot` | Screenshots desktop |
| `Moses, what did that invoice say about the total?` | Searches your own files (document search) |
| `Moses, log into the site on screen for me` | Sees the screen and drives the GUI (vision-act) |
| `Moses, what mics and cameras do I have?` | Lists attached audio + camera devices |
| `Moses, switch to my USB webcam` / `use my headphones` | Selects the input/output/camera device |
| `Moses, what was that thing I told you about my trip?` | Recalls from long-term + episodic memory |
| `Moses, forget my old address` | Deletes that memory (and tells you if nothing matched) |
| `Moses, let me talk to Mina` | Hands the conversation to Mina (or press **F6**) |
| `Moses, goodbye` | Shuts down |

### What's new — ported from the Moses & Mina web app

- **Conversation engine.** Talk over Moses and he stops within about half a second, then answers what you just said instead of resuming the old reply. The barge-in threshold learns how loud his own voice is through your speakers, so his echo doesn't cut him off. When Gemini rotates a live session, the conversation carries over (session resumption, or the last few exchanges as a fallback), and reconnects back off gently. Turn latency is logged to `memory/latency.jsonl`.
- **Mina.** A second persona with her own voice (Aoede), portrait, talking-face video, colour theme and prompt. Moses keeps his Charon voice. Switch by voice, button or F6; the swap waits for a natural pause, and the last few exchanges carry across.
- **Memory.** Protected categories (identity, health, relationships) and anything marked critical are never trimmed. `forget_memory` really deletes, across facts and past sessions. Turns are saved as they happen, so a crash doesn't lose them. Sessions are distilled into tagged episodes, shown with how long ago they happened so old news isn't treated as current. Recall adds meaning-based matches (gemini-embedding-2) as a fallback to keyword search.
- **How he talks.** The web app's conversation rules: short spoken turns, takes a side instead of both-sidesing, doesn't invent details of your life, and doesn't end every turn on a question. For heavy moments he gives his honest read and one small next step, and never steers you toward just moving on. Good news gets what it means for you, not a pat on the head.

### What's new — a presence on the desktop

- **A living HUD.** The centre of the window is now a particle scene on the graphics card, in the visual language of the web landing page, and it is driven by the real audio: it swells with his voice, draws inward and turns white while you speak, tightens into rings while he thinks, dims when muted. The ring of bars around the portrait is the actual spectrum of whoever is talking. It slows down when nothing is happening and stops drawing when the window is hidden. Measured fullscreen at 3440×1440 on a Quadro K620: 50 fps (the monitor's limit) at roughly a quarter of the CPU the painted HUD used.
- **The orb and shortcuts**, described under *Running Moses*.
- **Note cards** (the web app's `show_note`, as floating cards). Probed on the live model with both prompts: a card every time for an address, a shopping list, a text for the landlord and a line to say, and never for chat or a rough day (22/22 after one rule was tightened — the first run once said "here's a list you can copy" without making one).
- **"Look at this" (Ctrl+Alt+L).** The screen goes to him as part of a turn, the only way the live model reliably sees a picture (sent as a video frame it described a cat and a dog that weren't there). Captured through the screenshot portal on Wayland, about 1.8 s; tested with a known picture on screen (0.99 match) and in the running app, where he answered out loud about it.
- **Wake word (optional, off by default).** A 3-million-parameter keyword spotter runs locally at under 2 ms per audio chunk; while he is asleep no audio is sent anywhere, and the two seconds around his name are kept so "Moses, what's the weather" arrives whole. On 30 natural-voice test lines it heard 29, and 26–30 with this room's recorded noise mixed in at any plausible speaking level; near-homophones ("mimosa", "minimum") can wake him, and 26 minutes of continuous nameless speech produced one false wake.
- **Echo cancellation (Linux).** On start Moses asks PipeWire/PulseAudio for an echo-cancelled microphone and speaker pair and moves only his own audio onto it, so the mic no longer hears him through open speakers and talking over him is reliable without headphones. Your system's default devices are left as they were, and the pair is removed when he quits.

Run the tests with `env/bin/python -m unittest discover -s tests`.

### Earlier under the hood

- **One voice everywhere.** The task/agent layer now speaks as Moses (no more "sir"); the planner/executor share a single identity and a cached Gemini client.
- **Multi-step tasks pass data.** Plan steps can reference earlier results with `{{stepN}}` — e.g. research, then write the findings to a file for real.
- **Episodic memory** (`memory/episodes.json`) records what you did together; `recall_memory` searches it on demand.
- **Proactive nudges** — reminders now also come through Moses's own voice, with a heads-up beforehand.
- **Safety** — generated code is screened for destructive operations before it ever runs; the vision voice no longer feeds back into the mic.

---

## License

[CC BY-NC 4.0](LICENSE) — free to use, share and adapt for **non-commercial** purposes, with credit. This follows the license of the original MARK XXXIX project; commercial use is not permitted.

## Credits

Moses is built on **MARK XXXIX** by **FatihMakes** — the original cross-platform voice assistant this project grew from ([setup video](https://youtu.be/ej1f5OE3SNQ)).

