-- ============================================================================
-- Master Prompters 2.0: Gemini 3.6 Flash cost lookup
-- ADDITIVE. Does not modify registrations / events / checkins / table schema.
-- Seeds pc_evaluation_cost_lookup so admin cost totals match Python fallbacks
-- in backend/app/services/eval_cost.py (USD per 1K tokens).
-- ============================================================================

insert into public.pc_evaluation_cost_lookup (model, input_price, output_price, thinking_price, note)
values (
  'gemini-3.6-flash',
  0.0015,
  0.0075,
  0.0075,
  'Gemini 3.6 Flash (USD per 1K tokens). Thinking billed at output rate.'
)
on conflict (model) do update set
  input_price = excluded.input_price,
  output_price = excluded.output_price,
  thinking_price = excluded.thinking_price,
  note = excluded.note,
  updated_at = now();
