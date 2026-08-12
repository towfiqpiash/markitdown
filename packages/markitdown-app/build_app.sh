#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="$WORKSPACE_ROOT/dist"
APP_BUNDLE="$DIST_DIR/MarkItDown.app"
CONTENTS_DIR="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

ICON_SRC="/Users/towfiq/.gemini/antigravity-ide/brain/345e9420-a5b7-4563-8e65-bab77d7fa2d9/media__1786455404679.png"

echo "Building MarkItDown macOS Desktop Application..."

# 1. Clean previous build
rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS_DIR"
mkdir -p "$RESOURCES_DIR"

# 2. Generate AppIcon.icns
if [ -f "$ICON_SRC" ]; then
    echo "Creating AppIcon.icns from user provided icon..."
    ICONSET_DIR="$(mktemp -d)/AppIcon.iconset"
    mkdir -p "$ICONSET_DIR"

    TMP_PNG="$(mktemp).png"
    # Convert source image to PNG format
    sips -s format png "$ICON_SRC" --out "$TMP_PNG" >/dev/null 2>&1
    
    # Center crop to 680x680 to remove outer white letterboxing
    sips -c 680 680 "$TMP_PNG" >/dev/null 2>&1
    
    # Resize to 1024x1024 master icon
    sips -z 1024 1024 "$TMP_PNG" >/dev/null 2>&1

    # Generate all required macOS icon resolutions
    sips -z 16 16     "$TMP_PNG" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1
    sips -z 32 32     "$TMP_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1
    sips -z 32 32     "$TMP_PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1
    sips -z 64 64     "$TMP_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1
    sips -z 128 128   "$TMP_PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1
    sips -z 256 256   "$TMP_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1
    sips -z 256 256   "$TMP_PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1
    sips -z 512 512   "$TMP_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1
    sips -z 512 512   "$TMP_PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1
    sips -z 1024 1024 "$TMP_PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null 2>&1

    iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/AppIcon.icns"
    rm -rf "$(dirname "$ICONSET_DIR")" "$TMP_PNG"
fi

# 3. Copy Info.plist
cp "$SCRIPT_DIR/Info.plist" "$CONTENTS_DIR/Info.plist"

# 4. Compile Swift Binary
echo "Compiling Swift executable..."
swiftc -parse-as-library "$SCRIPT_DIR/main.swift" \
    -o "$MACOS_DIR/MarkItDown" \
    -framework AppKit \
    -framework WebKit \
    -framework Network

chmod +x "$MACOS_DIR/MarkItDown"

# 5. Install to /Applications
echo "Installing to /Applications/MarkItDown.app..."
rm -rf /Applications/MarkItDown.app
cp -R "$APP_BUNDLE" /Applications/MarkItDown.app

# 6. Force macOS LaunchServices & Dock to reload icon cache
echo "Updating macOS LaunchServices icon cache..."
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f -r /Applications/MarkItDown.app
touch /Applications/MarkItDown.app
killall Dock Finder 2>/dev/null || true

echo "Successfully built & installed MarkItDown.app with user icon!"
