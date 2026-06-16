"""TRUSTROUTE AI — Evidence-backed referral guidance for families and field workers.

Track 3: Referral Copilot  |  Supporting: Track 1 Facility Trust Desk

Helps community health workers route families to trusted care options using plain-language
intake, smart follow-up questions, support pathway matching, facility trust signals,
evidence and uncertainty notes, and nearby facility recommendations.
Uses Unity Catalog trusted tables (Gate B mode) with SQLite state store and Claude Sonnet.

Session flow:
  Screen 1 (step=0) - family care need input
  Screen 2 (step=1) - follow-up questions + profile card + "Generate support plan"
  Screen 3 (step=2) - matched pathways, support plan, NFHS indicators, facilities
"""
from __future__ import annotations

import json

import streamlit as st

from src.config import (
    CLAUDE_AVAILABLE,
    CLAUDE_MODEL,
    DATA_MODE,
    SAMPLE_DATA_DIR,
    STATE_STORE_MODE,
    UC_CATALOG,
    UC_SCHEMA,
)
from src.data_loader import (
    _load,
    _norm,
    get_data_source_status,
    get_district_alias,
    get_district_for_pincode,
    get_facilities,
    get_facility_trust_score,
    get_nfhs_for_district,
    get_nfhs_lookup_trace,
    list_nfhs_districts,
    load_facility_trust_scores,
    load_pathways,
    load_scenarios,
    rank_facilities_for_pathways,
)
from src.bb_logging import (
    log_base_profile,
    log_final_profile,
    log_matched_pathways,
    log_facilities_selected,
    log_district_context,
    log_action_plan_input,
    log_nfhs_lookup_trace,
)
from src.profile_extractor import extract_profile_with_trace
from src.followup import (
    generate_followup_questions_with_trace,
    merge_profile,
    parse_followup_answers,
)
from src.rules_engine import _eval_condition, match_pathways
from src.action_plan import generate_action_plan_with_trace
from src.agent_trace import empty_agent_trace, rules_engine_trace, step_display_label
from src.state_store import StateStore
from src.ui_helpers import (
    ai_mode_label,
    badge_ai_label,
    badge_data_label,
    badge_state_label,
    compute_proxy_trust_signal,
    data_source_label,
    district_context_rows,
    facility_evidence_summary,
    facility_why_shown,
    format_facility,
    get_nfhs_display_rows,
    limited_facilities,
    pathway_reason,
    plan_method_label,
    preferred_district_index,
    state_store_label,
)

# -- Page config --------------------------------------------------------------
st.set_page_config(
    page_title="TrustRoute AI",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -- Session state init -------------------------------------------------------
_STATE_DEFAULTS: dict = {
    "step": 0,
    "original_text": "",
    "base_profile": None,
    "followup_questions": [],
    "followup_answers": {},
    "followup_updates": {},
    "final_profile": None,
    "matched_pathways": [],
    "action_plan": "",
    "plan_method": "",
    "agent_trace": empty_agent_trace(),
    "nfhs_rows": [],
    "facilities_list": [],
    "district_info": {},
    "nfhs_lookup_trace": {},
    "session_id": None,
    "feedback_submitted": False,
    "shortlisted_facilities": [],
    "facility_scoring_trace": {},
}
for _k, _v in _STATE_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

store = StateStore()
pathways = load_pathways()
data_status = get_data_source_status()

# -- Header -------------------------------------------------------------------
st.title("TrustRoute AI")
_pill = (
    "background:#e8f4f8;color:#1a3a4f;border:1px solid #b8d8e8;"
    "padding:3px 11px;border-radius:12px;font-size:0.75rem;font-weight:600;"
    "display:inline-block;margin-right:6px;"
)
st.markdown(
    f'<div style="margin:4px 0 16px;">'
    f'<span style="{_pill}">{badge_data_label(DATA_MODE, data_status.get("active_source"), data_status.get("fallback_reason"))}</span>'
    f'<span style="{_pill}">{badge_state_label(STATE_STORE_MODE)}</span>'
    f'<span style="{_pill}">{badge_ai_label(CLAUDE_AVAILABLE, CLAUDE_MODEL)}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

tab1, tab2, tab3 = st.tabs(
    ["Referral Navigator", "Program Leader Dashboard", "Data Trust / Debug"]
)

# ============================================================================
# TAB 1 - FAMILY NAVIGATOR
# ============================================================================
with tab1:
    step = st.session_state.step

    # -- SCREEN 1: Scenario input --------------------------------------------
    if step == 0:
        _route_svg = (
            '<svg viewBox="0 0 200 64" xmlns="http://www.w3.org/2000/svg" width="130" height="42">'
            '<line x1="22" y1="32" x2="162" y2="32" stroke="#5ab4cf" stroke-width="2.5"'
            ' stroke-dasharray="5,4" opacity="0.65"/>'
            '<circle cx="22" cy="32" r="9" fill="#1a3a4f" stroke="#7ec8e3" stroke-width="2.5"/>'
            '<circle cx="22" cy="32" r="4" fill="#a9d8ed"/>'
            '<circle cx="82" cy="32" r="8" fill="#1d5a7a" stroke="#7ec8e3" stroke-width="2"/>'
            '<circle cx="82" cy="32" r="3.5" fill="#7ec8e3"/>'
            '<circle cx="142" cy="32" r="8" fill="#1d5a7a" stroke="#7ec8e3" stroke-width="2"/>'
            '<circle cx="142" cy="32" r="3.5" fill="#7ec8e3"/>'
            '<polygon points="168,32 157,26 157,38" fill="#7ec8e3" opacity="0.85"/>'
            '<path d="M 183 14 L 198 20 L 198 36 Q 190 46 183 50 Q 176 46 168 36 L 168 20 Z"'
            ' fill="#0d4f6b" stroke="#7ee3c8" stroke-width="1.5"/>'
            '<polyline points="175,32 181,39 192,22" stroke="#a9d8ed" stroke-width="2.2"'
            ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
        )
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#1a3a4f 0%,#1d6b8a 100%);'
            f'border-radius:10px;padding:24px 32px;margin-bottom:20px;">'
            f'<div style="display:flex;align-items:center;gap:20px;margin-bottom:12px;">'
            f'{_route_svg}'
            f'<div>'
            f'<div style="color:#ffffff;font-size:1.5rem;font-weight:700;'
            f'letter-spacing:-0.2px;margin-bottom:5px;">TrustRoute AI</div>'
            f'<div style="color:#a9d8ed;font-size:1rem;">Evidence-backed referral guidance for families and field workers.</div>'
            f'</div></div>'
            f'<div style="color:#8ecfe0;font-size:0.9rem;line-height:1.6;">'
            f"Describe a family's situation in plain language. TrustRoute AI asks smart follow-up questions, "
            f'matches support pathways, and recommends nearby facilities using trusted data, trust signals, and uncertainty notes.'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        st.subheader("Describe the family's care need")
        st.caption(
            "As a community health worker or NGO coordinator, enter the family's health situation "
            "in plain language. TrustRoute AI will help identify support pathways and nearby facility options."
        )

        raw = st.text_area(
            "Family situation and care need",
            value=st.session_state.original_text,
            height=180,
            placeholder=(
                "Example: I live in pincode 560001. I am pregnant and have a 3-year-old child. "
                "I do not know where to go for affordable health services. "
                "I need help with nutrition, vaccination, and finding a nearby facility."
            ),
        )

        scenarios = load_scenarios()
        if scenarios:
            sample_labels = {
                "scenario_maternal_nutrition": "Pregnant mother with young child",
                "scenario_child_vaccination": "Parent with child needing vaccination",
                "scenario_field_worker_district_risk": "Field worker reviewing district health risk",
            }
            with st.expander("Try a sample referral scenario", expanded=False):
                demo_cols = st.columns(min(len(scenarios), 3))
                for i, sc in enumerate(scenarios):
                    label = sample_labels.get(sc.get("id"), sc.get("title", "Sample scenario"))
                    if demo_cols[i % 3].button(label, key=f"demo_{i}"):
                        st.session_state.original_text = sc["scenario_text"]
                        st.rerun()

        if st.button("Analyze care need", type="primary", disabled=not raw.strip()):
            spinner_msg = (
                "Analysing your situation with Claude..."
                if CLAUDE_AVAILABLE
                else "Extracting profile..."
            )
            with st.spinner(spinner_msg):
                base_profile, profile_trace = extract_profile_with_trace(raw.strip())

                pincode = base_profile.get("pincode") or ""
                district_info: dict = {}
                nfhs_rows: list[dict] = []
                facilities: list[dict] = []

                nfhs_lookup_trace_val: dict = {}
                if pincode:
                    district_info = get_district_for_pincode(pincode) or {}
                    if district_info:
                        base_profile["district_norm"] = district_info["district_norm"]
                        base_profile["state_norm"] = district_info["state_norm"]
                        nfhs_rows = get_nfhs_for_district(
                            district_info["district_norm"], district_info["state_norm"]
                        )
                        nfhs_lookup_trace_val = get_nfhs_lookup_trace(
                            district_info["district_norm"], district_info["state_norm"]
                        )
                        facilities = get_facilities(
                            pincode, district_info["district_norm"], district_info["state_norm"]
                        )
                log_base_profile(base_profile, pincode_source="pincode_district_lookup")
                log_nfhs_lookup_trace(nfhs_lookup_trace_val)

                followup_qs, followup_trace = generate_followup_questions_with_trace(
                    base_profile, raw.strip()
                )

            # Clear any previous follow-up form inputs from session state
            for _old_key in list(st.session_state.keys()):
                if _old_key.startswith("fq_"):
                    del st.session_state[_old_key]

            st.session_state.original_text = raw.strip()
            st.session_state.base_profile = base_profile
            st.session_state.agent_trace = {
                "profile_extraction": profile_trace,
                "followup_questions": followup_trace,
                "action_plan": empty_agent_trace()["action_plan"],
                "rules_engine": rules_engine_trace(),
            }
            st.session_state.district_info = district_info
            st.session_state.nfhs_rows = nfhs_rows
            st.session_state.nfhs_lookup_trace = nfhs_lookup_trace_val
            st.session_state.facilities_list = facilities
            st.session_state.followup_questions = followup_qs
            st.session_state.followup_answers = {}
            st.session_state.followup_updates = {}
            st.session_state.final_profile = None
            st.session_state.step = 1
            st.rerun()

        st.caption(
            "TrustRoute AI supports referral decisions. "
            "It does not replace professional medical advice or direct confirmation with a facility."
        )

    # -- SCREEN 2: Follow-up questions + profile card -------------------------
    elif step == 1:
        base_profile: dict = st.session_state.base_profile
        questions: list[dict] = st.session_state.followup_questions

        st.subheader("A few quick questions to route the family to the right support")
        st.caption(
            "Answer 2-3 short questions so TrustRoute AI can route the family to the right support pathways and facilities."
        )

        with st.expander("Your original description", expanded=False):
            st.write(st.session_state.original_text)

        # -- Follow-up questions (no form wrapper — allows live profile preview) -
        form_answers: dict[str, str] = {}
        for q in questions:
            form_answers[q["id"]] = st.text_input(
                q["question"],
                key=f"fq_{q['id']}",
                placeholder=q.get("placeholder", "Type your answer here..."),
            )

        # -- Live profile preview (updates as user fills in answers) ----------
        st.markdown("---")
        st.markdown("**Profile used for routing** *(updates as you answer questions above)*")

        _di = st.session_state.district_info
        _pin = base_profile.get("pincode") or "-"
        _dist = _di.get("district_norm", "") or "-"
        _state_name = _di.get("state_norm", "")
        _loc = f"{_dist}, {_state_name}".strip(", ") or "-"

        if base_profile.get("pregnant"):
            _preg_str = "Pregnant"
        elif base_profile.get("recently_delivered"):
            _preg_str = "Recently delivered"
        else:
            _preg_str = "Not pregnant"

        if base_profile.get("child_under_5"):
            _age_m = base_profile.get("child_age_months")
            if _age_m:
                _yrs = _age_m // 12
                _rem = _age_m % 12
                _child_str = (
                    f"{_age_m} months ({_yrs}y {_rem}m)" if _rem
                    else f"{_age_m} months ({_yrs} yr)"
                )
            else:
                _child_str = "Under 5 (age not specified)"
        else:
            _child_str = "No child under 5"

        _needs = base_profile.get("needs") or []
        _needs_str = ", ".join(_needs) if _needs else "-"

        # Parse current form_answers for live insurance/travel/urgency preview
        _preview_updates = parse_followup_answers(questions, form_answers)

        _ins_parts = []
        if _preview_updates.get("uninsured") is True or base_profile.get("uninsured") is True:
            _ins_parts.append("Uninsured / no coverage")
        if _preview_updates.get("low_cost_need") or base_profile.get("low_income"):
            _ins_parts.append("Low-cost need")
        if _preview_updates.get("insurance_status") == "insured":
            _ins_parts = ["Insured"]
        _ins_str = " · ".join(_ins_parts) if _ins_parts else "Will be applied when you generate the plan."

        _travel_km = _preview_updates.get("travel_km") or base_profile.get("travel_km")
        _travel_str = f"Up to {_travel_km} km" if _travel_km else "Will be applied when you generate the plan."

        _urgency_val = _preview_updates.get("urgency") or base_profile.get("urgency", "")
        if _urgency_val == "urgent":
            _urgency_str = "Urgent today"
        elif _urgency_val == "routine":
            _urgency_str = "Planning ahead (routine)"
        else:
            _urgency_str = "Will be applied when you generate the plan."

        _pc1, _pc2 = st.columns(2)
        with _pc1:
            st.write(f"**PIN:** {_pin}")
            st.write(f"**District / State:** {_loc}")
            st.write(f"**Pregnancy status:** {_preg_str}")
            st.write(f"**Child age:** {_child_str}")
        with _pc2:
            st.write(f"**Needs detected:** {_needs_str}")
            st.write(f"**Insurance / cost:** {_ins_str}")
            st.write(f"**Travel range:** {_travel_str}")
            st.write(f"**Urgency:** {_urgency_str}")

        st.caption(
            "Profile updates as you answer questions above. Click Generate when ready."
        )

        st.markdown("")
        submitted = st.button("Generate support plan", type="primary")

        if submitted:
            # 1 - Parse free-text answers -> structured updates
            followup_updates = parse_followup_answers(questions, form_answers)

            # 2 - If pincode newly provided, look up district/NFHS/facilities
            if "pincode" in followup_updates and not st.session_state.district_info:
                _new_pin = followup_updates["pincode"]
                _new_di = get_district_for_pincode(_new_pin) or {}
                if _new_di:
                    followup_updates["district_norm"] = _new_di["district_norm"]
                    followup_updates["state_norm"] = _new_di["state_norm"]
                    st.session_state.district_info = _new_di
                    st.session_state.nfhs_rows = get_nfhs_for_district(
                        _new_di["district_norm"], _new_di["state_norm"]
                    )
                    st.session_state.facilities_list = get_facilities(
                        _new_pin, _new_di["district_norm"], _new_di["state_norm"]
                    )

            # 3 - Merge base_profile + followup_updates -> final_profile
            final_profile = merge_profile(base_profile, followup_updates)
            log_final_profile(final_profile)

            # 4 - Match pathways using final_profile (not base_profile)
            matched = match_pathways(final_profile, pathways)
            log_matched_pathways(matched)
            # Re-rank facilities for the matched pathways (deprioritise dental/eye-only)
            _ranked = rank_facilities_for_pathways(
                st.session_state.facilities_list,
                pathway_ids={pw.get("pathway_id") for pw in matched},
                pincode=final_profile.get("pincode", ""),
                state_norm=st.session_state.district_info.get("state_norm", ""),
            )
            st.session_state.facilities_list = _ranked
            log_facilities_selected(_ranked)
            log_district_context(st.session_state.get("nfhs_lookup_trace") or {})

            # 5 - Generate action plan
            spin_msg = (
                "Generating your support plan with Claude..."
                if CLAUDE_AVAILABLE
                else "Generating your support plan..."
            )
            with st.spinner(spin_msg):
                plan_text, plan_method, action_trace = generate_action_plan_with_trace(
                    final_profile,
                    matched,
                    st.session_state.nfhs_rows,
                    st.session_state.facilities_list,
                    followup_answers=form_answers,
                )
            agent_trace = dict(st.session_state.get("agent_trace") or empty_agent_trace())
            agent_trace["action_plan"] = action_trace
            agent_trace["rules_engine"] = rules_engine_trace()

            # 6 - Persist to SQLite with full lineage
            _d = st.session_state.district_info
            session_id = store.save_session(
                raw_text=st.session_state.original_text,
                profile=final_profile,
                plan_text=plan_text,
                plan_method=plan_method,
                district_norm=_d.get("district_norm", ""),
                state_norm=_d.get("state_norm", ""),
                lineage={
                    "base_profile": base_profile,
                    "followup_answers": form_answers,
                    "followup_updates": followup_updates,
                    "agent_trace": agent_trace,
                    "matched_pathway_ids": [pw.get("pathway_id") for pw in matched],
                    "facilities_count": len(st.session_state.facilities_list),
                },
            )

            # 7 - Commit to session state
            st.session_state.followup_answers = form_answers
            st.session_state.followup_updates = followup_updates
            st.session_state.final_profile = final_profile
            st.session_state.matched_pathways = matched
            st.session_state.action_plan = plan_text
            st.session_state.plan_method = plan_method
            st.session_state.agent_trace = agent_trace
            st.session_state.session_id = session_id
            st.session_state.feedback_submitted = False
            st.session_state.step = 2
            st.rerun()

        if st.button("Back"):
            st.session_state.step = 0
            st.rerun()

    # -- SCREEN 3: Results ----------------------------------------------------
    elif step == 2:
        # Safe-failure guard: final_profile must exist
        if not st.session_state.final_profile:
            st.warning(
                "Please complete the follow-up questions first. "
                "The results screen requires a completed profile."
            )
        if st.button("Back"):
                st.session_state.step = 1
                st.rerun()
        else:
            final_profile = st.session_state.final_profile
            matched = st.session_state.matched_pathways
            plan_text = st.session_state.action_plan
            nfhs_rows = st.session_state.nfhs_rows
            facilities = st.session_state.facilities_list
            district_info = st.session_state.district_info

            pin = final_profile.get("pincode", "?")
            district = district_info.get("district_norm", "")
            state = district_info.get("state_norm", "")
            location_str = f"PIN {pin}" + (f" - {district}, {state}" if district else "")
            st.subheader(f"Results for {location_str}")

            st.info(
                "TrustRoute AI matched support pathways and nearby facility options based on "
                "your scenario and follow-up answers. Trust signals reflect data completeness."
            )

            st.markdown("### Matched Support Pathways")
            if matched:
                for pw in matched:
                    with st.container(border=True):
                        st.markdown(f"**{pw.get('pathway_name', pw.get('pathway_id'))}**")
                        st.write(pw.get("recommended_action", ""))
                        st.write(f"**Why matched:** {pathway_reason(final_profile, pw)}")
                        with st.expander("Technical match rule", expanded=False):
                            st.caption(
                                f"Category: {pw.get('category', '')}  |  "
                                f"Trigger: `{pw.get('trigger_condition', '')}`"
                            )
            else:
                st.info(
                    "No support pathways matched the current profile. "
                    "Please consult a local health worker for personalised guidance."
                )

            st.markdown("---")
            method_label = plan_method_label(st.session_state.plan_method)
            st.subheader(f"Personalized Support Plan  |  {method_label}")
            st.markdown(plan_text)

            if facilities:
                st.markdown("---")
                st.subheader("Nearby Health Facilities")
                st.caption(
                    "Showing up to 5 higher-confidence facilities based on your location, "
                    "travel preference, and pathway relevance. Trust signal reflects data "
                    "completeness — not a guarantee of service quality."
                )
                _trust_scores = load_facility_trust_scores()
                _shortlisted = st.session_state.shortlisted_facilities
                _search_pin = final_profile.get("pincode", "")
                _search_state = district_info.get("state_norm", "")
                _fs_trace: dict = {
                    "trust_scores_loaded": len(_trust_scores),
                    "facilities_selected": len(limited_facilities(facilities)),
                    "matched_to_trust_table": 0,
                    "proxy_fallback": 0,
                    "top_facility_scores": [],
                }

                _signal_colors = {
                    "High": ("#1a6e1a", "#e8f5e8"),
                    "Medium": ("#7a5500", "#fff8e1"),
                    "Limited": ("#4a4a4a", "#f5f5f5"),
                    "Unknown": ("#555555", "#eeeeee"),
                }

                for _fac_idx, f in enumerate(limited_facilities(facilities)):
                    fd = format_facility(f)
                    _trust_row = get_facility_trust_score(f, _trust_scores)
                    _ev = facility_evidence_summary(f, _trust_row)
                    _signal = _ev["trust_info"]["signal"]
                    _score_disp = _ev["trust_info"].get("score_display", "")
                    _score_src = _ev["trust_info"].get("score_source", "")
                    _matched_by = _ev["trust_info"].get("matched_by", "proxy")
                    _sc, _bc = _signal_colors.get(_signal, ("#4a4a4a", "#f5f5f5"))
                    _fac_name = f.get("name", "")
                    _already_saved = _fac_name in _shortlisted
                    _why_shown = facility_why_shown(f, _search_pin, _search_state, _signal)

                    # Build badge text: "Trust signal: High (8.5/10) · proxy"
                    _src_short = "UC" if "Unity Catalog" in _score_src else "proxy"
                    _badge = f"Trust signal: {_signal}"
                    if _score_disp:
                        _badge += f" ({_score_disp})"
                    _badge += f"  ·  {_src_short}"

                    # Scoring trace entry
                    if _trust_row:
                        _fs_trace["matched_to_trust_table"] += 1
                    else:
                        _fs_trace["proxy_fallback"] += 1
                    _fs_trace["top_facility_scores"].append({
                        "rank": _fac_idx + 1,
                        "name": _fac_name,
                        "trust_signal": _signal,
                        "trust_score_display": _score_disp,
                        "score_source": _score_src,
                        "matched_by": _matched_by,
                    })

                    with st.container(border=True):
                        _col_main, _col_btn = st.columns([5, 1])
                        with _col_main:
                            st.markdown(f"**{fd['name']}**")
                            st.markdown(
                                f'<span style="background:{_bc};color:{_sc};border:1px solid {_sc}40;'
                                f'padding:2px 9px;border-radius:10px;font-size:0.72rem;font-weight:600;">'
                                f'{_badge}</span>',
                                unsafe_allow_html=True,
                            )
                        with _col_btn:
                            if _already_saved:
                                st.caption("Saved")
                            else:
                                if st.button(
                                    "Save for follow-up",
                                    key=f"shortlist_{_fac_idx}",
                                    type="secondary",
                                ):
                                    _shortlist_data = dict(f)
                                    _shortlist_data["_trust_signal"] = _signal
                                    _shortlist_data["_trust_score_display"] = _score_disp
                                    _shortlist_data["_score_source"] = _score_src
                                    _shortlist_data["_matched_by"] = _matched_by
                                    store.save_shortlist_item(
                                        st.session_state.get("session_id"),
                                        _fac_name,
                                        _shortlist_data,
                                    )
                                    new_saved = list(st.session_state.shortlisted_facilities)
                                    new_saved.append(_fac_name)
                                    st.session_state.shortlisted_facilities = new_saved
                                    st.rerun()

                        if fd["address"]:
                            st.write(fd["address"])
                        if fd["phone"]:
                            st.write(f"Phone: {fd['phone']}")
                        if fd["email"]:
                            st.write(f"Email: {fd['email']}")
                        if fd["service_tags"]:
                            st.write("Services: " + ", ".join(fd["service_tags"][:3]))
                        st.caption(
                            "Trust signal reflects available evidence and data completeness — "
                            "not a guarantee of service quality. Please call to confirm current services before visiting."
                        )

                        with st.expander("Evidence from trusted facility record"):
                            for _ev_label, _ev_val in _ev["evidence_items"]:
                                st.write(f"**{_ev_label}:** {_ev_val}")
                            st.markdown("---")
                            st.write(f"**Trust signal:** {_ev['trust_info']['signal']}")
                            if _score_disp:
                                st.write(f"**Score:** {_score_disp}")
                            st.write(f"**Score source:** {_score_src or 'proxy'}")
                            st.write(f"**Matched by:** {_matched_by}")
                            st.write(f"**Why shown:** {_why_shown}")
                            st.write(f"**Evidence detail:** {_ev['trust_info']['why']}")
                            st.caption(
                                "Facility data is based on public records and may be incomplete or noisy. "
                                "Please call to confirm current services before visiting."
                            )

                st.session_state.facility_scoring_trace = _fs_trace

            # Shortlist summary (persisted to SQLite)
            _saved_list = st.session_state.shortlisted_facilities
            if _saved_list:
                st.markdown("---")
                st.subheader("Saved for Follow-up")
                st.caption(
                    "These facilities were saved during this session. "
                    "Records are persisted to local state for future reference."
                )
                for _sname in _saved_list:
                    st.write(f"- {_sname}")

            if nfhs_rows:
                st.markdown("---")
                row = nfhs_rows[0]
                d_name = row.get("district_name", "").strip() or district
                match_type = "district match" if len(nfhs_rows) == 1 else "state-level context"
                st.markdown("---")
                st.subheader(f"Relevant District Health Context")
                st.caption(f"{d_name} ({match_type}, NFHS-5)")
                selected_indicators, more_indicators = district_context_rows(final_profile, row)
                cols = st.columns(3)
                for idx, ind in enumerate(selected_indicators):
                    with cols[idx % 3]:
                        st.metric(label=ind["label"], value=ind["value"])
                        if ind["quality"] != "certain":
                            st.caption(f"Data quality: {ind['quality']}")

                with st.expander("View more district indicators"):
                    for ind in more_indicators:
                        st.write(f"**{ind['label']}**: {ind['value']}")
                        if ind["quality"] != "certain":
                            st.caption(f"Data quality: {ind['quality']}")

            st.markdown("---")
            st.subheader("How helpful was this plan?")
            if st.session_state.feedback_submitted:
                st.success("Thanks - your feedback was saved.")
            else:
                with st.form("screen3_feedback"):
                    rating = st.radio(
                        "Choose one:",
                        ["Helpful", "Somewhat helpful", "Not helpful"],
                        horizontal=True,
                    )
                    comment = st.text_area(
                        "What would make this plan more useful?",
                        height=90,
                    )
                    submitted_feedback = st.form_submit_button("Submit feedback")
                if submitted_feedback:
                    store.save_feedback(
                        st.session_state.get("session_id"),
                        rating,
                        comment.strip(),
                    )
                    st.session_state.feedback_submitted = True
                    st.rerun()

            st.markdown("---")
            if st.button("Start a New Query"):
                for key in list(_STATE_DEFAULTS.keys()):
                    v = _STATE_DEFAULTS[key]
                    st.session_state[key] = list(v) if isinstance(v, list) else v
                st.rerun()
# ============================================================================
# TAB 2 - PROGRAM LEADER DASHBOARD
# ============================================================================
with tab2:
    st.subheader("Program Leader Dashboard")
    st.caption("District health trends - pathway demand simulation - facility overview")

    all_nfhs = _load("nfhs_5_district_health_indicators")

    if not all_nfhs:
        st.warning(
            "No NFHS data loaded. "
            "Run `python scripts/export_sample_data.py` to populate sample_data/."
        )
    else:
        district_names = list_nfhs_districts()
        if not district_names:
            st.warning("No district names found in NFHS data.")
        else:
            _recent = store.get_recent_sessions(1)
            _recent_dist = _recent[0].get("district_norm", "") if _recent else ""
            _default_idx = preferred_district_index(district_names, _recent_dist)
            selected_district = st.selectbox("Select district:", district_names, index=_default_idx)
            sel_row = next(
                (r for r in all_nfhs if r.get("district_name", "").strip() == selected_district),
                None,
            )

            if sel_row:
                st.write(f"**{selected_district}** - {sel_row.get('state_ut','').strip()}")

                indicators = get_nfhs_display_rows(sel_row)
                certain = [i for i in indicators if i["quality"] == "certain"]

                if certain:
                    st.markdown("#### Key Health Indicators")
                    metric_cols = st.columns(4)
                    for idx, ind in enumerate(certain[:8]):
                        with metric_cols[idx % 4]:
                            st.metric(ind["label"], ind["value"])
                else:
                    st.info("No numeric indicators available for this district.")

                st.markdown("---")
                st.markdown("#### Pathway Demand - Sample Scenario Simulation")
                st.caption("Based on 3 included demo scenarios (not real population data)")

                scenarios = load_scenarios()
                demand: dict[str, int] = {pw["pathway_id"]: 0 for pw in pathways}
                for sc in scenarios:
                    signals = sc.get("expected_signals", {})
                    for pw in pathways:
                        if _eval_condition(pw.get("trigger_condition", ""), signals):
                            demand[pw["pathway_id"]] += 1

                for pw in pathways:
                    name = pw.get("pathway_name", pw["pathway_id"])
                    count = demand[pw["pathway_id"]]
                    bar = "#" * count + "." * (len(scenarios) - count)
                    st.write(f"**{name}**: {bar} {count}/{len(scenarios)}")

        st.markdown("---")
        _fac_src = "Unity Catalog trusted data" if data_status.get("active_source") == "uc" else "active data source"
        st.markdown(f"#### Facility Coverage ({_fac_src})")
        all_facilities = _load("facilities")
        if all_facilities:
            total = len(all_facilities)
            with_phone = sum(1 for f in all_facilities if f.get("officialPhone"))
            with_coords = sum(
                1 for f in all_facilities
                if f.get("latitude") and str(f.get("latitude")).strip() not in ("NA", "")
            )
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric("Total facilities", total)
            fc2.metric("With phone number", with_phone)
            fc3.metric("With coordinates", with_coords)
        else:
            st.info("No facilities data loaded.")

# ============================================================================
# TAB 3 - DATA TRUST / DEBUG PANEL
# ============================================================================
with tab3:
    st.subheader("Data Trust / Debug Panel")

    # Source file status
    st.markdown("#### Data Source Status")
    source_files = [
        "facilities",
        "india_post_pincode_directory",
        "pincode_district_lookup",
        "nfhs_5_district_health_indicators",
        "support_pathways",
        "sample_scenarios",
    ]
    status_cols = st.columns(3)
    for idx, name in enumerate(source_files):
        rows = _load(name)
        with status_cols[idx % 3]:
            if rows:
                st.success(f"{name}  ({len(rows)} rows)")
            else:
                st.error(f"{name}  MISSING")

    # Optional: facility_trust_scores
    _ts_debug_rows = load_facility_trust_scores()
    _ts_src_label = "uc" if DATA_MODE == "uc" and _ts_debug_rows else ("proxy" if not _ts_debug_rows else "json")
    if _ts_debug_rows:
        st.success(f"facility_trust_scores  ({len(_ts_debug_rows)} rows, {_ts_src_label}) [optional]")
    else:
        st.warning("facility_trust_scores  not loaded — proxy scoring active [optional]")

    source_status = get_data_source_status()
    st.markdown("#### Data Source Runtime")
    st.write(f"**Configured data mode:** `{source_status.get('configured_mode', DATA_MODE)}`")
    st.write(f"**Active source:** `{source_status.get('active_source', 'unknown')}`")
    st.write(f"**Catalog / schema:** `{source_status.get('catalog', UC_CATALOG)}`.`{source_status.get('schema', UC_SCHEMA)}`")
    if source_status.get("http_path_redacted"):
        st.write(f"**SQL Warehouse HTTP path:** `{source_status['http_path_redacted']}`")
    if source_status.get("fallback_reason"):
        st.warning(source_status["fallback_reason"])

    table_status = source_status.get("tables", {})
    for table_name in [
        "facilities",
        "india_post_pincode_directory",
        "pincode_district_lookup",
        "nfhs_5_district_health_indicators",
        "support_pathways",
    ]:
        status = table_status.get(table_name, {})
        source = status.get("source", "not loaded")
        count = status.get("row_count", 0)
        st.write(f"`{table_name}`: {count} row(s), source `{source}`")
        if status.get("fallback_reason"):
            st.caption(f"Fallback reason: {status['fallback_reason']}")
    # Optional table
    _ts_rows_count = len(load_facility_trust_scores())
    _ts_src = "uc" if DATA_MODE == "uc" and _ts_rows_count > 0 else ("unavailable" if not _ts_rows_count else "json")
    st.write(f"`facility_trust_scores` [optional]: {_ts_rows_count} row(s), source `{_ts_src}`")

    # AI mode
    st.markdown("---")
    st.markdown("#### AI Configuration")
    if CLAUDE_AVAILABLE:
        st.success(f"Claude AI active - model: `{CLAUDE_MODEL}`")
    else:
        st.warning(
            "Deterministic mode - `ANTHROPIC_API_KEY` not set. "
            "Copy `.env.example` to `.env` and add your key to enable Claude."
        )

    st.markdown("---")
    st.markdown("#### Trusted Data Sources")
    _TRUSTED_TABLE_PURPOSES = {
        "facilities": "Health facility directory — name, address, phone, specialties",
        "pincode_district_lookup": "PIN code to district/state mapping (primary, with coordinates)",
        "india_post_pincode_directory": "India Post PIN directory — fallback district lookup",
        "nfhs_5_district_health_indicators": "NFHS-5 district health indicators — maternal, child, immunization, nutrition",
        "support_pathways": "Support pathway rules — trigger conditions, recommended actions",
        "facility_trust_scores": "Optional — facility trust/evidence scores for enriched referral cards",
    }
    _active_src = source_status.get("active_source", "json")
    _src_label = "Unity Catalog trusted tables" if _active_src == "uc" else "Local sample JSON reference"
    st.caption(f"Source: {_src_label}")
    for _tbl, _purpose in _TRUSTED_TABLE_PURPOSES.items():
        if _tbl == "facility_trust_scores":
            _ts_n = len(load_facility_trust_scores())
            _ts_s = "uc" if DATA_MODE == "uc" and _ts_n > 0 else ("unavailable" if not _ts_n else "json")
            st.write(f"**`{_tbl}`** ({_ts_n} rows, {_ts_s}) [optional] — {_purpose}")
        else:
            _tbl_status = source_status.get("tables", {}).get(_tbl, {})
            _rows = _tbl_status.get("row_count", 0)
            _src = _tbl_status.get("source", "not loaded")
            st.write(f"**`{_tbl}`** ({_rows} rows, {_src}) — {_purpose}")

    st.markdown("---")
    st.markdown("#### NFHS District Lookup Trace (current session)")
    _nfhs_trace = st.session_state.get("nfhs_lookup_trace") or {}
    if _nfhs_trace:
        st.write(f"**Requested:** {_nfhs_trace.get('requested_district')} / {_nfhs_trace.get('requested_state')}")
        st.write(f"**Match type:** `{_nfhs_trace.get('match_type')}`")
        st.write(f"**Matched district:** {_nfhs_trace.get('matched_district')} / {_nfhs_trace.get('matched_state')}")
        st.write(f"**Alias candidates tried:** {_nfhs_trace.get('alias_candidates_tried')}")
        st.write(f"**State rows available:** {_nfhs_trace.get('state_row_count', 0)} | **Rows returned:** {_nfhs_trace.get('candidate_row_count', 0)}")
    else:
        st.info("No NFHS lookup trace yet. Complete a Family Navigator query with a valid PIN code.")

    st.markdown("---")
    st.markdown("#### Claude Agent Trace")
    agent_trace = st.session_state.get("agent_trace") or empty_agent_trace()
    trace_rows = [
        ("Profile extraction", "profile_extraction", False),
        ("Follow-up questions", "followup_questions", False),
        ("Action plan", "action_plan", False),
        ("Rules engine", "rules_engine", True),
    ]
    for label, key, is_rules_engine in trace_rows:
        step_trace = agent_trace.get(key, {})
        model = step_trace.get("model") or "None"
        st.write(
            f"**{label}:** {step_display_label(step_trace, rules_engine=is_rules_engine)} "
            f" | Model: `{model}`"
        )
        if step_trace.get("fallback_used") and step_trace.get("fallback_reason"):
            st.caption(f"Fallback reason: {step_trace['fallback_reason']}")

    # Facility Scoring Trace
    st.markdown("---")
    st.markdown("#### Facility Scoring Trace")
    _fst = st.session_state.get("facility_scoring_trace") or {}
    if _fst:
        _fst_col1, _fst_col2, _fst_col3 = st.columns(3)
        _fst_col1.metric("facility_trust_scores rows", _fst.get("trust_scores_loaded", 0))
        _fst_col2.metric("Matched to trust table", _fst.get("matched_to_trust_table", 0))
        _fst_col3.metric("Proxy fallback", _fst.get("proxy_fallback", 0))
        st.caption(
            f"Selected facilities: {_fst.get('facilities_selected', 0)}  ·  "
            "Ranking formula: 40% service/pathway relevance, 25% location, 25% trust/evidence, 10% contact completeness"
        )
        _top_scores = _fst.get("top_facility_scores", [])
        if _top_scores:
            st.markdown("**Top facility scores:**")
            for _fs_item in _top_scores:
                _score_str = f" · score={_fs_item['trust_score_display']}" if _fs_item["trust_score_display"] else ""
                st.write(
                    f"**{_fs_item['rank']}.** {_fs_item['name']}"
                    f" · trust_signal={_fs_item['trust_signal']}"
                    f"{_score_str}"
                    f" · source={_fs_item['score_source'] or 'proxy'}"
                    f" · matched_by={_fs_item['matched_by']}"
                )
    else:
        st.info("No facility scoring trace yet. Complete a Family Navigator query to see scoring details.")

    # Profile lineage trace (current session)
    st.markdown("---")
    st.markdown("#### Profile Lineage Trace (current session)")
    if st.session_state.get("base_profile"):
        with st.expander("1. Original scenario (Screen 1)", expanded=False):
            st.write(st.session_state.get("original_text") or "-")

        with st.expander("2. Base profile extracted from Screen 1", expanded=False):
            st.write("**Needs detected:**")
            st.write(", ".join(st.session_state.base_profile.get("needs") or []) or "-")
            st.json(st.session_state.base_profile)

        _fq = st.session_state.get("followup_questions") or []
        if _fq:
            with st.expander("3. Generated follow-up questions", expanded=False):
                for _q in _fq:
                    st.write(f"**{_q.get('id', 'question')}:** {_q.get('question', '')}")

        _fa = st.session_state.get("followup_answers") or {}
        if _fa:
            with st.expander("4. Follow-up answers (Screen 2)", expanded=False):
                for _qid, _ans in _fa.items():
                    st.write(f"**{_qid}:** {_ans or '-'}")

        _fu = st.session_state.get("followup_updates") or {}
        if _fu:
            with st.expander("5. Follow-up updates (parsed from answers)", expanded=False):
                st.json(_fu)

        _fp = st.session_state.get("final_profile")
        if _fp:
            with st.expander("6. Final merged profile used for Screen 3", expanded=False):
                st.json(_fp)

        _mp = st.session_state.get("matched_pathways") or []
        if _mp:
            with st.expander("7. Matched pathways (generated from final_profile)", expanded=False):
                for _pw in _mp:
                    st.write(
                        f" **{_pw.get('pathway_name', _pw.get('pathway_id'))}**  "
                        f"- trigger: `{_pw.get('trigger_condition', '')}`"
                    )
    else:
        st.info(
            "No session data yet. Complete a Family Navigator query to see the profile lineage."
        )

    # District matching trace
    st.markdown("---")
    st.markdown("#### District Matching Trace")
    test_pin = st.text_input("Enter a pincode to trace:", value="560001", key="debug_pin")
    if test_pin.strip():
        di = get_district_for_pincode(test_pin.strip())
        if di:
            alias = get_district_alias(di["district_norm"])
            st.write(
                f"Lookup -> `district_norm={di['district_norm']}`, "
                f"`state_norm={di['state_norm']}`, "
                f"lat={di['lat']}, lon={di['lon']}"
            )
            st.write(f"NFHS alias: `{di['district_norm']}` -> `{alias}`")
            nfhs = get_nfhs_for_district(di["district_norm"], di["state_norm"])
            if nfhs:
                match_label = "district match" if _norm(nfhs[0].get("district_name")) == alias else "state fallback"
                st.success(
                    f"NFHS: {len(nfhs)} row(s) found ({match_label}) - "
                    f"district_name=`{nfhs[0].get('district_name','').strip()}`"
                )
            else:
                st.error("No NFHS rows found for this pincode's district/state.")
        else:
            st.error(f"Pincode `{test_pin.strip()}` not found in local sample data.")

    # Recent sessions
    st.markdown("---")
    st.markdown("#### Recent Sessions (SQLite)")
    sessions = store.get_recent_sessions(10)
    if sessions:
        for s in sessions:
            pin_info = f"{s.get('district_norm','')} / {s.get('state_norm','')}"
            st.write(
                f"`{s['id'][:8]}...`  {s['created_at']}  "
                f"- {pin_info}  "
                f"- plan: **{s.get('plan_method','?')}**"
            )
    else:
        st.write("No sessions recorded yet. Complete a Family Navigator query to create one.")

    # Raw data preview
    st.markdown("---")
    st.markdown("#### Trusted Data Preview")
    preview_choice = st.selectbox("File to preview:", source_files, key="debug_file")
    preview_rows = _load(preview_choice)
    if preview_rows:
        import pandas as pd

        df = pd.DataFrame(preview_rows[:10])
        st.dataframe(df, width="stretch")
        if len(preview_rows) > 10:
            st.caption(f"Showing 10 of {len(preview_rows)} rows.")
    else:
        st.warning(f"No data for `{preview_choice}`.")

