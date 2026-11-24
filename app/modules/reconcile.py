from collections import Counter


def balance(intake, cases):
    accounted = (
        intake["accepted"] + intake["rejected"] + intake["blank"] + intake["repeated"]
    )
    status = Counter(case["status"] for case in cases)
    ready = status.pop("READY", 0)
    observed = sum(len(case["records"]) for case in cases)
    anomalies = [case for case in cases if case["status"] != "READY"]
    diagnosed = [case for case in anomalies if case.get("diagnosis")]
    causes = Counter(case["diagnosis"]["cause"] for case in diagnosed)
    balanced = accounted == intake["input"] and observed == intake["accepted"]
    return dict(
        input=intake["input"],
        accepted=intake["accepted"],
        isolated=intake["rejected"],
        ignored=intake["blank"] + intake["repeated"],
        accounted=accounted,
        balanced=balanced,
        ready=ready,
        pending=len(cases) - ready,
        issues=dict(sorted(status.items())),
        anomalies=len(anomalies),
        diagnosed=len(diagnosed),
        causes=dict(sorted(causes.items())),
        releasable=bool(cases)
        and balanced
        and not intake["rejected"]
        and len(diagnosed) == len(anomalies),
    )
