import importlib.util
import os

HERE = os.path.dirname(os.path.realpath(__file__))
spec = importlib.util.spec_from_file_location(
    "fwqa", os.path.join(HERE, "..", "find-why-question-answers.py"))
fwqa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fwqa)


def row(group, text, session="s1", origin="human"):
    return {"group": group, "text": text, "session": session, "origin": origin,
            "project": "p", "time": "t"}


def test_pairs_a_why_prompt_with_the_reply_after_it():
    rows = [row("assistant", "Accept the invitation."),
            row("user", "why are you saying such things?"),
            row("assistant", "The column header I wrote asked for an action.")]
    out = list(fwqa.pair(rows, fwqa.DEFAULT_PATTERN))
    assert len(out) == 1
    assert out[0]["before"] == "Accept the invitation."
    assert out[0]["after"] == "The column header I wrote asked for an action."


def test_skips_non_matching_injected_and_other_session_rows():
    rows = [row("user", "build it"),
            row("user", "why did you do that", origin="hook"),
            row("user", "wdym"),
            row("assistant", "reply in another session", session="s2")]
    out = list(fwqa.pair(rows, fwqa.DEFAULT_PATTERN))
    assert len(out) == 1 and out[0]["user"] == "wdym" and out[0]["after"] == ""


def test_skips_long_pastes():
    rows = [row("user", "why did you " + "x" * 2000)]
    assert list(fwqa.pair(rows, fwqa.DEFAULT_PATTERN)) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok   ", name)
