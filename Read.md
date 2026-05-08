# Momo — macOS 데스크탑 펫

화면을 어슬렁거리며 시스템 하드웨어 사용량을 알려주는 macOS 데스크탑 펫.
PyQt6 + macmon 기반. 모든 처리는 로컬 (외부 API 없음).

기본은 **세 마리 무리 모드** (요키 / 진돗개 / 비숑이 한 위젯 안에서 같이 뛰어다님).
한 마리만 쓰는 단일 모드도 지원.

## 기능

- 화면을 자유롭게 돌아다님 (드래그로 직접 옮길 수도 있음)
- 한 위젯 안 3마리가 각자 다른 위상으로 통통 튀어 갤럽 모션
- 시스템 부하에 따라 상태 변화: **평소** (어슬렁) / **흥분** (CPU ≥ 70%, 빠르게) / **잠** (CPU 낮은 상태 90초 지속)
- CPU 온도 ≥ 80°C 면 헥헥거림 (호흡·흔들림 가속)
- 클릭으로 4가지 정보 화면 순환:
  1. 시스템 전체 — CPU, 메모리, **온도**, **전력**, 디스크, 네트워크
  2. CPU 많이 먹는 프로세스 TOP 3
  3. 메모리 많이 먹는 프로세스 TOP 3
  4. **코어별 점유율** (Apple Silicon P-core / E-core 자동 분리)

## 요구사항

- macOS Apple Silicon 권장 (Intel 도 동작하나 온도/전력은 표시 안 됨)
- Python 3.8+
- Homebrew (macmon 설치용, 없어도 펫은 동작)

## 설치

```bash
git clone https://github.com/TY-tlog/momo.git
cd momo
./setup.sh
```

`setup.sh` 가 자동으로:

1. Python venv 생성 → 의존성 설치 (PyQt6, psutil, rembg, pyobjc, Pillow)
2. `brew install macmon` (Apple Silicon 온도/전력 측정)
3. `assets/` 의 스프라이트 확인 (없으면 어떻게 만들지 안내)
4. 바탕화면에 `DesktopPet.app` 빌드

이 저장소에는 기본 무리(요키/진돗개/비숑) 스프라이트가 이미 들어 있어서
clone 직후 바로 실행 가능합니다.

## 실행

**바탕화면의 `DesktopPet.app` 더블클릭.** 끝.

> 첫 실행 시 macOS Gatekeeper 가 "확인할 수 없는 개발자" 경고를 띄울 수 있습니다.
> 그러면 앱을 **우클릭 → "열기"** 한 번 → 대화상자에서 다시 "열기".
> 다음부터는 그냥 더블클릭으로 실행됩니다.

터미널에서 직접 실행도 가능:

```bash
./run.sh           # 포그라운드 (터미널 닫으면 펫도 종료)
./run.sh detach    # 백그라운드 (터미널 닫아도 살아있음)
```

## 조작

| 입력 | 동작 |
|------|------|
| 펫 클릭 | 통계 말풍선 (다시 클릭하면 다음 모드로 순환) |
| 펫 드래그 | 원하는 위치로 이동 |
| 펫 우클릭 | 메뉴 (통계 / 일시정지 / 우하단 호출 / 종료) |
| 메뉴바 트레이 아이콘 | 동일 메뉴 |

종료: 메뉴 "종료" 또는 터미널에서 `pkill -f pet.py`.

## 다른 펫 사진으로 바꾸기

### A) 무리 모드 — 한 사진에 펫 3마리

`prep_pack_sprites.py` 가 한 장의 사진에서 좌→우 순서로 3마리를
잘라서 `dog_yorkie.png` / `dog_jindo.png` / `dog_bichon.png` 로 저장합니다.
파일 이름은 고정이지만 어떤 견종이든 상관없습니다 — 좌측이 yorkie 슬롯,
가운데가 jindo (leader/트레이 아이콘), 우측이 bichon 슬롯이라고 생각하면 됩니다.

```bash
./venv/bin/python prep_pack_sprites.py /path/to/photo.png
./make_app.sh
```

자르는 영역은 비율 기준이라 사진 해상도 무관. 강아지가 너무 한쪽에
치우쳐 있거나 겹치면 `prep_pack_sprites.py` 안의 `CROPS` 비율을 조정.

### B) 단일 모드 — 펫 한 마리

`pet.py` 의 `PACK_LAYOUT` 을 한 항목만 남기거나, 또는 `dog.png` 단독을
사용하도록 단순화하고 싶다면:

```bash
./venv/bin/python prep_sprite.py /path/to/photo.png
# pet.py 의 PACK_LAYOUT 을 한 줄로 줄이거나, 코드 직접 수정
./make_app.sh
```

`rembg` 가 배경을 자동 제거합니다. 옆모습이면 갤럽 모션이 자연스럽지만
정면 사진도 OK.

## 다른 컴퓨터에서 셋업

같은 GitHub 계정의 다른 Mac 에서:

```bash
git clone https://github.com/TY-tlog/momo.git
cd momo
./setup.sh
```

기본 스프라이트가 함께 들어 있어 추가 설정 없이 바로 동작합니다.

업데이트 받기:

```bash
git pull && ./setup.sh
```

## 파일 구조

```
pet.py                  메인 앱 (PyQt6 + 상태 머신 + 무리 합성 렌더)
monitor.py              하드웨어 샘플러 (psutil + macmon 래퍼 + 코어 레이아웃 감지)
prep_pack_sprites.py    한 사진에서 3마리(yorkie/jindo/bichon) 분리 (rembg)
prep_sprite.py          단일 모드용: 한 사진 → dog.png (rembg)
make_app.sh             바탕화면에 DesktopPet.app 빌드
setup.sh                초기 셋업 (한 번만 실행)
run.sh                  터미널에서 직접 실행
requirements.txt        Python 의존성 목록
assets/dog_yorkie.png   왼쪽 펫 스프라이트
assets/dog_jindo.png    가운데 leader (트레이 아이콘 소스)
assets/dog_bichon.png   오른쪽 펫 스프라이트
assets/dog.png          (옵션) 단일 모드 폴백
```

## 알려진 한계

- 다리 자체의 굽혔다 펴는 애니메이션은 없습니다 (정지 사진 1장에서 만든 sprite). 갤럽 점프와 호흡 squash 로 흉내냅니다.
- Apple Silicon 외 환경에서는 macmon 이 동작하지 않아 온도/전력만 빠지고, 나머지는 그대로 동작합니다.
