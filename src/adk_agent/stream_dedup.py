DEFAULT_OVERLAP_WINDOW = 800
DEFAULT_MIN_CROSS_TYPE_OVERLAP = 6
THINK_CLOSE_MARKERS = ("</think>", "</thought>")


def compute_same_type_delta(
    base_acc: str,
    raw_fragment: str,
    overlap_window: int = DEFAULT_OVERLAP_WINDOW,
) -> str:
    if not raw_fragment:
        return ""

    if raw_fragment.startswith(base_acc):
        return raw_fragment[len(base_acc):]

    max_overlap = 0
    scan_base = base_acc[-overlap_window:]
    overlap_len = min(len(scan_base), len(raw_fragment))
    for i in range(1, overlap_len + 1):
        if scan_base.endswith(raw_fragment[:i]):
            max_overlap = i

    return raw_fragment[max_overlap:]


def strip_leaked_think_from_text(raw_fragment: str) -> tuple[str, bool]:
    if not raw_fragment:
        return "", False

    lowered = raw_fragment.lower()
    marker_pos = -1
    marker_len = 0

    for marker in THINK_CLOSE_MARKERS:
        pos = lowered.rfind(marker)
        if pos > marker_pos:
            marker_pos = pos
            marker_len = len(marker)

    if marker_pos < 0:
        return raw_fragment, False

    cleaned = raw_fragment[marker_pos + marker_len :].lstrip()
    return cleaned, True


def dedupe_textual_event_chunks(
    chunks: list[dict],
    accumulated_text_by_type: dict[str, str],
) -> list[dict]:
    current_totals = {"thought": "", "text": ""}
    emitted_types: set[str] = set()
    output_chunks: list[dict] = []

    for chunk in chunks:
        c_type = chunk.get("type")
        if c_type in current_totals and isinstance(chunk.get("content"), str):
            current_totals[c_type] += chunk["content"]

    for chunk in chunks:
        c_type = chunk.get("type")
        if c_type not in current_totals:
            output_chunks.append(chunk)
            continue

        if c_type in emitted_types:
            continue
        emitted_types.add(c_type)

        raw_fragment = current_totals[c_type]
        if not raw_fragment:
            continue

        base_acc = accumulated_text_by_type[c_type]
        raw_delta = compute_same_type_delta(
            base_acc=base_acc,
            raw_fragment=raw_fragment,
        )

        if not raw_delta:
            continue

        accumulated_text_by_type[c_type] = advance_stream_accumulator(
            base_acc=base_acc,
            raw_fragment=raw_fragment,
            raw_delta=raw_delta,
        )

        display_delta = compute_stream_delta(
            base_acc=base_acc,
            raw_fragment=raw_fragment,
            previous_other_type_acc=accumulated_text_by_type["thought"] if c_type == "text" else "",
            is_first_fragment_of_type=(not base_acc and c_type == "text"),
        )

        if c_type == "text":
            display_delta, _ = strip_leaked_think_from_text(display_delta)

        if display_delta:
            output_chunks.append({"type": c_type, "content": display_delta})

    return output_chunks


def trim_cross_type_prefix(
    delta: str,
    previous_other_type_acc: str,
    is_first_fragment_of_type: bool,
    overlap_window: int = DEFAULT_OVERLAP_WINDOW,
    min_overlap: int = DEFAULT_MIN_CROSS_TYPE_OVERLAP,
) -> str:
    if not delta or not previous_other_type_acc or not is_first_fragment_of_type:
        return delta

    scan_base = previous_other_type_acc[-overlap_window:]
    overlap_len = min(len(scan_base), len(delta))
    max_overlap = 0
    for i in range(min_overlap, overlap_len + 1):
        if scan_base.endswith(delta[:i]):
            max_overlap = i

    return delta[max_overlap:]


def compute_stream_delta(
    base_acc: str,
    raw_fragment: str,
    previous_other_type_acc: str = "",
    is_first_fragment_of_type: bool = False,
    overlap_window: int = DEFAULT_OVERLAP_WINDOW,
    min_cross_type_overlap: int = DEFAULT_MIN_CROSS_TYPE_OVERLAP,
) -> str:
    delta = compute_same_type_delta(
        base_acc=base_acc,
        raw_fragment=raw_fragment,
        overlap_window=overlap_window,
    )
    return trim_cross_type_prefix(
        delta=delta,
        previous_other_type_acc=previous_other_type_acc,
        is_first_fragment_of_type=is_first_fragment_of_type,
        overlap_window=overlap_window,
        min_overlap=min_cross_type_overlap,
    )


def advance_stream_accumulator(base_acc: str, raw_fragment: str, raw_delta: str) -> str:
    if raw_fragment.startswith(base_acc):
        return raw_fragment
    return base_acc + raw_delta
