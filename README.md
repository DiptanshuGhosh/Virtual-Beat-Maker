# 🥁 Virtual Drumkit — The Beat Maker

An interactive drum machine and digital piano built with **Python** and **Pygame**, letting you create, edit, save, and play custom drum beats and piano melodies through a clean, visual grid-based interface.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Pygame](https://img.shields.io/badge/Pygame-2.x-green.svg)

---

## ✨ Features

### 🥁 Drum Machine
- **6-instrument drum kit** — Hi-Hat, Snare, Bass Drum, Crash Cymbal, Floor Tom, and Clap
- **Visual step-sequencer grid** — click any cell to toggle a beat on/off (green = active, gray = inactive)
- **Real-time beat tracker** — a moving highlight shows exactly where you are in the loop
- **Adjustable BPM** — speed up or slow down playback in increments (default: 240 BPM)
- **Variable loop length** — from 8 up to 48+ beats per cycle
- **Channel mute/unmute** — isolate individual instruments while the rest keep playing
- **Play / Pause** — control playback without losing your pattern
- **Clear board** — instantly reset the grid
- **Save & Load system** — name and save beats to `saved_beats.txt`, then reload, edit, or delete them later

### 🎹 Digital Piano
- **Playable on-screen keyboard** — click keys (or use mapped computer-keyboard shortcuts) to play notes in real time
- **Multi-octave layout** with clearly labeled white and black keys
- **Sustain / release handling** so notes stop cleanly when a key is lifted
- **Layered with the drum grid** — play piano over your drum loop for quick melody + rhythm sketches
- **Visual key-press feedback** — pressed keys highlight so you can follow along visually

### ⚙️ Under the Hood
- Built entirely with `pygame` (`mixer`, `font`, `display`, `event`, `time.Clock`, `draw`)
- Multi-channel audio via `pygame.mixer.set_num_channels()` to avoid clipping when several sounds play at once
- Runs on a 60 FPS main loop for smooth animation and accurate timing
- Beat timing calculated as `beat_length = 3600 // bpm` for tempo-accurate playback
- Beats stored and parsed as structured strings for easy persistence and reloading

---

## 🖥️ Requirements

**Hardware**
- Intel i3 processor or above
- 2 GB RAM or more
- 2 GB free disk space

**Software**
- Windows 7 or later (or any OS with Python + Pygame support)
- Python 3.8+
- Recommended IDE: Visual Studio Code

---

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/<your-username>/virtual-drumkit.git
cd virtual-drumkit

# Install dependencies
pip install pygame

# Run the app
python beat_maker.py
```

---

## 🎮 Controls

| Action | How |
|---|---|
| Toggle a drum beat | Click a grid cell |
| Play / Pause | Click the **Play/Pause** button |
| Adjust tempo | **+5 / -5** BPM buttons |
| Adjust loop length | **+1 / -1** beats buttons |
| Mute/unmute instrument | Click the instrument label |
| Clear grid | Click **Clear Board** |
| Save a beat | Click **Save Beat** → type a name |
| Load a beat | Click **Load Beat** → select from list |
| Delete a saved beat | Click **Delete Beat** in the Load menu |
| Play piano notes | Click on-screen keys or use mapped keyboard keys |

---

## 🗂️ Project Structure

virtual-drumkit/
├── beat_maker.py # Main application (drum grid, piano, UI, game loop)
├── sounds/ # .wav files for drum samples and piano notes
├── saved_beats.txt # Auto-generated file storing saved beat patterns
├── Roboto-Bold.ttf # UI font
└── README.md
--

## 🧠 Concepts Demonstrated

- Event-driven programming & GUI development
- 2D grid-based data structures for state management
- Real-time audio processing with multiple simultaneous channels
- File I/O for persistent data storage/retrieval
- Object-oriented function design and modular code organization
- Timing and animation mathematics for a 60 FPS render loop

---

## 📋 Roadmap

- [ ] Export beats as `.wav`/`.mp3` audio files
- [ ] Record and play back piano melodies alongside drum loops
- [ ] Add more instrument/sound kits (selectable themes)
- [ ] MIDI input support for the piano
- [ ] Dark/light theme toggle

---

## 📚 Credits / References

- LeMaster Tech — "How to Program a Drum Kit in Python! Beat Making Code Tutorial!" (YouTube, May 2022)
- Stack Overflow — How does `collidepoint()` work in Pygame?
- GitHub community references

---

## 👤 Author

**Diptanshu Ghosh**
Computer Science Project (2025–26)

---

