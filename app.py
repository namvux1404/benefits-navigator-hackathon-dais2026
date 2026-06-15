"""BENEFITBRIDGE AI — Gate A local-only Streamlit app.

Runs entirely on local sample JSON files + SQLite.
No live Databricks / Unity Catalog / Lakebase connections in this gate.
Claude API is used if ANTHROPIC_API_KEY is set; falls back to deterministic otherwise.

Session flow:
  Screen 1 (step=0) — original scenario input
  Screen 2 (step=1) — follow-up questions + profile card + "Generate support plan"
  Screen 3 (step=2) — matched pathways, action plan, NFHS indicators, facilities
"""
from __future__ import annotations

import json

import streamlit as st

from src.config import CLAUDE_AVAILABLE, CLAUDE_MODEL, DATA_MODE, SAMPLE_DATA_DIR, STATE_STORE_MODE
from src.data_loader import (
    _load,
    _norm,
    get_district_alias,
    get_district_for_pincode,
    get_facilities,
    get_nfhs_for_district,
    list_nfhs_districts,
    load_pathways,
    load_scenarios,
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
    data_source_label,
    district_context_rows,
    format_facility,
    get_nfhs_display_rows,
    limited_facilities,
    next_steps_for_profile,
    pathway_reason,
    plan_method_label,
    preferred_district_index,
    state_store_label,
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BenefitBridge AI",
    page_icon="🌉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session state init ───────────────────────────────────────────────────────
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
    "session_id": None,
    "feedback_submitted": False,
}
for _k, _v in _STATE_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

store = StateStore()
pathways = load_pathways()

# ── Header ───────────────────────────────────────────────────────────────────
st.title("🌉 BenefitBridge AI")
_badge = (
    f"{data_source_label(DATA_MODE)}  ·  "
    f"{state_store_label(STATE_STORE_MODE)}  ·  "
    f"{ai_mode_label(CLAUDE_AVAILABLE, CLAUDE_MODEL)}"
)
st.caption(_badge)

tab1, tab2, tab3 = st.tabs(
    ["👪 Family Navigator", "📊 Program Leader Dashboard", "🔍 Data Trust / Debug"]
)

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — FAMILY NAVIGATOR
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    step = st.session_state.step

    # ── SCREEN 1: Scenario input ────────────────────────────────────────────
    if step == 0:
        st.subheader("Tell us about your family")

        scenarios = load_scenarios()
        if scenarios:
            st.write("**Quick-start demo scenarios:**")
            demo_cols = st.columns(min(len(scenarios), 3))
            for i, sc in enumerate(scenarios):
                if demo_cols[i % 3].button(sc["title"][:55], key=f"demo_{i}"):
                    st.session_state.original_text = sc["scenario_text"]
                    st.rerun()

        st.markdown("---")
        raw = st.text_area(
            "Describe your family's situation and health needs:",
            value=st.session_state.original_text,
            height=130,
            placeholder=(
                "Example: I live in pincode 560001. I am pregnant and have a 3-year-old child. "
                "I need help with nutrition and finding a nearby health facility."
            ),
        )

        if st.button("Analyse My Family Profile", type="primary", disabled=not raw.strip()):
            spinner_msg = (
                "Analysing your situation with Claude…"
                if CLAUDE_AVAILABLE
                else "Extracting profile…"
            )
            with st.spinner(spinner_msg):
                base_profile, profile_trace = extract_profile_with_trace(raw.strip())

                pincode = base_profile.get("pincode") or ""
                district_info: dict = {}
                nfhs_rows: list[dict] = []
                facilities: list[dict] = []

                if pincode:
                    district_info = get_district_for_pincode(pincode) or {}
                    if district_info:
                        base_profile["district_norm"] = district_info["district_norm"]
                        base_profile["state_norm"] = district_info["state_norm"]
                        nfhs_rows = get_nfhs_for_district(
                            district_info["district_norm"], district_info["state_norm"]
                        )
                        facilities = get_facilities(
                            pincode, district_info["district_norm"], district_info["state_norm"]
                        )

                followup_qs, followup_trace = generate_followup_questions_with_trace(
                    base_profile, raw.strip()
                )

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
            st.session_state.facilities_list = facilities
            st.session_state.followup_questions = followup_qs
            st.session_state.followup_answers = {}
            st.session_state.followup_updates = {}
            st.session_state.final_profile = None
            st.session_state.step = 1
            st.rerun()

    # ── SCREEN 2: Follow-up questions + profile card ─────────────────────────
    elif step == 1:
        base_profile: dict = st.session_state.base_profile
        questions: list[dict] = st.session_state.followup_questions

        st.subheader("A few quick questions to personalise your plan")
        st.caption(
            "Answer 2–3 short questions so we can match the right support pathways for your family."
        )

        with st.expander("Your original description", expanded=False):
            st.write(st.session_state.original_text)

        # ── Follow-up form with profile card inside ──────────────────────────
        form_answers: dict[str, str] = {}
        with st.form("followup_form"):
            for q in questions:
                form_answers[q["id"]] = st.text_input(
                    q["question"],
                    key=f"fq_{q['id']}",
                    placeholder=q.get("placeholder", "Type your answer here…"),
                )

            # ── Compact profile card (base_profile summary) ──────────────────
            st.markdown("---")
            st.markdown("**Profile used for matching**")

            _di = st.session_state.district_info
            _pin = base_profile.get("pincode") or "—"
            _dist = _di.get("district_norm", "") or "—"
            _state_name = _di.get("state_norm", "")
            _loc = f"{_dist}, {_state_name}".strip(", ") or "—"

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
            _needs_str = ", ".join(_needs) if _needs else "—"

            _ins_parts = []
            if base_profile.get("uninsured") is True:
                _ins_parts.append("No insurance (extracted)")
            if base_profile.get("low_income"):
                _ins_parts.append("Low-cost need (extracted)")
            _ins_str = " · ".join(_ins_parts) if _ins_parts else "Answer above to complete"

            _travel_km = base_profile.get("travel_km")
            _travel_str = f"Up to {_travel_km} km" if _travel_km else "Answer above to complete"

            _urgency = base_profile.get("urgency", "")
            _urgency_str = _urgency.capitalize() if _urgency else "Answer above to complete"

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
                "Your answers above complete this profile before matching support pathways."
            )

            submitted = st.form_submit_button("Generate support plan", type="primary")

        if submitted:
            # 1 — Parse free-text answers → structured updates
            followup_updates = parse_followup_answers(questions, form_answers)

            # 2 — If pincode newly provided, look up district/NFHS/facilities
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

            # 3 — Merge base_profile + followup_updates → final_profile
            final_profile = merge_profile(base_profile, followup_updates)

            # 4 — Match pathways using final_profile (not base_profile)
            matched = match_pathways(final_profile, pathways)

            # 5 — Generate action plan
            spin_msg = (
                "Generating your support plan with Claude…"
                if CLAUDE_AVAILABLE
                else "Generating your support plan…"
            )
            with st.spinner(spin_msg):
                plan_text, plan_method, action_trace = generate_action_plan_with_trace(
                    final_profile,
                    matched,
                    st.session_state.nfhs_rows,
                    st.session_state.facilities_list,
                )
            agent_trace = dict(st.session_state.get("agent_trace") or empty_agent_trace())
            agent_trace["action_plan"] = action_trace
            agent_trace["rules_engine"] = rules_engine_trace()

            # 6 — Persist to SQLite with full lineage
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

            # 7 — Commit to session state
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

        if st.button("← Back"):
            st.session_state.step = 0
            st.rerun()

    # ── SCREEN 3: Results ────────────────────────────────────────────────────
    elif step == 2:
        # Safe-failure guard: final_profile must exist
        if not st.session_state.final_profile:
            st.warning(
                "Please complete the follow-up questions first. "
                "The results screen requires a completed profile."
            )
            if st.button("Back to questions"):
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
                "Based on your original scenario and follow-up answers, "
                "the app matched these support pathways."
            )

            st.markdown("### Matched Support Pathways")
            if matched:
                for pw in matched:
                    with st.container(border=True):
                        st.markdown(f"**{pw.get('pathway_name', pw.get('pathway_id'))}**")
                        st.write(pw.get("recommended_action", ""))
                        st.write(f"**Reason:** {pathway_reason(final_profile, pw)}")
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
            st.subheader(f"Personalized Action Plan  |  {method_label}")
            st.markdown(plan_text)

            st.markdown("---")
            st.subheader("Next Steps")
            for step_text in next_steps_for_profile(final_profile):
                st.write(f"- {step_text}")

            if facilities:
                st.markdown("---")
                st.subheader("Nearby Health Facilities")
                st.caption("Showing up to 5 facilities based on your location and travel preference.")
                for f in limited_facilities(facilities):
                    fd = format_facility(f)
                    with st.container(border=True):
                        st.markdown(f"**{fd['name']}**")
                        if fd["address"]:
                            st.write(fd["address"])
                        if fd["phone"]:
                            st.write(f"Phone: {fd['phone']}")
                        if fd["email"]:
                            st.write(f"Email: {fd['email']}")
                        if fd["service_tags"]:
                            st.write("Services: " + ", ".join(fd["service_tags"][:3]))
                        city_state = ", ".join(
                            x for x in [
                                f.get("address_city", ""),
                                f.get("address_stateOrRegion", ""),
                            ] if x
                        )
                        if city_state:
                            st.caption(city_state)
                        with st.expander("View data details"):
                            st.caption("Sample facility data. Verify availability before visiting.")
                            if f.get("source"):
                                st.write(f"Source: {f.get('source')}")
                            if f.get("source_content_id"):
                                st.write(f"Source content ID: {f.get('source_content_id')}")
                            if fd["lat"] and fd["lon"]:
                                st.write(f"Coordinates: {fd['lat']:.4f}, {fd['lon']:.4f}")

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
                st.success("Thanks — your feedback was saved.")
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
                    st.session_state[key] = _STATE_DEFAULTS[key]
                st.rerun()
# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — PROGRAM LEADER DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Program Leader Dashboard")
    st.caption("District health trends · pathway demand simulation · facility overview")

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
                st.write(f"**{selected_district}** — {sel_row.get('state_ut','').strip()}")

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
                st.markdown("#### Pathway Demand — Sample Scenario Simulation")
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
                    bar = "█" * count + "░" * (len(scenarios) - count)
                    st.write(f"**{name}**: {bar} {count}/{len(scenarios)}")

        st.markdown("---")
        st.markdown("#### Facility Coverage (sample_data)")
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

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — DATA TRUST / DEBUG PANEL
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Data Trust / Debug Panel")

    # Source file status
    st.markdown("#### Sample Data Sources")
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

    # AI mode
    st.markdown("---")
    st.markdown("#### AI Configuration")
    if CLAUDE_AVAILABLE:
        st.success(f"Claude AI active — model: `{CLAUDE_MODEL}`")
    else:
        st.warning(
            "Deterministic mode — `ANTHROPIC_API_KEY` not set. "
            "Copy `.env.example` to `.env` and add your key to enable Claude."
        )

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

    # Profile lineage trace (current session)
    st.markdown("---")
    st.markdown("#### Profile Lineage Trace (current session)")
    if st.session_state.get("base_profile"):
        with st.expander("1. Original scenario (Screen 1)", expanded=False):
            st.write(st.session_state.get("original_text") or "—")

        with st.expander("2. Base profile extracted from Screen 1", expanded=False):
            st.write("**Needs detected:**")
            st.write(", ".join(st.session_state.base_profile.get("needs") or []) or "—")
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
                    st.write(f"**{_qid}:** {_ans or '—'}")

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
                        f"✅ **{_pw.get('pathway_name', _pw.get('pathway_id'))}**  "
                        f"— trigger: `{_pw.get('trigger_condition', '')}`"
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
                f"Lookup → `district_norm={di['district_norm']}`, "
                f"`state_norm={di['state_norm']}`, "
                f"lat={di['lat']}, lon={di['lon']}"
            )
            st.write(f"NFHS alias: `{di['district_norm']}` → `{alias}`")
            nfhs = get_nfhs_for_district(di["district_norm"], di["state_norm"])
            if nfhs:
                match_label = "district match" if _norm(nfhs[0].get("district_name")) == alias else "state fallback"
                st.success(
                    f"NFHS: {len(nfhs)} row(s) found ({match_label}) — "
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
                f"`{s['id'][:8]}…`  {s['created_at']}  "
                f"— {pin_info}  "
                f"— plan: **{s.get('plan_method','?')}**"
            )
    else:
        st.write("No sessions recorded yet. Complete a Family Navigator query to create one.")

    # Raw data preview
    st.markdown("---")
    st.markdown("#### Sample Data Preview")
    preview_choice = st.selectbox("File to preview:", source_files, key="debug_file")
    preview_rows = _load(preview_choice)
    if preview_rows:
        import pandas as pd

        df = pd.DataFrame(preview_rows[:10])
        st.dataframe(df, use_container_width=True)
        if len(preview_rows) > 10:
            st.caption(f"Showing 10 of {len(preview_rows)} rows.")
    else:
        st.warning(f"No data for `{preview_choice}`.")
