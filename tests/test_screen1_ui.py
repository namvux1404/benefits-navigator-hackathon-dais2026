"""Tests for Screen 1 presentation polish: hero card, SVG asset, badge pills."""
import re
from pathlib import Path

APP_SRC = Path("app.py").read_text(encoding="utf-8")
SVG_PATH = Path("assets") / "benefitbridge_logo.svg"


# -- App title -----------------------------------------------------------------

def test_app_title_is_exact():
    assert 'st.title("TrustRoute AI")' in APP_SRC


# -- Mojibake and emoji guards -------------------------------------------------

def test_no_mojibake_eth_thorn():
    assert chr(0x00F0) + chr(0x0178) not in APP_SRC


def test_no_mojibake_a_circumflex():
    assert chr(0x00E2) not in APP_SRC


def test_no_replacement_character():
    assert chr(0xFFFD) not in APP_SRC


def test_tab_labels_are_plain_text():
    assert '["Referral Navigator", "Program Leader Dashboard", "Data Trust / Debug"]' in APP_SRC


def test_tab_labels_contain_no_high_unicode():
    match = re.search(r'st\.tabs\(\s*\[([^\]]+)\]', APP_SRC)
    assert match, "st.tabs(...) not found"
    for ch in match.group(1):
        assert ord(ch) < 0x1F300, f"High-range char U+{ord(ch):04X} in tab labels"


def test_title_contains_no_emoji():
    match = re.search(r'st\.title\(([^)]+)\)', APP_SRC)
    assert match, "st.title(...) not found"
    for ch in match.group(1):
        assert ord(ch) < 0x1F300, f"Emoji char U+{ord(ch):04X} in st.title"


# -- Hero section content ------------------------------------------------------

def test_hero_subtitle_present():
    assert "Evidence-backed referral guidance for families and field workers." in APP_SRC


def test_hero_description_present():
    assert "Describe a family's situation in plain language" in APP_SRC


def test_hero_uses_inline_svg():
    assert "<svg" in APP_SRC


def test_hero_has_dark_gradient_background():
    assert "linear-gradient" in APP_SRC


def test_hero_brand_name_inside_card():
    assert "TrustRoute AI" in APP_SRC


# -- SVG asset file ------------------------------------------------------------

def test_svg_asset_file_exists():
    assert SVG_PATH.exists(), "assets/benefitbridge_logo.svg not found"


def test_svg_uses_standard_shapes_only():
    svg_text = SVG_PATH.read_text(encoding="utf-8")
    allowed = {"svg", "rect", "path", "line", "circle", "g", "polygon",
                "polyline", "text", "defs", "title", "desc"}
    found = set(re.findall(r"<(\w+)[\s/>]", svg_text))
    disallowed = found - allowed
    assert not disallowed, f"Non-standard SVG elements: {disallowed}"


def test_svg_has_no_external_references():
    svg_text = SVG_PATH.read_text(encoding="utf-8")
    # xmlns namespace declaration is required — only flag actual remote resource refs
    assert "xlink:href" not in svg_text
    assert "url(http" not in svg_text
    assert "<image" not in svg_text


def test_svg_has_viewbox():
    svg_text = SVG_PATH.read_text(encoding="utf-8")
    assert "viewBox" in svg_text


# -- Badge pill helpers --------------------------------------------------------

def test_badge_data_label_json():
    from src.ui_helpers import badge_data_label
    label = badge_data_label("json_only")
    assert label.startswith("Data:")
    assert "JSON" in label


def test_badge_data_label_uc():
    from src.ui_helpers import badge_data_label
    label = badge_data_label("uc")
    assert label.startswith("Data:")
    assert "Unity Catalog" in label


def test_badge_data_label_fallback():
    from src.ui_helpers import badge_data_label
    label = badge_data_label("uc", active_source="json_fallback")
    assert label.startswith("Data:")
    assert "JSON" in label


def test_badge_state_label_sqlite():
    from src.ui_helpers import badge_state_label
    label = badge_state_label("sqlite")
    assert label.startswith("State:")
    assert "SQLite" in label


def test_badge_state_label_lakebase():
    from src.ui_helpers import badge_state_label
    label = badge_state_label("lakebase")
    assert label.startswith("State:")
    assert "Lakebase" in label


def test_badge_ai_label_claude():
    from src.ui_helpers import badge_ai_label
    label = badge_ai_label(True, "claude-sonnet-4-5-20250929")
    assert label.startswith("AI:")
    assert "Sonnet" in label or "Claude" in label


def test_badge_ai_label_deterministic():
    from src.ui_helpers import badge_ai_label
    label = badge_ai_label(False, "")
    assert label.startswith("AI:")
    assert "Deterministic" in label


def test_badge_pills_html_in_app():
    assert "border-radius:12px" in APP_SRC


def test_badge_data_label_imported_in_app():
    assert "badge_data_label" in APP_SRC


def test_badge_state_label_imported_in_app():
    assert "badge_state_label" in APP_SRC


def test_badge_ai_label_imported_in_app():
    assert "badge_ai_label" in APP_SRC


# -- Screen 1 layout order ----------------------------------------------------

def test_hero_comes_before_text_area():
    hero_idx = APP_SRC.index("linear-gradient")
    text_area_idx = APP_SRC.index("st.text_area(")
    assert hero_idx < text_area_idx


def test_text_area_before_sample_expander():
    text_area_idx = APP_SRC.index("st.text_area(")
    expander_idx = APP_SRC.index('st.expander("Try a sample referral scenario"')
    assert text_area_idx < expander_idx


def test_sample_scenarios_in_expander():
    assert 'st.expander("Try a sample referral scenario", expanded=False)' in APP_SRC


def test_analyze_button_label():
    assert '"Analyze care need"' in APP_SRC
