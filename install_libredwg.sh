#!/bin/bash
#
# FireAI V5.1.2 - LibreDWG Installer
# ======================================
# Installs LibreDWG tools for DWG → DXF conversion
#

set -e

echo "=========================================="
echo "FireAI V5.1.2 - LibreDWG Installer"
echo "=========================================="

# Detect OS
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif [ -f /etc/centos-release ]; then
        echo "centos"
    elif [ -f /etc/redhat-release ]; then
        echo "rhel"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
echo "Detected OS: $OS"

install_ubuntu() {
    echo "Installing for Ubuntu/Debian..."
    sudo apt update
    sudo apt install -y libredwg-tools
}

install_fedora() {
    echo "Installing for Fedora..."
    sudo dnf install -y libredwg-tools
}

install_centos() {
    echo "Installing for CentOS/RHEL..."
    sudo dnf install -y epel-release
    sudo dnf install -y libredwg-tools
}

install_macos() {
    echo "Installing for macOS..."
    if command -v brew &> /dev/null; then
        brew install libredwg
    else
        echo "Error: Homebrew not found. Install Homebrew first:"
        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)\""
        exit 1
    fi
}

# Install based on OS
case "$OS" in
    ubuntu|debian)
        install_ubuntu
        ;;
    fedora)
        install_fedora
        ;;
    centos|rhel|rocky|alma)
        install_centos
        ;;
    darwin)
        install_macos
        ;;
    *)
        echo "Error: Unsupported OS: $OS"
        echo "Trying Ubuntu method..."
        install_ubuntu || exit 1
        ;;
esac

# Verify installation
echo ""
echo "=========================================="
echo "Verifying installation..."
echo "=========================================="

if command -v dxf-out &> /dev/null; then
    echo "✅ dxf-out installed:"
    dxf-out --version
    echo ""
    echo "=========================================="
    echo "✅ LibreDWG installed successfully!"
    echo "=========================================="
    echo ""
    echo "You can now use DWG files with FireAI:"
    echo "  from parsers.dwg_parser import DWGParser"
    echo "  parser = DWGParser()"
    echo "  result = parser.parse('building.dwg')"
else
    echo "❌ dxf-out not found after installation"
    exit 1
fi