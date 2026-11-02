from app.api.health import health


def test_health_reports_model_database_and_sarvam_subsystems():
    body = health()
    assert {"model_loaded", "database_initialized", "sarvam_configured"} <= body.keys()
    assert {"model", "database", "sarvam"} <= body["subsystems"].keys()
