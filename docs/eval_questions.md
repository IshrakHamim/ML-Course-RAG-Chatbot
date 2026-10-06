# Evaluation questions for tuning `RAG_MIN_SCORE`

Use these after ingesting `sample_data/` to pick a threshold that separates in-scope from
out-of-scope questions:

```bash
cd backend
python -m app.cli ingest ../sample_data
python -m app.cli search "What is the late submission policy?"
```

`search` prints the top chunk scores (`score = 1 - cosine distance`). Write the **top score**
for each question in the tables below. Then set `RAG_MIN_SCORE` in `.env` roughly halfway
between the **lowest in-scope** score and the **highest out-of-scope** score.

- If the threshold is too high, real questions get "not found".
- If it is too low, off-topic questions are answered from unrelated chunks. The system prompt
  still makes the model refuse, but the reply costs a chat call.

## In scope (should be answered, with a source)

| # | Question | Expected source | Top score |
|---|----------|-----------------|-----------|
| 1 | What is the late submission policy for lab assignments? | handbook, p. 3 | |
| 2 | When are Dr. Okonkwo-Lindqvist's office hours? | handbook, p. 1 | |
| 3 | How much does the final project count towards the grade? | handbook, p. 2 | |
| 4 | How many GPU hours does each student get on the Orca cluster? | handbook, p. 5 | |
| 5 | What are the library opening hours during exam weeks? | student_services | |
| 6 | What does RAG stand for and what problem does it solve? | Wikipedia URL | |

## Out of scope (should get the polite "not found" fallback)

| # | Question | Top score |
|---|----------|-----------|
| 1 | What is the capital of Australia? | |
| 2 | Write a poem about cats. | |
| 3 | Who won the 2018 FIFA World Cup? | |
| 4 | How do I bake sourdough bread? | |
| 5 | What is the boiling point of nitrogen? | |

## Follow-up (conversation memory)

1. "What is the late submission policy?" then "And can I use grace days for the final project?"
2. "Who teaches the course?" then "When are her office hours?"
