# Product Spec — Student Journey

## Vision
A personalized learning companion. The learner tells us who they are and what
they want; the system uses AI + web search to assemble study material, generate
practice (quizzes, mock tests), prepare them for interviews, and keep them
engaged through email and progress tracking. Our own courses & certifications
plug into the same journey.

---

## The complete user journey (end to end)

### 1. Account
- Landing → Sign up / Log in (email+password or OTP; OAuth optional later).
- Email verification.

### 2. Who are you? (user type branch)
The single most important fork. User picks **Working Professional** or **Student**.

### 3. Profiling wizard (branches by type)

**Working Professional**
- Years of experience
- Current / last role and company
- Industry / domain
- Key skills (multi-select + free text)
- Highest qualification
- Goal: upskill · career switch · certification · interview prep
- Target role / target domain

**Student**
- Education level: Class 10 · Class 12 · Undergraduate · Postgraduate
- Stream: Science (PCM / PCB) · Commerce · Arts / Humanities
- Subjects of interest
- Target exams: JEE · NEET · CUET · CAT · GATE · UPSC · others
- Preferred colleges
- Career interest

### 4. Common preferences (both types)
- Topics they want to learn / improve
- Learning goal / target outcome
- Time available per day / week
- Preferred test cadence: daily · weekly · both
- Notification (email) preferences

### 5. Course enrollment (optional, any time)
- Browse catalog of our courses & certifications.
- Enroll → course is linked into the journey (its syllabus seeds study material,
  quizzes, reminders, and certification-prep emails).

### 6. Dashboard / Home
- AI-curated recommended study material.
- Today's / this week's test.
- Course progress (if enrolled).
- Streak, scores, strengths/weaknesses snapshot.

### 7. Study material flow (AI + web search)
1. Build a search query from the learner's profile + preferences (+ enrolled course syllabus).
2. Web search via provider abstraction (Tavily primary → DuckDuckGo fallback).
3. LLM curates: dedupes, ranks, summarizes, tags by topic/difficulty, **cites sources**.
4. Present as a reading list (summary + link + save-to-library).
5. Saved material is chunked + embedded into the vector store (RAG) so quizzes
   and a future "ask about this material" chat can draw from it.

### 8. Quiz / MCQ engine
- User opts into daily / weekly test (or generates on demand).
- LLM generates MCQs from chosen topics / saved material at a chosen difficulty,
  returned as **validated structured output** (question, 4 options, answer, explanation, topic, difficulty).
- Timed test-taking UI → auto-scoring → per-question explanations → saved to history.
- Feeds progress analytics (per-topic accuracy, trend).

### 9. Email / notification flow
- Welcome & verification.
- Study digest (curated material on cadence).
- Daily / weekly test reminders.
- Results & performance summary.
- Course nudges; certification deadline reminders.

### 10. Mock test flow (formal)
- Scheduled or on-demand full-length mock; larger question set; sectional; timed.
- Detailed report: section scores, percentile, time-per-question, weak areas, next-step material.

### 11. Mock interview flow — **SEPARATE SUBSYSTEM**
Why separate from mock tests:
- **Stateful & multi-turn**: a real dialogue with adaptive follow-up questions.
- **Qualitative evaluation**: scored on a rubric (communication, technical depth,
  problem-solving, structure/clarity), not a right/wrong key.
- **Different data model**: interview sessions, turns, transcripts, rubric scores.
- **Different agents**: an *interviewer agent* (asks/adapts) + an *evaluator agent* (scores/feedback).
- **Latency-sensitive / possibly voice**: optional STT (speech-in) + TTS (speech-out).

Flow:
1. Pick a target role or paste a job description.
2. Interviewer agent runs an adaptive multi-turn interview (text first; voice later).
3. Evaluator agent produces a rubric score + detailed written feedback + an improvement plan.
4. Report saved; links back to study material for weak areas.

### 12. Analytics & progression
- Skill graph / mastery per topic.
- Strengths & weaknesses → recommended next material.
- Streaks, badges, leaderboard (gamification).

---

## Personas (quick)
- **Aanya, Class 12 Science** — wants JEE prep material + daily MCQs + college guidance.
- **Rahul, 3-yr backend dev** — wants a career switch to data; needs upskilling material,
  weekly mocks, and mock interviews against real JDs.
- **Meera, enrolled in our PM certification** — wants course-aligned study + reminders + cert exam mocks.

## Out of scope for v1
Courses/enrollment UI, email engine, mock test (formal), mock interview, gamification.
(All planned — see `ROADMAP.md`.)
