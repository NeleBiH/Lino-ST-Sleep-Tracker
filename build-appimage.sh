#!/bin/bash
# SleepyPenguin - Sleep Tracker
# AppImage build script
# This script creates a portable AppImage package

set -e

APP_NAME="Lino-ST"
APP_ID="io.github.lino-st"
VERSION="0.2"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Lino-ST AppImage Builder ===${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build-appimage"
APPDIR="$BUILD_DIR/$APP_NAME.AppDir"

# Check for Lino-ST.py
if [ ! -f "$SCRIPT_DIR/Lino-ST.py" ]; then
    echo -e "${RED}Error: 'Lino-ST.py' not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# Check Python availability
check_python() {
    echo -e "${BLUE}Checking Python installation...${NC}"

    # Try python3 first, then python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        # Check if it's Python 3
        PY_VERSION=$(python --version 2>&1 | grep -oP '\d+' | head -1)
        if [ "$PY_VERSION" = "3" ]; then
            PYTHON_CMD="python"
        else
            PYTHON_CMD=""
        fi
    else
        PYTHON_CMD=""
    fi

    if [ -z "$PYTHON_CMD" ]; then
        echo -e "${RED}Error: Python 3 is not installed!${NC}"
        echo "Please install Python 3 first."
        exit 1
    fi

    # Get Python version
    PY_FULL_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+')
    echo -e "  Found: $PYTHON_CMD (version $PY_FULL_VERSION)"

    # Check for venv module
    if ! $PYTHON_CMD -c "import venv" 2>/dev/null; then
        echo -e "${RED}Error: Python venv module not found!${NC}"
        echo "Please install python3-venv package."
        exit 1
    fi
    echo -e "  venv module: ${GREEN}OK${NC}"

    # Check for pip
    if ! $PYTHON_CMD -m pip --version &>/dev/null; then
        echo -e "${RED}Error: pip not found!${NC}"
        echo "Please install python3-pip package."
        exit 1
    fi
    echo -e "  pip: ${GREEN}OK${NC}"
}

check_python
echo ""

# Check for wget
if ! command -v wget &> /dev/null; then
    echo -e "${RED}Error: wget is required for downloading appimagetool${NC}"
    exit 1
fi

# Download appimagetool if not present
mkdir -p "$BUILD_DIR"
APPIMAGETOOL="$BUILD_DIR/appimagetool-x86_64.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo -e "${BLUE}Downloading appimagetool...${NC}"
    wget -q --show-progress -O "$APPIMAGETOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
    echo ""
fi

# Clean previous build
echo -e "${BLUE}Preparing build directory...${NC}"
rm -rf "$APPDIR"
mkdir -p "$APPDIR"

# Create AppDir structure
echo "Creating AppDir structure..."
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/metainfo"

# Copy main application
echo "Copying application files..."
cp "$SCRIPT_DIR/Lino-ST.py" "$APPDIR/usr/bin/"
cp "$SCRIPT_DIR/LICENSE.MD" "$APPDIR/usr/" 2>/dev/null || true
cp "$SCRIPT_DIR/requirements.txt" "$APPDIR/usr/" 2>/dev/null || true
cp "$SCRIPT_DIR/image.png" "$APPDIR/usr/" 2>/dev/null || true

# Copy icons
if [ -d "$SCRIPT_DIR/Icons" ]; then
    cp -r "$SCRIPT_DIR/Icons" "$APPDIR/usr/"
    # Copy main icon for AppImage
    if [ -f "$SCRIPT_DIR/Icons/icon_256x256.png" ]; then
        cp "$SCRIPT_DIR/Icons/icon_256x256.png" "$APPDIR/$APP_NAME.png"
        cp "$SCRIPT_DIR/Icons/icon_256x256.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"
        cp "$SCRIPT_DIR/Icons/icon_256x256.png" "$APPDIR/.DirIcon"
    fi
fi

# Create recordings directory
mkdir -p "$APPDIR/usr/bin/recordings"

# Install dependencies to system Python (no venv for AppImage)
echo ""
echo -e "${BLUE}Installing Python dependencies (system-wide)...${NC}"
$PYTHON_CMD -m pip install --upgrade pip --quiet
if [ -f "$APPDIR/usr/requirements.txt" ]; then
    $PYTHON_CMD -m pip install -r "$APPDIR/usr/requirements.txt" --quiet --target "$APPDIR/usr/lib/python-packages"
else
    $PYTHON_CMD -m pip install PySide6 numpy sounddevice soundfile --quiet --target "$APPDIR/usr/lib/python-packages"
fi
echo -e "  Python packages: ${GREEN}OK${NC}"

# Get the Python version
PY_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "  Python version: ${GREEN}$PY_VERSION${NC}"

# Create desktop file
echo ""
echo -e "${BLUE}Creating metadata files...${NC}"
cat > "$APPDIR/$APP_NAME.desktop" << DESKTOP
[Desktop Entry]
Name=Lino-ST
Comment=Sleep Tracker - Record sounds while you sleep
Exec=lino-st
Icon=$APP_NAME
Terminal=false
Type=Application
Categories=Utility;Audio;
Keywords=sleep;tracker;audio;recording;
StartupWMClass=sleepypenguin
X-AppImage-Version=$VERSION
DESKTOP

cp "$APPDIR/$APP_NAME.desktop" "$APPDIR/usr/share/applications/"

# Create AppRun script with proper Python paths
echo "Creating AppRun script..."
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
# Lino-ST AppImage launcher
SELF=$(readlink -f "$0")
HERE=${SELF%/*}

# Set up Python environment using system Python with bundled packages
export PYTHONPATH="$HERE/usr/lib/python-packages:$PYTHONPATH"

# Set up Qt paths
export QT_PLUGIN_PATH="$HERE/usr/lib/python-packages/PySide6/Qt/plugins"
export QML2_IMPORT_PATH="$HERE/usr/lib/python-packages/PySide6/Qt/qml"

# Set up library paths for Qt
export LD_LIBRARY_PATH="$HERE/usr/lib/python-packages/PySide6/Qt/lib:$LD_LIBRARY_PATH"

# XDG paths for config/data
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

# Change to app directory for recordings
cd "$HERE/usr/bin"
export APP_DIR="$HERE/usr/bin"

# Run the application
exec "python3" "$HERE/usr/bin/Lino-ST.py" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# Create AppStream metadata
cat > "$APPDIR/usr/share/metainfo/$APP_ID.appdata.xml" << APPDATA
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>$APP_ID</id>
  <name>Lino-ST</name>
  <summary>Sleep Tracker - Record sounds while you sleep</summary>
  <metadata_license>MIT</metadata_license>
  <project_license>MIT</project_license>
  <description>
     <p>
       Lino-ST is a sleep tracker application that monitors and records
       sounds while you sleep. It features automatic threshold-based recording,
       waveform visualization, and session history tracking.
     </p>
    <p>Features:</p>
    <ul>
     <li>Start/Stop microphone monitoring</li>
     <li>Auto-record when sound is detected</li>
     <li>Live microphone level meter</li>
     <li>Per-clip list with Play/Stop and Delete</li>
     <li>Language support (EN/HR/DE)</li>
     <li>Sleep session history</li>
     <li>EU/US date format support</li>
     <li>12h/24h time format support</li>
     <li>Audio format selection (OGG/WAV)</li>
     <li>Export recordings to ZIP</li>
     <li>Modern dark UI with glossy effects</li>
    </ul>
  </description>
  <launchable type="desktop-id">$APP_NAME.desktop</launchable>
   <url type="homepage">https://github.com/lino-st</url>
     <provides>
     <binary>lino-st</binary>
   </provides>
  <releases>
     <release version="$VERSION" date="$(date +%Y-%m-%d)">
       <description>
         <p>Version 0.2 with enhanced UI and audio format selection.</p>
       </description>
     </release>
  </releases>
  <content_rating type="oars-1.1" />
</component>
APPDATA

echo -e "  Metadata: ${GREEN}OK${NC}"

# Build AppImage
echo ""
echo -e "${BLUE}Building AppImage...${NC}"
cd "$BUILD_DIR"

# Set architecture
export ARCH=x86_64

# Run appimagetool
OUTPUT_FILE="$SCRIPT_DIR/${APP_NAME}-${VERSION}-x86_64.AppImage"
"$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT_FILE" 2>&1 | grep -v "^$" || true

if [ -f "$OUTPUT_FILE" ]; then
    chmod +x "$OUTPUT_FILE"
    echo ""
    echo -e "${GREEN}=== AppImage Build Complete! ===${NC}"
    echo ""
    echo "AppImage created: $OUTPUT_FILE"
    SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo "Size: $SIZE"
    echo ""
    echo "To run:"
    echo "  ./${APP_NAME}-${VERSION}-x86_64.AppImage"
    echo ""
    echo -e "${YELLOW}Note: Recordings will be saved inside the AppImage directory.${NC}"
    echo "For persistent storage, run from a fixed location or configure"
    echo "the recordings path in the application."
else
    echo -e "${RED}Error: AppImage creation failed!${NC}"
    exit 1
fi

# Cleanup option
echo ""
read -p "Remove build directory ($BUILD_DIR)? [y/N]: " cleanup
if [[ "$cleanup" =~ ^[Yy]$ ]]; then
    rm -rf "$BUILD_DIR"
    echo "Build directory removed."
fi
