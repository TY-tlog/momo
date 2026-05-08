#!/usr/bin/env bash
# 새 macOS Apple Silicon 컴퓨터에서 한 번 실행하면 끝.
#   ./setup.sh
#
# 하는 일:
#   1) Python venv 생성
#   2) pip 의존성 설치 (PyQt6, psutil, rembg, pyobjc, ...)
#   3) macmon 설치 (Homebrew 필요, 온도/전력 측정용)
#   4) assets/dog.png 가 없으면 안내 메시지 출력
#   5) 바탕화면에 DesktopPet.app 빌드
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
    echo "Python 3 가 필요합니다."
    echo "  Homebrew: brew install python3"
    echo "  또는 https://python.org 에서 다운로드"
    exit 1
fi

if [ ! -d venv ]; then
    echo "[1/5] venv 생성 중..."
    python3 -m venv venv
else
    echo "[1/5] venv 이미 있음, 스킵"
fi

echo "[2/5] Python 의존성 설치 중..."
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

if ! command -v macmon >/dev/null; then
    if command -v brew >/dev/null; then
        echo "[3/5] macmon 설치 중 (Apple Silicon 온도/전력 측정)..."
        brew install macmon
    else
        echo "[3/5] 경고: Homebrew 가 없어서 macmon 설치 안 함."
        echo "      온도/전력 표시 없이도 펫은 동작합니다."
        echo "      나중에 추가하려면: https://brew.sh 에서 brew 설치 후 'brew install macmon'"
    fi
else
    echo "[3/5] macmon 이미 설치됨, 스킵"
fi

PACK_OK=true
for f in dog_yorkie.png dog_jindo.png dog_bichon.png; do
    [ -f "assets/$f" ] || PACK_OK=false
done
if [ -f assets/dog.png ] || [ "$PACK_OK" = true ]; then
    echo "[4/5] 펫 스프라이트 이미 있음, 스킵"
else
    echo
    echo "[4/5] 펫 스프라이트가 없습니다."
    echo
    echo "옵션 A) 한 마리 (한 사진에 펫 한 마리):"
    echo "  ./venv/bin/python prep_sprite.py /path/to/photo.png"
    echo
    echo "옵션 B) 세 마리 무리 (한 사진에 펫 3마리 나란히):"
    echo "  ./venv/bin/python prep_pack_sprites.py /path/to/photo.png"
    echo "  (좌→우 순서로 yorkie / jindo / bichon 으로 분리됩니다.)"
    echo
    echo "그 후 다시 ./setup.sh 실행하시면 .app 까지 빌드됩니다."
    exit 0
fi

echo "[5/5] 바탕화면에 DesktopPet.app 빌드 중..."
./make_app.sh

echo
echo "설정 완료."
echo "바탕화면의 DesktopPet.app 을 더블클릭하면 펫이 실행됩니다."
