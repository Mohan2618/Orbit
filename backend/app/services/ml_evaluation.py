"""Explicit-column evaluation for small CSV or JSONL prediction artifacts."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

MAX_DATASET_BYTES = 2 * 1024 * 1024
MAX_EVALUATION_ROWS = 10_000


class EvaluationInputError(ValueError):
    pass


def evaluate_file(path: Path, label_column: str, prediction_column: str, task_type: str) -> dict:
    if path.stat().st_size > MAX_DATASET_BYTES:
        raise EvaluationInputError("Prediction data exceeds the 2 MiB evaluation limit.")
    if task_type not in {"classification", "regression"}:
        raise EvaluationInputError("task_type must be classification or regression.")
    rows = _read_rows(path)
    if len(rows) > MAX_EVALUATION_ROWS:
        raise EvaluationInputError("Prediction data exceeds the 10,000 row evaluation limit.")
    if not rows:
        raise EvaluationInputError("The selected prediction file has no data rows.")
    missing_columns = {label_column, prediction_column} - set(rows[0])
    if missing_columns:
        raise EvaluationInputError("The selected label and prediction columns were not found.")
    valid = [(row.get(label_column), row.get(prediction_column)) for row in rows]
    if any(
        value is not None and not isinstance(value, (str, int, float, bool))
        for pair in valid
        for value in pair
    ):
        raise EvaluationInputError("Label and prediction columns must contain scalar values.")
    valid = [(truth, prediction) for truth, prediction in valid if truth not in {None, ""} and prediction not in {None, ""}]
    if not valid:
        raise EvaluationInputError("No rows contain both a label and a prediction.")
    if task_type == "classification":
        return _classification(valid, len(rows))
    return _regression(valid, len(rows))


def _read_rows(path: Path) -> list[dict]:
    try:
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".csv":
            return list(csv.DictReader(content.splitlines()))
        if path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in content.splitlines() if line.strip()]
            if all(isinstance(row, dict) for row in rows):
                return rows
    except (OSError, UnicodeDecodeError, csv.Error, json.JSONDecodeError) as exc:
        raise EvaluationInputError("The prediction file is not valid UTF-8 CSV or JSONL data.") from exc
    raise EvaluationInputError("Only UTF-8 .csv and .jsonl prediction files are supported.")


def _classification(values: list[tuple[object, object]], total_rows: int) -> dict:
    pairs = [(str(truth), str(prediction)) for truth, prediction in values]
    labels = sorted({truth for truth, _ in pairs} | {prediction for _, prediction in pairs})
    correct = sum(truth == prediction for truth, prediction in pairs)
    per_class = []
    for label in labels:
        true_positive = sum(truth == label and prediction == label for truth, prediction in pairs)
        false_positive = sum(truth != label and prediction == label for truth, prediction in pairs)
        false_negative = sum(truth == label and prediction != label for truth, prediction in pairs)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class.append({"label": label, "precision": precision, "recall": recall, "f1": f1})
    confusion = {}
    for truth, prediction in pairs:
        key = f"{truth} -> {prediction}"
        confusion[key] = confusion.get(key, 0) + 1
    return {
        "task_type": "classification",
        "evaluated_rows": len(pairs),
        "skipped_rows": total_rows - len(pairs),
        "accuracy": correct / len(pairs),
        "macro_precision": sum(item["precision"] for item in per_class) / len(per_class),
        "macro_recall": sum(item["recall"] for item in per_class) / len(per_class),
        "macro_f1": sum(item["f1"] for item in per_class) / len(per_class),
        "per_class": per_class[:100],
        "confusion_counts": dict(list(sorted(confusion.items()))[:500]),
        "limitations": "Metrics use exact string label matching; class balance and domain suitability are not assessed.",
    }


def _regression(values: list[tuple[object, object]], total_rows: int) -> dict:
    try:
        pairs = [(float(truth), float(prediction)) for truth, prediction in values]
    except (TypeError, ValueError) as exc:
        raise EvaluationInputError("Regression labels and predictions must be numeric.") from exc
    if any(not math.isfinite(value) for pair in pairs for value in pair):
        raise EvaluationInputError("Regression labels and predictions must be finite numbers.")
    mean_truth = sum(truth for truth, _ in pairs) / len(pairs)
    absolute_error = [abs(truth - prediction) for truth, prediction in pairs]
    squared_error = [(truth - prediction) ** 2 for truth, prediction in pairs]
    if any(not math.isfinite(value) for value in squared_error):
        raise EvaluationInputError("Regression values are outside the supported numeric range.")
    total_sum_squares = sum((truth - mean_truth) ** 2 for truth, _ in pairs)
    return {
        "task_type": "regression",
        "evaluated_rows": len(pairs),
        "skipped_rows": total_rows - len(pairs),
        "mae": sum(absolute_error) / len(pairs),
        "rmse": math.sqrt(sum(squared_error) / len(pairs)),
        "r2": 1 - sum(squared_error) / total_sum_squares if total_sum_squares else None,
        "limitations": "Evaluation uses the supplied rows only; data quality and statistical significance are not assessed.",
    }
