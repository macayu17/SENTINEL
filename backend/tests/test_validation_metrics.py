from backend.src.validation.metrics import classification_metrics, lead_time_summary


def test_lead_time_summary_matches_warnings_to_future_events():
    warnings = [
        {"timestamp": 60, "triggered": True},
        {"timestamp": 120, "triggered": True},
        {"timestamp": 240, "triggered": True},
    ]
    events = [{"timestamp": 150}, {"timestamp": 300}]

    summary = lead_time_summary(warnings, events, horizon_seconds=120)

    assert summary["matched_events"] == 2
    assert summary["lead_times_seconds"] == [90.0, 60.0]
    assert summary["mean_lead_time_seconds"] == 75.0
    assert summary["coverage"] == 1.0


def test_classification_metrics_counts_thresholded_predictions():
    metrics = classification_metrics(
        scores=[0.8, 0.7, 0.2, 0.1],
        labels=[True, False, True, False],
        threshold=0.5,
    )

    assert metrics["true_positive"] == 1
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 1
    assert metrics["true_negative"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["accuracy"] == 0.5
