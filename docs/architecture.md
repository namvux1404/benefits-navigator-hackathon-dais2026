1. FAMILY / CAREGIVER / FIELD WORKER
   |
   | Natural language need:
   | “I live in pincode 560001. I am pregnant and have a 3-year-old child.
   |  I need help with nutrition, vaccination, and finding a nearby facility.”
   v

2. DATABRICKS APP — STREAMLIT UI
    - Family Navigator
    - Program Leader Dashboard
    - Data Trust / Debug Panel
    - Shows data source badge:
      Local sample JSON / Unity Catalog trusted tables
    - Shows state badge:
      SQLite fallback / Lakebase
      |
      v

3. CLAUDE AGENT
    - Understands natural language
    - Extracts structured profile
    - Asks intelligent follow-up questions
    - Generates grounded action plan
    - Uses deterministic fallback if API key unavailable
      |
      v

4. FOLLOW-UP QUESTION LOOP
    - Missing pincode?
    - Pregnancy / recently delivered?
    - Child age?
    - Insurance status?
    - Urgent vs routine?
    - Travel distance for facility?
      |
      v

5. RULES ENGINE — EXPLAINABLE SUPPORT MATCHING
    - Matches support pathways
    - Uses deterministic rules
    - No fake eligibility claims
    - No unsupported program invention
    - Ranks relevant support paths:
      Maternal Health
      Child Nutrition
      Immunization
      Health Insurance Awareness
      Household Health Risk
      Women Preventive Screening
      |
      v

6. TRUSTED DATA — UNITY CATALOG / DELTA
   Catalog: benefits_navigator
   Schema: trusted

   Tables:
    - facilities
    - india_post_pincode_directory
    - pincode_district_lookup
    - nfhs_5_district_health_indicators
    - support_pathways

   Purpose:
    - Facility directory
    - PIN-to-district resolution
    - District health indicators
    - Support pathway rules
    - Data-quality caveats
      |
      v

7. DATABRICKS SQL WAREHOUSE
    - Secure SQL access
    - Reads Unity Catalog trusted data
    - Powers local Gate B and deployed app data access
      |
      v

8. LAKEBASE POSTGRES — APPLICATION STATE STORE
   Stores:
    - family_intake_events
    - pathway_matches
    - facility_recommendations
    - action_plans
    - user_feedback

   Purpose:
    - Persistent app memory
    - Transactional state
    - Feedback capture
    - Program analytics foundation
      |
      v

9. PROGRAM LEADER DASHBOARD
    - Pathway demand
    - District health trends
    - Facility coverage
    - Missing contact data
    - Recent family needs
    - Need vs access gaps
      |
      v

10. GENIE / NATURAL LANGUAGE ANALYTICS
    Program leaders ask:
- Which districts show high child nutrition risk?
- Which support pathways are most requested?
- Which facilities are missing phone numbers?
- Where do we have high need but low facility coverage?
  |
  v

11. SOCIAL IMPACT INSIGHTS
- Family-level action
- Field-worker consistency
- Program-leader visibility
- Better outreach decisions
- Trusted data-driven planning