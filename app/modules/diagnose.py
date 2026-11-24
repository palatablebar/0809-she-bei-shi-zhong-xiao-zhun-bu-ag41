"""异常归因：依据检查点与相邻同步点判断设备漂移、基准跳变或证据不足。

归因只使用三方证据：插值基准（相邻同步点）、检查点、读数。
证据冲突时保留不确定，不为赶交接强行归因。
"""

from fractions import Fraction

DRIFT = "DEVICE_DRIFT"
JUMP = "BASELINE_JUMP"
UNCLEAR = "INSUFFICIENT_EVIDENCE"
MEASURED = ("OFFSET_LIMIT", "MISMATCH")


def rate_breaks(anchors, before, after):
    """读数所在同步段的速率是否与相邻段矛盾。

    返回 None 表示没有相邻段可比（同步点不足三个）。
    """
    index = next(
        (
            i
            for i, ((a, _), (c, _)) in enumerate(zip(anchors, anchors[1:]))
            if a == before and c == after
        ),
        None,
    )
    if index is None or len(anchors) < 3:
        return None
    rates = [
        Fraction(d2 - d1, t2 - t1)
        for (t1, d1), (t2, d2) in zip(anchors, anchors[1:])
    ]
    near = [rates[j] for j in (index - 1, index + 1) if 0 <= j < len(rates)]
    if not near:
        return None
    deviates = any(rate != rates[index] for rate in near)
    steady_outside = len(near) == 1 or near[0] == near[1]
    return deviates and steady_outside


def diagnose(case, payload, rows):
    affected = [row["record"] for row in rows if row["kind"] == "reading"]
    status = case["status"]
    if status not in MEASURED or payload is None:
        # 结构性异常无法测量，保留不确定并指向原始状态码。
        return {"cause": UNCLEAR, "affected": affected, "evidence": {"status": status}}
    anchors, _, _ = payload
    evidence = case["measure"]["evidence"]
    residual = evidence["residual_ms"]  # 基准 - 读数
    delta = case["delta"]  # 基准 - 检查点
    rate_break = rate_breaks(anchors, evidence["before_tick"], evidence["after_tick"])
    if delta == 0:
        # 检查点确认基准，读数偏离：设备漂移。
        cause = DRIFT
    elif delta == residual:
        # 检查点确认读数，基准偏离：基准跳变；但同步段速率平滑时证据冲突。
        cause = UNCLEAR if rate_break is False else JUMP
    else:
        # 三方互不一致，证据不足。
        cause = UNCLEAR
    return {
        "cause": cause,
        "affected": affected,
        "evidence": {
            "status": status,
            "residual_ms": residual,
            "check_delta_ms": delta,
            "reading_delta_ms": delta - residual,
            "before_tick": evidence["before_tick"],
            "after_tick": evidence["after_tick"],
            "rate_break": rate_break,
        },
    }
