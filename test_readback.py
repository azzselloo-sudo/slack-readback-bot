"""
Unit tests for the pure logic (no Slack calls).
Run: python test_readback.py
"""
import readback as rb

CFG = rb.CFG


def test_resolve_reaction_wins():
    s = rb._status_from_reactions_and_replies(["white_check_mark"], [], CFG)
    assert s == "resolved", s


def test_snooze_reaction():
    s = rb._status_from_reactions_and_replies(["zzz"], [], CFG)
    assert s == "snoozed", s


def test_open_when_nothing():
    s = rb._status_from_reactions_and_replies([], [], CFG)
    assert s == "open", s


def test_resolve_keyword_in_reply():
    s = rb._status_from_reactions_and_replies([], ["확인했어요"], CFG)
    assert s == "resolved", s


def test_snooze_keyword_in_reply():
    s = rb._status_from_reactions_and_replies([], ["later 보자"], CFG)
    assert s == "snoozed", s


def test_resolve_beats_snooze():
    # snooze reaction + resolve reply -> resolved
    s = rb._status_from_reactions_and_replies(["zzz"], ["done"], CFG)
    assert s == "resolved", s


def test_chunk_keeps_all_lines():
    text = "\n".join(f"line {i}" for i in range(500))
    chunks = rb._chunk_text(text, limit=200)
    assert len(chunks) > 1
    assert "\n".join(chunks).count("line ") == 500
    assert all(len(c) <= 200 for c in chunks)


def test_chunk_short_text_single():
    chunks = rb._chunk_text("hello\nworld", limit=3800)
    assert chunks == ["hello\nworld"], chunks


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
