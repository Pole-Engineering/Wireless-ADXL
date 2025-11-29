#!/bin/bash

# WADXL Klipper Installer Script
# This script installs WADXL to Klipper

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Delay function
delay() {
    sleep 0.05
}

# Sudo check
check_sudo() {
    if [ "$EUID" -eq 0 ]; then
        clear
        echo -e "${RED}╔═══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║                        WARNING                           ║${NC}"
        echo -e "${RED}╚═══════════════════════════════════════════════════════════╝${NC}"
        echo
        echo -e "${RED}[✗] This script should NOT be run with sudo/root privileges!${NC}"
        echo
        echo -e "${YELLOW}Please run as a normal user:${NC}"
        echo
        echo -e "${WHITE}  ./install_wadxl.sh${NC}"
        echo
        echo -e "${RED}Script terminating...${NC}"
        delay
        delay
        exit 1
    fi
}

# ASCII Art
display_banner() {
    clear
    echo -e "${CYAN}"
    cat << "EOF"
 ██╗    ██╗ █████╗ ██████╗ ██╗  ██╗██╗
 ██║    ██║██╔══██╗██╔══██╗╚██╗██╔╝██║
 ██║ █╗ ██║███████║██║  ██║ ╚███╔╝ ██║
 ██║███╗██║██╔══██║██║  ██║ ██╔██╗ ██║
 ╚███╔███╔╝██║  ██║██████╔╝██╔╝ ██╗███████╗
  ╚══╝╚══╝ ╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚══════╝

  Klipper Integration Installer v1.0
EOF
    echo -e "${NC}"
    delay

    echo -e "${PURPLE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}  WADXL - Wireless ADXL345 Implementation${NC}"
    delay
    echo -e "${WHITE}  Wireless accelerometer implementation for klipper${NC}"
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════${NC}"
    echo
    delay
}

# Variables
WEBSERVER_URL="https://raw.githubusercontent.com/Pole-Engineering/Wireless-ADXL/main/software/standalone.py"  
KLIPPER_DIR="$HOME/klipper"
KLIPPY_EXTRAS_DIR="$KLIPPER_DIR/klippy/extras"
WADXL_FILE="wadxl.py"
TEMP_FILE="/tmp/$WADXL_FILE"

# Functions
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
    delay
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
    delay
}

print_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
    delay
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
    delay
}

print_step() {
    echo -e "\n${CYAN}►${NC} ${WHITE}$1${NC}"
    delay
}

# Main function
main() {
    # Check sudo first
    check_sudo

    # Display banner
    display_banner

    print_step "Starting WADXL installation..."

    # Check Klipper directory
    print_status "Checking Klipper directory..."
    if [ ! -d "$KLIPPER_DIR" ]; then
        print_error "Klipper directory not found: $KLIPPER_DIR"
        print_status "Please ensure Klipper is properly installed."
        exit 1
    fi
    print_success "Klipper directory found"

    # Check klippy extras directory
    print_status "Checking klippy extras directory..."
    if [ ! -d "$KLIPPY_EXTRAS_DIR" ]; then
        print_error "Klippy extras directory not found: $KLIPPY_EXTRAS_DIR"
        print_status "Creating klippy extras directory..."
        mkdir -p "$KLIPPY_EXTRAS_DIR"
        if [ $? -eq 0 ]; then
            print_success "Klippy extras directory created"
        else
            print_error "Failed to create klippy extras directory"
            exit 1
        fi
    else
        print_success "Klippy extras directory found"
    fi

    # Download WADXL file
    print_step "Downloading WADXL module..."
    print_status "Downloading from: $WEBSERVER_URL"

    if command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "$TEMP_FILE" "$WEBSERVER_URL"
    elif command -v curl >/dev/null 2>&1; then
        curl -L -o "$TEMP_FILE" "$WEBSERVER_URL" --progress-bar
    else
        print_error "Neither wget nor curl found. Please install one of them."
        exit 1
    fi

    if [ $? -ne 0 ]; then
        print_error "Failed to download WADXL module"
        exit 1
    fi

    if [ ! -f "$TEMP_FILE" ]; then
        print_error "Downloaded file not found"
        exit 1
    fi
    print_success "WADXL module downloaded successfully"

    # Verify file is not empty
    if [ ! -s "$TEMP_FILE" ]; then
        print_error "Downloaded file is empty"
        rm -f "$TEMP_FILE"
        exit 1
    fi

    # Move file to klipper extras
    print_step "Installing WADXL module..."
    print_status "Moving file to: $KLIPPY_EXTRAS_DIR/$WADXL_FILE"

    mv "$TEMP_FILE" "$KLIPPY_EXTRAS_DIR/$WADXL_FILE"
    if [ $? -ne 0 ]; then
        print_error "Failed to move WADXL module to extras directory"
        exit 1
    fi

    # Set proper permissions
    chmod 644 "$KLIPPY_EXTRAS_DIR/$WADXL_FILE"
    print_success "WADXL module installed successfully"

    # Final verification
    print_step "Verifying installation..."
    if [ -f "$KLIPPY_EXTRAS_DIR/$WADXL_FILE" ]; then
        file_size=$(stat -c%s "$KLIPPY_EXTRAS_DIR/$WADXL_FILE" 2>/dev/null || stat -f%z "$KLIPPY_EXTRAS_DIR/$WADXL_FILE" 2>/dev/null)
        print_success "Installation verified (File size: $file_size bytes)"
    else
        print_error "Installation verification failed"
        exit 1
    fi

    # Installation complete
    echo
    delay
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                  INSTALLATION COMPLETE                   ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo
    delay
    print_success "WADXL wireless accelerometer module has been successfully installed!"
    print_status "Location: $KLIPPY_EXTRAS_DIR/$WADXL_FILE"
    echo
    delay
    print_warning "Next steps:"
    echo "  1. Add WADXL configuration to your printer.cfg file"
    delay
    echo "  2. Restart Klipper service"
    delay
    echo "  3. Configure your wireless ADXL345 accelerometer"
    echo
    delay
    print_status "For configuration help, please refer to the WADXL documentation."
    echo
    delay
}

main