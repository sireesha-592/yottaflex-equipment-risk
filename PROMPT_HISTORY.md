# AI Prompt History

The assessment requests prompts submitted to AI tools. Keep this file accurate and update it with every prompt used for this project. The entries below describe the initial project-planning request in this ChatGPT conversation; they are not a substitute for recording any further prompts.

## ChatGPT — initial planning
**Prompt summary:** Asked for help understanding the 72-hour code challenge, then requested a complete project in one day. Shared the problem requirements for synthetic industrial equipment data generation, risk identification, validation, reproducibility, and public GitHub submission.

## Additional prompts
Add the exact prompts you use for further AI assistance here, including date/time and tool name. AI responses are optional per the candidate FAQ, but prompt history is required. Do not claim prompts were used if they were not.

## Additional prompt record — 2026-10-27

**User prompt:** “okay cheyi” (continue the agreed work: improve risk scoring, verify data requirements, prepare a clean GitHub submission, and run final checks).

**AI assistance summary:** Reviewed the existing risk-scoring and evaluation implementation; revised the explainable heuristic to use lower, documented thresholds for temperature/vibration/current elevation, time-ordered upward drift, and variability as a supporting signal; excluded invalid sensor/range readings, zero-imputed readings, and shutdown/maintenance readings from risk evidence; added regression tests; updated README with scoring assumptions and a measured starter evaluation. The implementation was tested locally with pytest and a deterministic starter dataset. The candidate must personally review the changes, understand the trade-offs, and rerun the commands before submission.
