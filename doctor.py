# -*- coding: utf-8 -*-
"""키트 환경 진단. `kit.yaml`을 읽어 부족한 것만, 해결 방법까지 알려준다.

받은 사람이 첫 실행에서 막히는 지점이 늘 같아서(파이썬 버전·키 없음·패키지 없음·설정파일 미복사)
그 넷을 여기서 한 번에 본다. 실패를 나열만 하면 소용없으므로 각 줄에 다음 행동을 붙인다.

    python doctor.py          진단
    python doctor.py --json   기계용 출력 (n8n·에이전트가 읽는다)

이 파일은 `09-kits/_standard/doctor.py` 가 정본이고 각 키트에 복사본으로 들어간다.
키트는 배포 후 혼자 서야 하므로 공용 모듈로 빼지 않는다.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OK, WARN, FAIL = "OK", "WARN", "FAIL"


def _load_yaml(path):
    try:
        import yaml
    except ImportError:
        print("[FAIL] pyyaml 미설치 — 진단기가 kit.yaml 을 못 읽는다.\n"
              "        설치: pip install pyyaml", file=sys.stderr)
        sys.exit(2)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dotenv():
    """.env / .env.local 값을 OS 환경변수보다 우선해서 읽는다(키트는 로컬 파일이 정본)."""
    vals = {}
    for name in (".env", ".env.local"):
        f = HERE / name
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip("'\"")
    return vals


def _placeholder(v):
    """.env.example 을 그대로 복사만 하고 값을 안 채운 경우를 잡는다."""
    if not v:
        return True
    low = v.lower()
    return (any(t in v for t in ("여기", "본인", "your", "xxxx", "...", "..."))
            or low in ("sk-", "changeme"))


def check():
    spec = _load_yaml(HERE / "kit.yaml")
    env = dict(os.environ)
    env.update(_dotenv())
    out = []

    want = str(spec.get("python") or "").replace(">=", "").strip()
    cur = f"{sys.version_info.major}.{sys.version_info.minor}"
    if want:
        ok = tuple(int(x) for x in cur.split(".")) >= tuple(int(x) for x in want.split(".")[:2])
        out.append((OK if ok else FAIL, f"Python {cur}",
                    "" if ok else f"{want} 이상 필요. https://www.python.org/downloads/"))
    else:
        out.append((OK, f"Python {cur}", ""))

    for e in spec.get("env") or []:
        key = e.get("key")
        required = e.get("required", True)
        val = env.get(key)
        if val and not _placeholder(val):
            out.append((OK, key, ""))
        else:
            how = f"발급: {e.get('where','')}  저장: {e.get('store','.env')}"
            out.append((FAIL if required else WARN,
                        f"{key} {'없음' if not val else '예시값 그대로'}", how))

    for f in spec.get("files") or []:
        p = HERE / f.get("path", "")
        if p.exists():
            out.append((OK, f["path"], ""))
        else:
            src = f.get("from")
            out.append((FAIL if f.get("required", True) else WARN, f"{f['path']} 없음",
                        f"복사: cp {src} {f['path']}" if src else f.get("how", "")))

    for pkg in spec.get("packages") or []:
        mod = pkg.split("==")[0].split(">=")[0].replace("-", "_")
        if importlib.util.find_spec(mod) is None:
            out.append((FAIL, f"{pkg} 미설치",
                        f"설치: {(spec.get('commands') or {}).get('setup', 'pip install -r requirements.txt')}"))
        else:
            out.append((OK, pkg, ""))

    return spec, out


def main():
    spec, out = check()
    if "--json" in sys.argv:
        print(json.dumps({"kit": spec.get("name"),
                          "checks": [{"level": l, "what": w, "how": h} for l, w, h in out],
                          "ok": not any(l == FAIL for l, _, _ in out)}, ensure_ascii=False))
        return 0 if not any(l == FAIL for l, _, _ in out) else 1

    print(f"── {spec.get('name')} 진단 ──")
    for level, what, how in out:
        print(f"[{level:4}] {what}")
        if how:
            print(f"        {how}")
    bad = [w for l, w, _ in out if l == FAIL]
    cmds = spec.get("commands") or {}
    if bad:
        print(f"\n{len(bad)}개 해결 후 다시 `python doctor.py`.")
        return 1
    print(f"\n전부 통과. 모의 실행: {cmds.get('dry_run') or cmds.get('start', '(없음)')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
