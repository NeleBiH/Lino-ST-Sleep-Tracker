# Lino-ST Sleep Tracker

A modern, cross-platform sleep tracking application built with PySide6 that monitors and records sounds while you sleep.

<img width="797" height="826" alt="main" src="https://github.com/user-attachments/assets/6de1e50f-743b-46f1-ace8-a02f52200a15" />
<img width="797" height="826" alt="history" src="https://github.com/user-attachments/assets/9b787cde-cac4-4fdf-928f-a5575a7e3d86" />
<img width="797" height="826" alt="settings" src="https://github.com/user-attachments/assets/28c2252d-80dd-4970-84cc-65921ca8fd55" />

# Lino-ST Sleep Tracker
-------------------------------------------------------------------------------------------------------------------------------------------------
<img width="472" height="370" alt="Screenshot_20251212_211636" src="https://github.com/user-attachments/assets/826235fd-76ee-4ad8-ab82-85de55c98c5a" />


## Features

- 🎤 **Smart Audio Recording** - Automatically records when sound exceeds threshold
- 📊 **Live Audio Monitoring** - Real-time microphone level meter (dB and percentage)
- 🌊 **Waveform Visualization** - Visual waveform display for each recording
- 📅 **Sleep Session History** - Track your sleep patterns over time
- 🌍 **Multi-language Support** - English, Croatian, German
- ⚙️ **Customizable Settings** - Date/time formats, audio formats (OGG/WAV)
- 💾 **Export Functionality** - Export recordings to ZIP archive
- 🎨 **Modern Dark UI** - Beautiful glossy dark theme with smooth animations
- 🔊 **Audio Playback** - Built-in player for recordings
- 🗑️ **Easy Management** - Delete individual or all recordings
- 📱 **System Tray** - Minimize to tray with wake lock support
- 🎛️ **Audio Format Selection** - Choose between OGG (smaller) and WAV (uncompressed)
- 📋 **Enhanced Tables** - Grid lines and centered text for better readability

## Requirements

- Python 3.8+
- PortAudio (system library)
- GStreamer plugins (for audio playback)

### System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install libportaudio2 portaudio19-dev python3-dev libsndfile1 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
```

**Fedora:**
```bash
sudo dnf install portaudio portaudio-devel python3-devel libsndfile gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-bad-free gstreamer1-plugins-ugly
```

**Arch Linux:**
```bash
sudo pacman -S portaudio libsndfile gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly
```

**openSUSE:**
```bash
sudo zypper install portaudio-devel libsndfile1 gstreamer-plugins-base gstreamer-plugins-good gstreamer-plugins-bad gstreamer-plugins-ugly
```

## Installation

### From Source

1. Clone the repository:
```bash
git clone https://github.com/yourusername/Lino-ST-Sleep-Tracker.git
cd Lino-ST-Sleep-Tracker
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python "Lino-ST.py"
```

### Using Install Script (Linux)

```bash
chmod +x install.sh
./install.sh
```

This will:
- Detect your Linux distribution
- Install system dependencies
- Create virtual environment
- Install Python dependencies
- Create desktop entry and icons
- Install to `~/.local/share/sleepypenguin/`

## Usage

1. **Start Monitoring** - Click the Start button to begin audio monitoring
2. **Adjust Sensitivity** - Use the Microphone Sensitivity slider (right = more sensitive)
3. **Set Clip Length** - Configure maximum recording length (0 = unlimited)
4. **View Recordings** - Recordings appear automatically in the list below
5. **Play Recordings** - Use Play/Stop buttons to preview recordings
6. **Manage Files** - Delete individual recordings or use Delete All in Settings
7. **Export Data** - Export all recordings to ZIP archive from Settings
8. **View History** - Check the History tab for past sleep sessions
9. **Customize** - Configure date/time format and audio format (OGG/WAV) in Settings

## Audio Formats

- **OGG Vorbis** (Recommended) - Smaller file sizes, good quality
- **WAV** - Uncompressed, larger files but maximum compatibility

## Data Storage

- **Recordings**: `./recordings/` (relative to app directory)
- **Session History**: `~/.config/Lino-ST/sessions.json`

## Building

### AppImage (Linux)

```bash
chmod +x build-appimage.sh
./build-appimage.sh
```

This creates a portable AppImage in the project directory:
- `Lino-ST-0.2-x86_64.AppImage` (~258MB)

### Manual Build

```bash
# Install dependencies
pip install -r requirements.txt

# Run application
python "Lino-ST.py"
```

## Configuration

The application stores configuration in:
- `~/.config/Lino-ST/` - User settings and session history
- `./recordings/` - Audio recordings

## Troubleshooting

### Audio Issues

If you encounter audio problems:

1. **Check PortAudio installation:**
```bash
python -c "import sounddevice; print('PortAudio OK')"
```

2. **Run with setup helper:**
```bash
python "Sleep tracker.py" --setup
```

3. **Check microphone permissions** - Ensure the app has access to your microphone

### Common Issues

- **No audio input**: Check system microphone permissions and PortAudio installation
- **Crash on startup**: Run with `--setup` to install missing dependencies
- **Recording issues**: Adjust microphone sensitivity slider
- **License dialog empty**: Restart application (license is now hardcoded)

## Development

### Project Structure

```
Lino-ST-Sleep-Tracker/
├── Lino-ST.py               # Main application
├── requirements.txt          # Python dependencies
├── install.sh              # Linux install script
├── uninstall.sh            # Linux uninstall script
├── build-appimage.sh       # AppImage build script
├── image.png              # About dialog image
├── Icons/                 # Application icons
├── recordings/            # Audio recordings (created at runtime)
└── README.md             # This file
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE.MD](LICENSE.MD) file for details.

## Changelog

### Version 0.2
- ✨ Added audio format selection (OGG/WAV)
- 🎨 Improved UI with table grid lines and centered text
- 🖼️ Added image to About dialog
- ⚙️ Moved action buttons to Settings tab
- 🐛 Fixed dialog button styling
- 🔧 Enhanced transparency handling for images
- 🏷️ Renamed project from SleepyPenguin to Lino-ST
- 📄 Hardcoded MIT license in application
- 📚 Updated help documentation with new features

### Version 0.1
- 🎤 Initial release with core sleep tracking functionality
- 📊 Basic audio monitoring and recording
- 🌍 Multi-language support
- 📅 Session history tracking

## Support

If you encounter any issues or have suggestions:

1. Check the [Troubleshooting](#troubleshooting) section
2. Search existing [GitHub Issues](https://github.com/yourusername/Lino-ST-Sleep-Tracker/issues)
3. Create a new issue with detailed information

## Acknowledgments

- [PySide6](https://doc.qt.io/qtforpython/) - Qt for Python
- [NumPy](https://numpy.org/) - Numerical computing
- [sounddevice](https://python-sounddevice.readthedocs.io/) - Audio I/O
- [soundfile](https://python-soundfile.readthedocs.io/) - Audio file handling

---

**Lino-ST Sleep Tracker** - Your desktop companion for better sleep understanding.
