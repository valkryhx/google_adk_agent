from skills.dex.models import DexTaskStatus
from skills.dex.summary import summarize_output


def test_summarize_output_extracts_result_and_error():
    ok = summarize_output(0, "line1\nreport done\n")
    assert ok["status"] is DexTaskStatus.COMPLETED
    assert ok["result_summary"] == "report done"
    assert ok["error_summary"] is None

    failed = summarize_output(1, "traceback\nboom\n")
    assert failed["status"] is DexTaskStatus.FAILED
    assert failed["result_summary"] is None
    assert failed["error_summary"] == "boom"
