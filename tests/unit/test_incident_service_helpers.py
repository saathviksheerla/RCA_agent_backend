import pytest

from app.services.incident_service import _score_recalled, _parse_recalled


class TestScoreRecalled:
    def test_matching_service_and_environment_scores_highest(self):
        text = "Title: X\nService: payment-service\nEnvironment: production"
        assert _score_recalled(text, "payment-service", "production") == 3

    def test_matching_service_only(self):
        text = "Service: payment-service\nEnvironment: staging"
        assert _score_recalled(text, "payment-service", "production") == 2

    def test_matching_environment_only(self):
        text = "Service: other-service\nEnvironment: production"
        assert _score_recalled(text, "payment-service", "production") == 1

    def test_no_match_scores_zero(self):
        text = "Service: other-service\nEnvironment: staging"
        assert _score_recalled(text, "payment-service", "production") == 0

    def test_empty_text_scores_zero(self):
        assert _score_recalled("", "payment-service", "production") == 0


class TestParseRecalled:
    def test_full_record_parses_all_fields(self):
        text = (
            "Title: Checkout latency spike\n"
            "Service: payment-service\n"
            "Environment: production\n"
            "Symptoms: connection pool exhausted\n"
            "Fix Applied: scaled RDS instance"
        )
        result = _parse_recalled(text)
        assert result.incident_title == "Checkout latency spike"
        assert result.service == "payment-service"
        assert result.symptom == "connection pool exhausted"
        assert result.fix == "scaled RDS instance"

    def test_missing_fix_applied_defaults_to_not_resolved_yet(self):
        text = "Title: X\nSymptoms: Y\nService: Z"
        result = _parse_recalled(text)
        assert result.fix == "Not resolved yet"

    def test_missing_fields_default_to_empty_string(self):
        result = _parse_recalled("")
        assert result.incident_title == ""
        assert result.symptom == ""
        assert result.service == ""
        assert result.fix == "Not resolved yet"

    def test_colon_in_value_only_splits_on_first_colon(self):
        text = "Title: Incident: timeout at 12:00"
        result = _parse_recalled(text)
        assert result.incident_title == "Incident: timeout at 12:00"
