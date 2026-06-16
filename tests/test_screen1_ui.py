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
    assert '"Find Trusted Care Options"' in APP_SRC


def test_screen1_subheader_uses_plural_care_needs():
    assert "Describe the family's care needs" in APP_SRC


def test_screen1_textarea_label_uses_plural_care_needs():
    assert '"Family situation and care needs"' in APP_SRC


def test_no_benefitbridge_in_user_facing_strings():
    assert "BenefitBridge AI" not in APP_SRC


_SPLIT_WORD_PATTERNS = [
    # original set
    "sup port", "rep lace", "loc ation", "fac ility",
    "quest ions", "path ways", "confirm ation", "recomm ends",
    # extended set
    "s ituation", "situ ation", "rout ing", "insur ance",
    "pro file", "pu blic", "ser vices", "avail able",
    "re cords", "pro vided", "con firm", "cur rent",
    # final global pass
    "avai lable", "opti ons", "evi dence", "com pleteness",
    "preg nant", "dist rict", "cover age", "post natal",
    "facil ity_trust",
]


def test_no_accidental_split_words_in_hero_and_footer():
    for pat in _SPLIT_WORD_PATTERNS:
        assert pat not in APP_SRC, f"Split word found in app.py: '{pat}'"


def test_no_accidental_split_words_in_ui_helpers():
    from pathlib import Path
    src = Path("src/ui_helpers.py").read_text(encoding="utf-8")
    for pat in _SPLIT_WORD_PATTERNS:
        assert pat not in src, f"Split word found in ui_helpers.py: '{pat}'"


def test_no_accidental_split_words_in_followup():
    from pathlib import Path
    src = Path("src/followup.py").read_text(encoding="utf-8")
    for pat in _SPLIT_WORD_PATTERNS:
        assert pat not in src, f"Split word found in followup.py: '{pat}'"


def test_no_accidental_split_words_in_action_plan():
    from pathlib import Path
    src = Path("src/action_plan.py").read_text(encoding="utf-8")
    for pat in _SPLIT_WORD_PATTERNS:
        assert pat not in src, f"Split word found in action_plan.py: '{pat}'"


# -- Correct Screen 1 strings locked -----------------------------------------

def test_hero_body_text_exact():
    # Check both halves (source splits across two adjacent string literals)
    assert "Describe a family's situation in plain language. TrustRoute AI asks smart follow-up questions," in APP_SRC
    assert "matches support pathways, and recommends nearby facilities using trusted data, trust signals, and uncertainty notes." in APP_SRC


def test_screen1_caption_exact():
    assert "As a community health worker or NGO coordinator, enter the family's health situation" in APP_SRC
    assert "TrustRoute AI will help identify support pathways and nearby facility options." in APP_SRC


def test_screen1_footer_exact():
    assert "TrustRoute AI supports referral decisions." in APP_SRC
    assert "It does not replace professional medical advice or direct confirmation with a facility." in APP_SRC


def test_screen1_title_still_trustroute():
    assert 'st.title("TrustRoute AI")' in APP_SRC


def test_screen1_button_still_find_trusted():
    assert '"Find Trusted Care Options"' in APP_SRC


# -- Correct Screen 2 strings locked -----------------------------------------

def test_screen2_heading_exact():
    assert "A few quick questions to route the family to the right support" in APP_SRC


def test_screen2_caption_contains_trustroute():
    assert "TrustRoute AI can route the family to the right support pathways and facilities" in APP_SRC


def test_screen2_profile_title_routing():
    assert "Profile used for routing" in APP_SRC


def test_screen2_footer_exact():
    assert "Profile updates as you answer questions above. Click Generate when ready." in APP_SRC
