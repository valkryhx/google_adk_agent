from ultraplan.trigger import UltraplanTrigger


def test_has_keyword_detects_plain_sentence():
    trigger = UltraplanTrigger()
    assert trigger.has_keyword("please ultraplan this task") is True


def test_has_keyword_ignores_file_like_context():
    trigger = UltraplanTrigger()
    assert trigger.has_keyword("open src/ultraplan/foo.py") is False


def test_replace_keyword_rewrites_first_trigger():
    trigger = UltraplanTrigger()
    assert trigger.replace_keyword("please ultraplan this task") == "please plan this task"
