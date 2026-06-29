-- Phase 1 refinement — per-education-level student profiling.
--
-- The student onboarding form now branches on `education_level` (high_school /
-- undergraduate / postgraduate / other), and each branch asks for different
-- scalar fields (degree, current_year, specialization, knowledge_level, …).
-- Rather than add ~10 sparse columns, level-specific scalars live in one
-- `details` jsonb map. The array columns (subjects/target_exams/
-- preferred_colleges) and `stream` are reused per branch for list/grade inputs.
--
-- Keys used in `details` (all optional, depend on education_level):
--   undergraduate : degree, current_year, future_pathway
--   postgraduate  : specialization, current_phase, target_industry
--   other         : current_focus, field_of_interest, knowledge_level, ultimate_goal
-- (high_school uses only the existing columns.)

alter table profiles_student
  add column if not exists details jsonb not null default '{}';
