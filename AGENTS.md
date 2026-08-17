# AGENTS.md — slack-readback-bot

Codex·클로드코드가 이 키트를 설치할 때 따르는 규칙. 사람이 읽어도 된다.

> 사용자가 "이 저장소를 내 운영체제에 맞게 설치해줘" 라고만 해도 아래 순서대로 진행한다.

## 이 키트가 하는 일

채널에 던져둔 '다시 볼 거'를 미처리 건만 모아 다시 올려주는 무상태 슬랙 봇

## 설치 순서 (이 순서를 지킨다)

1. 지원 OS 확인 : windows / macos / linux
2. 파이썬 >=3.9 확인
3. 설치 : `uv sync  (uv 없으면: pip install -r requirements.txt)`
4. 설정 파일 복사 : `.env` ← `.env.example`, `config.json` ← `config.example.json`
5. 키 입력 : 아래 표의 발급 페이지를 **사용자에게 열어주고**, 값은 사용자가 직접 `.env` 에 넣는다
6. 진단 : `python doctor.py` — FAIL 이 남아 있으면 여기서 멈춘다
7. 모의 실행 : `python readback.py --dry-run` — 실제 발송·게시가 없었는지 확인하고 보고한다
8. 실행 : `python readback.py`

## 절대 하지 않는 것

- API 키를 채팅·로그·커밋에 남기지 않는다. 사용자 PC의 `.env` 에만 둔다.
- 진단(6)이 FAIL 인 상태로 7·8 로 넘어가지 않는다.
- 아래 "사람이 결정할 것"을 대신 결정하지 않는다.

## 필요한 값

| 키 | 필수 | 어디서 받나 |
|---|---|---|
| `SLACK_BOT_TOKEN` | 필수 | https://api.slack.com/apps → OAuth & Permissions → Bot User OAuth Token |

## 사람이 결정할 것

- (없음)

## 제거

`슬랙 앱에서 봇 제거 후 폴더 삭제`

> 상태 파일이 없다. 채널을 읽어 판단하므로 제거 시 남는 게 없다.

