#!/bin/bash
# SleepyPenguin - Sleep Tracker
# Installation script for Linux
# This script installs the application from source

set -e

APP_NAME="lino-st"
APP_DISPLAY_NAME="Lino-ST"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Lino-ST Sleep Tracker - Installation ===${NC}"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for Lino-ST.py
if [ ! -f "$SCRIPT_DIR/Lino-ST.py" ]; then
    echo -e "${RED}Error: 'Lino-ST.py' not found in $SCRIPT_DIR${NC}"
    echo "Please run this script from the Lino-ST source directory."
    exit 1
fi

# Detect Linux distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO_ID=$(echo "$ID" | tr '[:upper:]' '[:lower:]')
        DISTRO_LIKE=$(echo "$ID_LIKE" | tr '[:upper:]' '[:lower:]')
    else
        DISTRO_ID="unknown"
        DISTRO_LIKE=""
    fi
}

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
        echo ""
        echo "Please install Python 3 first:"
        detect_distro
        case "$DISTRO_ID $DISTRO_LIKE" in
            *debian*|*ubuntu*|*mint*|*elementary*)
                echo "  sudo apt install python3 python3-venv python3-pip"
                ;;
            *fedora*|*rhel*|*centos*)
                echo "  sudo dnf install python3 python3-pip"
                ;;
            *arch*)
                echo "  sudo pacman -S python python-pip"
                ;;
            *opensuse*|*suse*)
                echo "  sudo zypper install python3 python3-pip"
                ;;
            *)
                echo "  Install python3, python3-venv, and python3-pip for your distribution"
                ;;
        esac
        exit 1
    fi

    # Get Python version
    PY_FULL_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+')
    echo -e "  Found: $PYTHON_CMD (version $PY_FULL_VERSION)"

    # Check for venv module
    echo -e "${BLUE}Checking for venv module...${NC}"
    if ! $PYTHON_CMD -c "import venv" 2>/dev/null; then
        echo -e "${YELLOW}Warning: Python venv module not found!${NC}"
        echo ""
        echo "Installing python3-venv..."
        detect_distro
        case "$DISTRO_ID $DISTRO_LIKE" in
            *debian*|*ubuntu*|*mint*|*elementary*)
                sudo apt install -y python3-venv
                ;;
            *fedora*|*rhel*|*centos*)
                # Usually included in python3
                sudo dnf install -y python3
                ;;
            *arch*)
                # venv is included in python package
                echo "venv should be included with python package on Arch"
                ;;
            *opensuse*|*suse*)
                sudo zypper install -y python3-venv
                ;;
            *)
                echo -e "${RED}Please install python3-venv manually${NC}"
                exit 1
                ;;
        esac
    fi
    echo -e "  venv module: ${GREEN}OK${NC}"

    # Check for pip
    echo -e "${BLUE}Checking for pip...${NC}"
    if ! $PYTHON_CMD -m pip --version &>/dev/null; then
        echo -e "${YELLOW}Warning: pip not found!${NC}"
        echo ""
        echo "Installing pip..."
        detect_distro
        case "$DISTRO_ID $DISTRO_LIKE" in
            *debian*|*ubuntu*|*mint*|*elementary*)
                sudo apt install -y python3-pip
                ;;
            *fedora*|*rhel*|*centos*)
                sudo dnf install -y python3-pip
                ;;
            *arch*)
                sudo pacman -S --noconfirm python-pip
                ;;
            *opensuse*|*suse*)
                sudo zypper install -y python3-pip
                ;;
            *)
                echo -e "${RED}Please install pip manually${NC}"
                exit 1
                ;;
        esac
    fi
    PIP_VERSION=$($PYTHON_CMD -m pip --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
    echo -e "  pip version: ${GREEN}$PIP_VERSION${NC}"
}

# Install system dependencies (audio libraries)
install_system_deps() {
    detect_distro
    echo -e "${BLUE}Detected distribution: $DISTRO_ID${NC}"
    echo ""

    case "$DISTRO_ID $DISTRO_LIKE" in
        *debian*|*ubuntu*|*mint*|*elementary*)
            echo "Installing audio dependencies via apt..."
            sudo apt update
            sudo apt install -y libportaudio2 portaudio19-dev libsndfile1 \
                gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
                gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
                libxcb-cursor0
            ;;
        *fedora*|*rhel*|*centos*)
            echo "Installing audio dependencies via dnf..."
            sudo dnf install -y portaudio portaudio-devel libsndfile \
                gstreamer1-plugins-base gstreamer1-plugins-good \
                gstreamer1-plugins-bad-free gstreamer1-plugins-ugly \
                xcb-util-cursor
            ;;
        *arch*)
            echo "Installing audio dependencies via pacman..."
            sudo pacman -S --noconfirm portaudio libsndfile gstreamer \
                gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly \
                xcb-util-cursor
            ;;
        *opensuse*|*suse*)
            echo "Installing audio dependencies via zypper..."
            sudo zypper install -y portaudio-devel libsndfile1 \
                gstreamer-plugins-base gstreamer-plugins-good \
                gstreamer-plugins-bad gstreamer-plugins-ugly
            ;;
        *)
            echo -e "${YELLOW}Unknown distribution. Please install these dependencies manually:${NC}"
            echo "  - PortAudio (libportaudio2)"
            echo "  - libsndfile"
            echo "  - GStreamer plugins (base, good, bad, ugly)"
            echo "  - xcb-util-cursor (for Qt)"
            read -p "Press Enter to continue or Ctrl+C to abort..."
            ;;
    esac
}

# Main installation
echo -e "${BLUE}Step 1: Checking Python environment${NC}"
echo ""
check_python
echo ""

echo -e "${BLUE}Step 2: System dependencies${NC}"
echo ""
echo -e "${YELLOW}Do you want to install system audio dependencies? (requires sudo)${NC}"
echo "This includes PortAudio, GStreamer plugins, and other audio libraries."
read -p "[y/N]: " install_deps
if [[ "$install_deps" =~ ^[Yy]$ ]]; then
    install_system_deps
else
    echo "Skipping system dependencies. Make sure you have PortAudio and GStreamer installed."
fi
echo ""

echo -e "${BLUE}Step 3: Installing Lino-ST${NC}"
echo ""

echo "Creating installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$DESKTOP_DIR"
mkdir -p "$ICON_DIR/16x16/apps"
mkdir -p "$ICON_DIR/32x32/apps"
mkdir -p "$ICON_DIR/64x64/apps"
mkdir -p "$ICON_DIR/128x128/apps"
mkdir -p "$ICON_DIR/256x256/apps"

# Copy application files
echo "Copying application files..."
cp "$SCRIPT_DIR/Lino-ST.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/LICENSE.MD" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/README.md" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/image.png" "$INSTALL_DIR/" 2>/dev/null || true

# Copy icons if they exist
if [ -d "$SCRIPT_DIR/Icons" ]; then
    cp -r "$SCRIPT_DIR/Icons" "$INSTALL_DIR/"
    # Install icons to system icon directories
    [ -f "$SCRIPT_DIR/Icons/icon_16x16.png" ] && cp "$SCRIPT_DIR/Icons/icon_16x16.png" "$ICON_DIR/16x16/apps/$APP_NAME.png"
    [ -f "$SCRIPT_DIR/Icons/icon_32x32.png" ] && cp "$SCRIPT_DIR/Icons/icon_32x32.png" "$ICON_DIR/32x32/apps/$APP_NAME.png"
    [ -f "$SCRIPT_DIR/Icons/icon_64x64.png" ] && cp "$SCRIPT_DIR/Icons/icon_64x64.png" "$ICON_DIR/64x64/apps/$APP_NAME.png"
    [ -f "$SCRIPT_DIR/Icons/icon_128x128.png" ] && cp "$SCRIPT_DIR/Icons/icon_128x128.png" "$ICON_DIR/128x128/apps/$APP_NAME.png"
    [ -f "$SCRIPT_DIR/Icons/icon_256x256.png" ] && cp "$SCRIPT_DIR/Icons/icon_256x256.png" "$ICON_DIR/256x256/apps/$APP_NAME.png"
fi

# Create recordings directory
mkdir -p "$INSTALL_DIR/recordings"

# Create virtual environment
echo "Creating Python virtual environment..."
# Remove old venv if exists
[ -d "$INSTALL_DIR/venv" ] && rm -rf "$INSTALL_DIR/venv"
$PYTHON_CMD -m venv "$INSTALL_DIR/venv"

# Install Python dependencies
echo "Installing Python dependencies (this may take a minute)..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip --quiet
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
else
    "$INSTALL_DIR/venv/bin/pip" install PySide6 numpy sounddevice soundfile --quiet
fi
echo -e "  Python packages: ${GREEN}OK${NC}"

# Create launcher script
echo "Creating launcher script..."
cat > "$BIN_DIR/$APP_NAME" << LAUNCHER
#!/bin/bash
# Lino-ST launcher script
APP_DIR="$INSTALL_DIR"
cd "\$APP_DIR"
exec "\$APP_DIR/venv/bin/python" "\$APP_DIR/Lino-ST.py" "\$@"
LAUNCHER
chmod +x "$BIN_DIR/$APP_NAME"

# Create desktop entry
echo "Creating desktop entry..."
cat > "$DESKTOP_DIR/$APP_NAME.desktop" << DESKTOP
[Desktop Entry]
Name=$APP_DISPLAY_NAME
Comment=Sleep Tracker - Record sounds while you sleep
Exec=$BIN_DIR/$APP_NAME
Icon=$APP_NAME
Terminal=false
Type=Application
Categories=Utility;Audio;
Keywords=sleep;tracker;audio;recording;
StartupWMClass=sleepypenguin
DESKTOP

# Update icon cache
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t "$ICON_DIR" 2>/dev/null || true
fi

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

# Add ~/.local/bin to PATH if not already there
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo -e "${YELLOW}Note: $HOME/.local/bin is not in your PATH${NC}"
    echo "Add this to your ~/.bashrc or ~/.zshrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo ""
echo -e "${GREEN}=== Installation Complete! ===${NC}"
echo ""
echo "You can now run Lino-ST:"
echo "  - From terminal: $APP_NAME"
echo "  - From application menu: Search for 'Lino-ST'"
echo ""
echo "Installation directory: $INSTALL_DIR"
echo "Recordings will be saved to: $INSTALL_DIR/recordings"
echo ""
echo -e "${YELLOW}Note: You may need to log out and back in for the application"
echo -e "to appear in your application menu.${NC}"
