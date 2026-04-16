from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.adk_agent.stream_dedup import (
    advance_stream_accumulator,
    compute_same_type_delta,
    compute_stream_delta,
    dedupe_textual_event_chunks,
    strip_leaked_think_from_text,
)


def test_cross_type_boundary_trims_text_prefix_repeated_from_thought():
    thought_acc = "我需要先分析问题。"
    text_acc = ""
    raw_text = "我需要先分析问题。最终答案是 X。"

    delta = compute_stream_delta(
        base_acc=text_acc,
        raw_fragment=raw_text,
        previous_other_type_acc=thought_acc,
        is_first_fragment_of_type=True,
    )

    assert delta == "最终答案是 X。"


def test_cross_type_trim_keeps_raw_accumulator_aligned_for_next_cumulative_text():
    thought_acc = "我需要先分析问题。"
    text_raw_acc = ""
    first_raw_text = "我需要先分析问题。最终答案是 X。"

    first_raw_delta = compute_same_type_delta(text_raw_acc, first_raw_text)
    first_display_delta = compute_stream_delta(
        base_acc=text_raw_acc,
        raw_fragment=first_raw_text,
        previous_other_type_acc=thought_acc,
        is_first_fragment_of_type=True,
    )
    text_raw_acc = advance_stream_accumulator(
        base_acc=text_raw_acc,
        raw_fragment=first_raw_text,
        raw_delta=first_raw_delta,
    )

    second_display_delta = compute_stream_delta(
        base_acc=text_raw_acc,
        raw_fragment=f"{first_raw_text}第二句。",
        previous_other_type_acc=thought_acc,
        is_first_fragment_of_type=False,
    )

    assert first_display_delta == "最终答案是 X。"
    assert second_display_delta == "第二句。"


def test_cross_type_boundary_does_not_trim_unrelated_first_text():
    delta = compute_stream_delta(
        base_acc="",
        raw_fragment="结论 B。",
        previous_other_type_acc="先想 A。",
        is_first_fragment_of_type=True,
    )

    assert delta == "结论 B。"


def test_strip_leaked_think_from_text_returns_only_visible_answer():
    cleaned, had_leak = strip_leaked_think_from_text(
        "执行超时了，让我尝试使用更简单的方法：\n在Windows环境下，我可以使用 PowerShell 的 Get-Date 命令：\n</think>\n让我换用 Windows PowerShell 命令来获取时间："
    )

    assert had_leak is True
    assert cleaned == "让我换用 Windows PowerShell 命令来获取时间："


def test_strip_leaked_think_from_text_keeps_normal_text_unchanged():
    cleaned, had_leak = strip_leaked_think_from_text("当前时间：2026-04-16 19:17:38 星期四")

    assert had_leak is False
    assert cleaned == "当前时间：2026-04-16 19:17:38 星期四"


def test_dedupe_textual_event_chunks_suppresses_replayed_thought_before_tool_call():
    chunks = [
        {"type": "thought", "content": "用户"},
        {"type": "thought", "content": "让我用bash思考后调用工具告诉他时间。"},
        {"type": "thought", "content": "根据我的系统环境，当前是Windows 11"},
        {"type": "text", "content": "我将使用bash工具获取当前系统时间。"},
        {"type": "tool_call", "content": "bash({'command': 'echo %time%'})"},
    ]
    state = {"thought": "", "text": ""}

    first_pass = dedupe_textual_event_chunks(chunks, state)
    second_pass = dedupe_textual_event_chunks(chunks, state)

    assert first_pass == [
        {
            "type": "thought",
            "content": "用户让我用bash思考后调用工具告诉他时间。根据我的系统环境，当前是Windows 11",
        },
        {"type": "text", "content": "我将使用bash工具获取当前系统时间。"},
        {"type": "tool_call", "content": "bash({'command': 'echo %time%'})"},
    ]
    assert second_pass == [
        {"type": "tool_call", "content": "bash({'command': 'echo %time%'})"},
    ]
