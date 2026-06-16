import json


def _reset_loader(dl, monkeypatch, mode):
    monkeypatch.setattr(dl, "DATA_MODE", mode)
    dl._LOAD_CACHE.clear()
    dl._TABLE_STATUS.clear()


def test_json_only_mode_loads_local_json(monkeypatch):
    import src.data_loader as dl

    _reset_loader(dl, monkeypatch, "json_only")
    rows = dl._load("support_pathways")
    status = dl.get_data_source_status()

    assert rows
    assert status["tables"]["support_pathways"]["source"] == "json"


def test_uc_mode_calls_unity_catalog_loader(monkeypatch):
    import src.data_loader as dl

    _reset_loader(dl, monkeypatch, "uc")
    calls = []

    def fake_load_uc_table(name):
        calls.append(name)
        return [{"pincode": "560001", "district_norm": "BENGALURU URBAN"}]

    monkeypatch.setattr(dl, "_load_uc_table", fake_load_uc_table)
    rows = dl._load("pincode_district_lookup")

    assert calls == ["pincode_district_lookup"]
    assert rows == [{"pincode": "560001", "district_norm": "BENGALURU URBAN"}]
    assert dl.get_data_source_status()["tables"]["pincode_district_lookup"]["source"] == "uc"


def test_uc_and_json_shapes_are_same_for_app_consumers(monkeypatch):
    import src.data_loader as dl

    _reset_loader(dl, monkeypatch, "json_only")
    local_row = dl._load("support_pathways")[0]

    _reset_loader(dl, monkeypatch, "uc")
    monkeypatch.setattr(dl, "_load_uc_table", lambda name: [dict(local_row)])
    uc_row = dl._load("support_pathways")[0]

    assert set(uc_row.keys()) == set(local_row.keys())


def test_uc_failure_falls_back_with_visible_reason(monkeypatch):
    import src.data_loader as dl

    _reset_loader(dl, monkeypatch, "uc")

    def fail_uc(name):
        raise RuntimeError("warehouse unavailable")

    monkeypatch.setattr(dl, "_load_uc_table", fail_uc)
    rows = dl._load("support_pathways")
    status = dl.get_data_source_status()

    assert rows
    assert status["active_source"] == "json_fallback"
    assert status["tables"]["support_pathways"]["source"] == "json_fallback"
    assert "Unity Catalog load failed" in status["fallback_reason"]


def test_header_badge_says_unity_catalog_when_uc_succeeds():
    from src.ui_helpers import data_source_label

    assert data_source_label("uc", "uc", None) == "Data source: Unity Catalog trusted tables"


def test_header_badge_says_json_fallback_when_uc_fails():
    from src.ui_helpers import data_source_label

    assert (
        data_source_label("uc", "json_fallback", "Unity Catalog load failed: RuntimeError")
        == "Data source: Local sample JSON fallback after Unity Catalog load failure"
    )


def test_state_mode_remains_sqlite_label():
    from src.ui_helpers import state_store_label

    assert state_store_label("sqlite") == "State: Local SQLite fallback"


def test_data_source_status_never_prints_token(monkeypatch):
    import src.data_loader as dl

    _reset_loader(dl, monkeypatch, "uc")
    monkeypatch.setattr(dl, "DATABRICKS_TOKEN", "secret-token-value")
    status_text = json.dumps(dl.get_data_source_status())

    assert "secret-token-value" not in status_text
    assert "DATABRICKS_TOKEN" not in status_text
