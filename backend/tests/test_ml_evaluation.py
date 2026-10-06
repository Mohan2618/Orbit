import pytest

from app.services.ml_evaluation import EvaluationInputError, evaluate_file


def test_classification_metrics_are_computed_from_explicit_columns(tmp_path):
    data = tmp_path / "predictions.csv"
    data.write_text("truth,prediction\ncat,cat\ndog,cat\ndog,dog\n,cat\n", encoding="utf-8")

    result = evaluate_file(data, "truth", "prediction", "classification")

    assert result["evaluated_rows"] == 3
    assert result["skipped_rows"] == 1
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["macro_f1"] == pytest.approx(2 / 3)


def test_regression_metrics_are_computed(tmp_path):
    data = tmp_path / "predictions.jsonl"
    data.write_text('{"actual": 1, "estimate": 2}\n{"actual": 3, "estimate": 3}\n', encoding="utf-8")

    result = evaluate_file(data, "actual", "estimate", "regression")

    assert result["mae"] == pytest.approx(0.5)
    assert result["rmse"] == pytest.approx(2**0.5 / 2)
    assert result["r2"] == pytest.approx(0.5)


def test_evaluation_rejects_missing_columns_and_invalid_numbers(tmp_path):
    data = tmp_path / "predictions.csv"
    data.write_text("label,prediction\na,1\n", encoding="utf-8")
    with pytest.raises(EvaluationInputError, match="columns"):
        evaluate_file(data, "truth", "prediction", "classification")
    data.write_text("truth,prediction\na,not-a-number\n", encoding="utf-8")
    with pytest.raises(EvaluationInputError, match="numeric"):
        evaluate_file(data, "truth", "prediction", "regression")
