#!/usr/bin/env bash
# 바탕화면에 DesktopPet.app 빌드. 더블클릭으로 펫 실행.
# 강아지 사진을 .icns 아이콘으로 변환해서 사용.
set -e
cd "$(dirname "$0")"

PROJECT="$PWD"
APP="$HOME/Desktop/DesktopPet.app"
ICONSET="/tmp/DesktopPet.iconset"
ICON_SQUARE="/tmp/desktop_pet_icon_1024.png"
ICNS="/tmp/desktop_pet_icon.icns"

# 1. dog.png 을 정사각형으로 (투명 배경 패딩) → 1024x1024 PNG
./venv/bin/python - <<PY
from PIL import Image
src = Image.open("$PROJECT/assets/dog.png").convert("RGBA")
size = max(src.size)
sq = Image.new("RGBA", (size, size), (0, 0, 0, 0))
sq.paste(src, ((size - src.width) // 2, (size - src.height) // 2), src)
sq = sq.resize((1024, 1024), Image.LANCZOS)
sq.save("$ICON_SQUARE")
PY

# 2. iconset (모든 표준 사이즈)
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
sips -z 16 16     "$ICON_SQUARE" --out "$ICONSET/icon_16x16.png"     >/dev/null
sips -z 32 32     "$ICON_SQUARE" --out "$ICONSET/icon_16x16@2x.png"  >/dev/null
sips -z 32 32     "$ICON_SQUARE" --out "$ICONSET/icon_32x32.png"     >/dev/null
sips -z 64 64     "$ICON_SQUARE" --out "$ICONSET/icon_32x32@2x.png"  >/dev/null
sips -z 128 128   "$ICON_SQUARE" --out "$ICONSET/icon_128x128.png"   >/dev/null
sips -z 256 256   "$ICON_SQUARE" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256 256   "$ICON_SQUARE" --out "$ICONSET/icon_256x256.png"   >/dev/null
sips -z 512 512   "$ICON_SQUARE" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512 512   "$ICON_SQUARE" --out "$ICONSET/icon_512x512.png"   >/dev/null
sips -z 1024 1024 "$ICON_SQUARE" --out "$ICONSET/icon_512x512@2x.png" >/dev/null

# 3. .icns
iconutil -c icns "$ICONSET" -o "$ICNS"

# 4. .app bundle
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
mkdir -p "$APP/Contents/Resources"
cp "$ICNS" "$APP/Contents/Resources/icon.icns"

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Desktop Pet</string>
    <key>CFBundleDisplayName</key>
    <string>Desktop Pet</string>
    <key>CFBundleIdentifier</key>
    <string>com.tyoon.desktoppet</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

cat > "$APP/Contents/MacOS/launcher" <<EOF
#!/bin/bash
# Homebrew bin 을 PATH 에 추가해서 macmon 찾을 수 있게 함
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
LOG=/tmp/desktop_pet.log

# 이미 떠 있는 펫이 있으면 종료 (중복 방지)
pkill -f "$PROJECT/pet.py" 2>/dev/null
sleep 0.3

exec "$PROJECT/venv/bin/python" "$PROJECT/pet.py" >>"\$LOG" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/launcher"

# Finder 가 새 아이콘을 즉시 갱신하도록 mtime 업데이트
touch "$APP"

echo "Built: $APP"
