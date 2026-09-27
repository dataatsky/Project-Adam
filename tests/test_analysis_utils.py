import pandas as pd

import pandas as pd

from analysis_utils import compute_mismatch_rate, compute_behavior_metrics


def test_compute_mismatch_rate_penalizes_missing_matches():
    df = pd.DataFrame({
        "imagined_outcomes_parsed": [["a", "b"]],
        "simulated_outcomes_parsed": [["a"]],
    })

    compute_mismatch_rate(df)

    assert df.loc[0, "mismatch_rate"] == 0.5


def test_compute_behavior_metrics_adds_columns():
    df = pd.DataFrame({
        "action_result_parsed": [{"success": True}, {"success": False}],
        "chosen_verb": ["wait", "go"],
        "impulses_parsed": [[{"urgency": 0.5}], [{"urgency": 0.9}, {"urgency": 0.3}]],
        "mood_intensity": [0.3, 0.6],
    })

    compute_behavior_metrics(df, window=2)

    assert "success_rate" in df.columns
    assert "wait_ratio" in df.columns
    assert "avg_impulse_urgency" in df.columns
    assert "mood_delta" in df.columns
    assert df.loc[1, "success_rate"] == 0.5


def test_mismatch_rate_ignores_options_that_were_not_imagined():
    from analysis_utils import compute_mismatch_rate_fuzzy

    df = pd.DataFrame({
        "imagined_outcomes_parsed": [[None, None], ["I reach the kitchen", None]],
        "simulated_outcomes_parsed": [["I walked north.", "Time passes."], ["I walked north into the kitchen.", "Time passes."]],
    })
    compute_mismatch_rate(df)
    assert pd.isna(df.loc[0, "mismatch_rate"])  # nothing imagined: no data, not 100% mismatch
    assert df.loc[1, "mismatch_rate"] == 1.0    # exact comparison of the one imagined option
    compute_mismatch_rate_fuzzy(df)
    assert pd.isna(df.loc[0, "mismatch_rate"])


def test_exact_and_fuzzy_mismatch_agree_on_missing_simulations():
    from analysis_utils import compute_mismatch_rate_fuzzy

    df = pd.DataFrame({"imagined_outcomes_parsed": [["a", "b"]], "simulated_outcomes_parsed": [["a"]]})
    compute_mismatch_rate(df)
    exact = df.loc[0, "mismatch_rate"]
    compute_mismatch_rate_fuzzy(df)
    assert exact == df.loc[0, "mismatch_rate"] == 0.5


def test_old_free_text_moods_are_normalized(tmp_path):
    from analysis_utils import prepare_dataframe
    from constants import LOG_HEADERS
    import csv

    path = tmp_path / "log.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_HEADERS)
        w.writeheader()
        for i, mood in enumerate(["curiosity", "Curious", "hunger", "resolve", "zany"]):
            w.writerow({"timestamp": i, "cycle_num": i, "mood": mood, "chosen_action": "wait_None"})
    df = prepare_dataframe(str(path))
    assert df["mood"].tolist() == ["curious", "curious", "hungry", "determined", "zany"]
