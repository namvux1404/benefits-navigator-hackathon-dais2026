from src.data_loader import (
    get_district_for_pincode,
    get_nfhs_for_district,
    get_facilities,
    load_pathways,
    load_scenarios,
)


def test_demo_pincode_lookup():
    result = get_district_for_pincode("560001")
    assert result is not None
    assert result["district_norm"] == "BENGALURU URBAN"
    assert result["state_norm"] == "KARNATAKA"


def test_pincode_with_leading_space():
    result = get_district_for_pincode(" 560001")
    assert result is not None


def test_unknown_pincode_returns_none():
    assert get_district_for_pincode("000000") is None


def test_nfhs_alias_resolves_bangalore():
    """BENGALURU URBAN -> alias BANGALORE -> should match NFHS 'Bangalore ' row."""
    rows = get_nfhs_for_district("BENGALURU URBAN", "KARNATAKA")
    assert len(rows) > 0
    norm_names = [r.get("district_name", "").strip().upper() for r in rows]
    assert any("BANGALORE" in n for n in norm_names)


def test_nfhs_state_fallback_for_unknown_district():
    rows = get_nfhs_for_district("XYZZY DISTRICT", "KARNATAKA")
    # Should return Karnataka state rows (max 5) or empty; never crash
    assert isinstance(rows, list)
    assert len(rows) <= 5
    for r in rows:
        assert r.get("state_ut", "").strip().upper() == "KARNATAKA"


def test_facilities_returns_list():
    facilities = get_facilities("560001", "BENGALURU URBAN", "KARNATAKA")
    assert isinstance(facilities, list)
    assert len(facilities) > 0


def test_pathways_six_rows():
    pathways = load_pathways()
    assert len(pathways) == 6
    ids = {pw["pathway_id"] for pw in pathways}
    for expected in (
        "maternal_care",
        "child_nutrition",
        "immunization",
        "health_insurance_awareness",
        "household_health_risk",
        "women_preventive_screening",
    ):
        assert expected in ids


def test_scenarios_loads():
    scenarios = load_scenarios()
    assert len(scenarios) >= 1
    assert "scenario_text" in scenarios[0]


# -- Facility ranking ----------------------------------------------------------

def test_rank_facilities_deprioritises_dental_for_maternal():
    """Dental-only facility should rank below hospital when maternal pathways are matched."""
    from src.data_loader import rank_facilities_for_pathways
    facilities = [
        {
            "name": "Dental Lavelle",
            "organization_type": "Dental Clinic",
            "specialties": "Dentistry",
            "address_zipOrPostcode": "560001",
            "address_stateOrRegion": "KARNATAKA",
            "officialPhone": "",
        },
        {
            "name": "City General Hospital",
            "organization_type": "Hospital",
            "specialties": "General Medicine, Obstetrics",
            "address_zipOrPostcode": "560001",
            "address_stateOrRegion": "KARNATAKA",
            "officialPhone": "080-12345678",
        },
        {
            "name": "Child Health Clinic",
            "organization_type": "Pediatric Clinic",
            "specialties": "Pediatrics",
            "address_zipOrPostcode": "560001",
            "address_stateOrRegion": "KARNATAKA",
            "officialPhone": "",
        },
    ]
    ranked = rank_facilities_for_pathways(
        facilities,
        pathway_ids={"maternal_care", "child_nutrition"},
        pincode="560001",
        state_norm="KARNATAKA",
    )
    names = [f["name"] for f in ranked]
    dental_idx = names.index("Dental Lavelle")
    hospital_idx = names.index("City General Hospital")
    assert hospital_idx < dental_idx, f"Hospital should rank above dental. Order: {names}"


def test_rank_facilities_pincode_match_is_tier_0():
    """Facilities with exact pincode match should always come before other-state facilities."""
    from src.data_loader import rank_facilities_for_pathways
    facilities = [
        {"name": "Far Hospital", "address_zipOrPostcode": "110001", "address_stateOrRegion": "DELHI"},
        {"name": "Local Clinic", "address_zipOrPostcode": "560001", "address_stateOrRegion": "KARNATAKA"},
    ]
    ranked = rank_facilities_for_pathways(facilities, pincode="560001", state_norm="KARNATAKA")
    assert ranked[0]["name"] == "Local Clinic"
