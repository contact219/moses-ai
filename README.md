# M.O.S.E.S
### Modular Omniscient System for Enhanced Services

A voice-activated AI desktop assistant powered by **Google Gemini Live**. Moses listens for his name, understands natural speech, and can control your computer, search the web, manage files, play videos, send messages, write code, and more — all through conversation.

---

## Features

- 🎙 **Always-on voice** — wake word activated (`Moses`)
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
- 🧠 **Long-term + episodic memory** — remembers your preferences *and* what you did together, and recalls it on topic
- 🔔 **Proactive** — gives spoken heads-ups before your reminders in his own voice
- 🎮 **Game updater** — Steam & Epic Games

---

## Requirements

- Ubuntu / Debian-based Linux (20.04+)
- Python 3.10 or higher
- A free **Google Gemini API key** — get one at https://aistudio.google.com/app/apikey
- Microphone and speakers
- Internet connection

---

## Installation

### One-command install

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

**Double-click the Moses icon** on your Desktop.

Or from terminal:

```bash
cd /path/to/moses-ai
./start_jarvis.sh
```

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
│   └── prompt.txt        # Moses personality & system prompt
├── config/
│   ├── api_keys.template.json
│   └── api_keys.json     # ← YOU CREATE THIS (gitignored)
├── memory/
│   ├── memory_manager.py
│   └── long_term.json    # ← auto-generated, gitignored
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
| `Moses, goodbye` | Shuts down |

### What's new under the hood

- **One voice everywhere.** The task/agent layer now speaks as Moses (no more "sir"); the planner/executor share a single identity and a cached Gemini client.
- **Multi-step tasks pass data.** Plan steps can reference earlier results with `{{stepN}}` — e.g. research, then write the findings to a file for real.
- **Episodic memory** (`memory/episodes.json`) records what you did together; `recall_memory` searches it on demand.
- **Proactive nudges** — reminders now also come through Moses's own voice, with a heads-up beforehand.
- **Safety** — generated code is screened for destructive operations before it ever runs; the vision voice no longer feeds back into the mic.

---

## License

MIT — free to use, modify, and distribute.
