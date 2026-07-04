# TASK_BRIEF : slack-readback-bot 키트

> 재개 시 여기부터. 현황·결정·남은 일 전부 이 문서에.
> 규칙: em dash 미사용, 영문+한글 혼용.

---

## 이게 뭔가 (What)

슬랙 채널에 "다시 볼 거"(링크·메모)를 던져두면, 봇이 아직 처리 안 한 것만 모아서 정해진 시간에 채널로 다시 올려주는 **무상태(zero-state) 리마인드 봇**. DB 없이 채널 자체를 읽어 상태를 판단한다.

- 처리 표시: ✅ 또는 답글 `확인`/`done` = 해결(리마인드 제외)
- 보류 표시: 💤 또는 답글 `보류`/`snooze` = 주간 digest에만
- 무표시 = 미확인(매일 digest에 뜸)
- 자기 과거 글을 확인해 중복 발송 방지

## 왜 키트로 (Why kit)

이 readback 기능은 원래 셀로직 콘텐츠 봇(Railway 상주, `azzselloo-sudo/selllogic-content-bot` 내 `bot.py`)에 내장돼 실운영 중이다. 그 기능만 **따로 떼서 남도 쓸 수 있게 자립형 공개 배포본**으로 뽑은 것이 이 레포. 즉 셀로직 봇에서 검증된 로직의 범용 배포판.

## 배포 상태 (Status, 2026-07-04)

- 레포: `github.com/azzselloo-sudo/slack-readback-bot` (**public**)
- 09-kits 편입: `09-kits/04-slack-readback-bot/` (레지스트리 04번 등록)
- 구성: README(이중언어)·LICENSE(MIT)·.env.example·config.example.json·readback.py·test_readback.py·.github/workflows/reminder.yml 전부 자립
- 시크릿: 없음(placeholder만). .gitignore가 .env·config.json 차단
- 내 개인 운영 인스턴스: **GitHub Actions 워크플로우 비활성화함**. 이유는 아래.

## 중요 판단 : 내 계정에선 안 돌린다

내(azzselloo) 워크스페이스에선 이 readback 리마인드를 **이미 셀로직 봇이 하고 있어서** 이 레포의 GitHub Actions는 중복이다. 게다가 저장소 변수 `READBACK_CONFIG`를 안 넣어둬서 실행마다 `JSONDecodeError`로 실패, 실패 메일만 계속 왔다(6/28 생성 이후 12회 전부 실패, 성공 0회). 그래서 **워크플로우를 disable** 처리해 실패 메일을 끊었다. 템플릿의 cron은 남겨둠(수신자는 그대로 써야 하므로).

> 다시 켜려면: `gh workflow enable "readback reminder" --repo azzselloo-sudo/slack-readback-bot` 후 변수·시크릿 2개 등록.

## 남에게 줄 때 (Handoff, BYO)

받는 사람 본인 것으로 딱 2개만 있으면 된다:
1. **슬랙 봇 토큰** (`xoxb-...`): api.slack.com/apps 에서 앱 생성, 스코프 `channels:history`·`channels:read`·`chat:write`·`reactions:read`(비공개 채널이면 `groups:history` 추가), 설치 후 복사. 채널에 `/invite @봇`.
2. **채널 ID**: config.json 의 `channels` 에 넣기.

구동 3택:
- 로컬 1회: `python readback.py daily --dry` (미리보기) / `--dry` 빼면 발송
- 상주: `python readback.py loop`
- 무료 자동: GitHub Actions (레포 Secret `SLACK_BOT_TOKEN` + Variable `READBACK_CONFIG`=config.json 전문)

## 남은 일 (Open)

- 없음(v1 배포 완료). 남에게 핸드오프 시 위 BYO 2개만 안내하면 됨.
- 선택: 셀로직 봇 쪽 readback 로직이 개선되면 이 배포판에도 반영(현재는 동등).
