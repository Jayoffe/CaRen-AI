# AI improvement report, 2026-11-07

**Result:** on two blind question sets with fleets the AI had never seen, accuracy rose from 79.74% to 96.93% and from 83.49% to 97.77%. The 95% goal was met on these author-written sets, but not yet shown on real customers. Two of the secondary targets were not fully met (section 9).

Nothing is committed or deployed. Restart the Django service to use the changes.

## 1. Existing architecture and weaknesses

Flow: Front-End -> LavaLust `ChatController` -> `automotive_ai_service` -> plan -> Back-End `ChatRetrieval` runs read-only tools for the signed-in user -> grounded answer.

| Stage | File | Finding |
|---|---|---|
| Normalising text | `ai_api/language.py` | The typo corrector changed correct words, and normalising removed meaning (tense) |
| Choosing intent and records | `ai_api/planner.py` | All rules; no trained model is involved. Rules were too keyword-driven and their order let one word override the question |
| Routing, small talk | `ai_api/assistant.py` | Fillers such as "can i ask" were not removed; acknowledgements fell through to the knowledge search |
| Composing answers | `ai_api/grounded_answers.py` | Already refuses peso amounts not in the records. Did not check that the answer named the car asked about |
| Authorization | Back-End `ChatRetrieval` | Sound: role and identity come from the session. Held at 100% before and after |
| Fallback classifier | `trained_models/chatbot_nlp.joblib` | Only sees questions the planner passes on. Not the cause of the misses |

## 2. Root causes of the 1,089 misses

They came from 172 distinct wordings. 1,034 misses failed in the base wording; about 50 needed a filler word or typo to fail.

| Misses | Cause | Example |
|---:|---|---|
| 409 | The phrase "cost me" sent hypothetical price questions to the customer's bookings | "How much would 5 days with the Vios cost me?" |
| 239 | Missing ways of asking one detail (90 of these were correct answers failed by a too-strict check) | "how old is", "run on", "5 or 7 seater" |
| 162 | Stock questions not recognised, or a seat number treated as a filter that hid the car | "do you guys have", "may X ba kayo", "pababa" |
| 114 | Admin bugs (below) | |
| 47 | Policy wording gaps | "is smoking ok", "drive it to Baguio" |
| 46 | Durations not recognised | "a whole week", "dalawang linggo" |
| 32 | Own bookings asked without the word "booking" | "when can I get my car" |
| 28 | Small talk sent to the knowledge search | "got it thanks", "yo" |
| 12 | Car-problem wording | "the car just clicks" |

These add up to 1,089. The grouping is by question family, so each row shows the main cause.

The admin bugs, traced in the code:
- **"Reservation #52 doesn't exist":** "what's reservation 52" was read as a customer named "What". The record was never missing; the database lookup was correct but filtered by a wrong name.
- **Confirmed instead of pending:** the typo corrector turned the correct word "approve" into "approved", which means confirmed.
- **"complete list":** "complete" became "completed" the same way.
- **"Rental price of the Vios":** read as reservations of a customer named "The Vios".
- **"Who reserved the Vios":** normalising turned "reserved" into "reserve", so the pattern never matched.

No miss came from a wrong database field, relationship or calculation. They were all misunderstandings before retrieval.

## 3. Improvements

| Change | What it improves |
|---|---|
| Hypothetical questions ("would", "if I", "supposing") are quotes unless the customer says "my" | The largest failure group |
| Durations in words, weeks, a month, Tagalog; "linggo" is a week after a number | Quotes. Hours now get an honest "daily rates only" answer |
| Typo corrector never changes a word into its own inflection | Admin status mistakes, for any word |
| Tagalog additions: sino, kanino, nag-book, naka-book, yung, anong, nyo, libre, pababa and more | Taglish understanding |
| Filler removal: "can i ask", "pls help", "good pm", "asap" | Questions wrapped in courtesy phrases |
| Small-talk detection before any lookup, reusing the existing `goodbye` intent | "Got it, thanks", "Okay, noted", with no API change |
| Stock questions answer "Yes, we have..." or "couldn't find" | Availability of listed and unlisted cars |
| Yes/no seat questions compare seats and never hide the car | "Is the Vios a 7 seater?" now gets "No, it has 5 seats" |
| Named cars stay recognised, including first-word and hyphen forms | "montero" for Montero Sport, "brv" for BR-V |
| Admin status words: to approve, awaiting, declined, canceled, finished | Pending/confirmed/cancelled/rejected/completed lists |
| Customer names only when the words can be a name | Fixes "What", "The Vios", "Reservations" |
| Who-booked in many wordings, in English and Tagalog; still refused for customers | Booking ownership |
| Vague price questions ask which vehicle and how many days | "How much po?" no longer guesses |
| Company money refused to customers however worded | Clearer refusals (no data had leaked before) |
| New final check: an answer about a found car must name that car | Step 10 of your pipeline. Existing peso validation is kept |
| Follow-ups: "does it have gps", "available ba bukas", and a second part of one message | Conversation context, still per viewer |

The approach is still rules, which is the main limit (section 12).

## 4. Files changed

No PHP in Back-End or any Front-End file changed; both repositories show no changes, and the Back-End retrieval tests pass.

| File | Purpose |
|---|---|
| `ai_api/planner.py` | Intent, entities and plan choice |
| `ai_api/language.py` | Typo correction, Tagalog, phrase normalising |
| `ai_api/assistant.py` | Filler removal, small talk, clarification |
| `ai_api/grounded_answers.py` | Seat answers, stock answers, tied rankings, final answer check |
| `ai_api/test_chat_regressions.py` | 18 new tests, one per root cause |
| `scripts/stress_test.py` (new) | Reusable evaluator with all the requested metrics |
| `scripts/stress_retrieval_cli.php` (new) | **Test harness only**, see below |
| `scripts/stress_sets/` (new) | Question generators |
| `data/evaluation/stress/` (new) | Baseline, question sets, two test fleets, run results |

**For your decision:** `scripts/stress_retrieval_cli.php` uses `require_once`, which your rules forbid in the backend. It is outside Back-End, runs only in tests, and copies the existing `Back-End/tests/chat_retrieval_cli.php` so tests can fix the date. Without it, tests that depend on today's date break as time passes.

## 5. Were more datasets necessary?

**No.** At most 12 of the 1,089 misses (about 1%) involved car knowledge, and troubleshooting scored 98.44% and 100% on the blind sets. The rest were understanding bugs, which more data would not fix. Nothing was downloaded.

## 6. Datasets evaluated

Facts come from web searches; details marked "unconfirmed" need checking before any use.

| Dataset | Source and content | License | Decision |
|---|---|---|---|
| Schema-Guided Dialogue | Google; about 18K task dialogues in 17 domains. A rental-car domain is unconfirmed by the search | CC BY-SA 4.0 (share-alike) | **Possible later**, for evaluation wording only. English only |
| CLINC150 | Labelled intents, including `car_rental`, `oil_change_how` and out-of-scope | CC BY 3.0 per the dataset card; original statement unconfirmed | **Possible later**, to test off-topic handling. Off-topic already scores well |
| Taglish e-commerce dialog-act corpus | 2019 paper, 28 tags | Availability and license unconfirmed | **Best fit if obtainable**; ask the authors. No licensed Taglish support dataset was found |
| NHTSA complaints | US government; complaints since 1995 | Complaints license unconfirmed (recalls file is tagged public domain) | **Rejected for now.** Unverified reports, and knowledge is not the gap |
| NHTSA vPIC | US vehicle specifications API | Free to use; license unconfirmed | **Rejected.** US market, and your database must stay the source of vehicle facts |
| SCANIA Component X | Real truck sensor and repair data, Scientific Data 2025 | Sources disagree; check before use | **Rejected for chat.** One anonymised truck component. Only relevant to a future maintenance model |

**Recommendation:** download nothing now. The most valuable data is your own customers' real questions, anonymised, which would need your approval and a privacy check. The new sets were never used for training.

## 7. Model training

None. The 1,089 misses were not classifier errors, so retraining would not have fixed them. `chatbot_nlp.joblib` and the maintenance model are unchanged.

## 8. Intent and retrieval

| Metric | Blind 1 before -> after | Blind 2 before -> after |
|---|---:|---:|
| Intent accuracy | 86.26% -> 97.82% | 87.59% -> 98.73% |
| Retrieval accuracy | 81.52% -> 96.36% | 81.69% -> 96.65% |

Retrieval counts as correct only if the right tool ran and the expected fact reached the answer.

## 9. Before and after

| Test | Questions | Before | After | How far to trust it |
|---|---:|---:|---:|---|
| **Blind 1**, second fleet | 2,019 | 79.74% | **96.93%** (95.74% after audit) | First run, no fixing from it beforehand |
| **Blind 2**, third fleet, final-round code | 1,254 | 83.49% | **97.77%** | First run, written after the fixes to that point |
| Validation 2, first run | 509 | not run | 94.50% | Honest early estimate |
| New 10,000 from the last test | 10,000 | 89.11% | 99.96% | **Not unseen**, I fixed against it |
| Validation 1 | 656 | 82.62% | 100% | **Not unseen** |
| Original 10,000 | 10,000 | 100% | 100% | Regression check |
| Three follow-up sets | 9,000 | 100% | 100% | Regression check |
| Your 236-case evaluation (real clock) | 236 | 99.58% | 99.58% | Same single failure before and after; see below |
| Unit tests | 204 (3 skipped) | 186 passing | all pass | |

The 236-case failure, `g-v05`, asks about 2026-11-06, which has now passed, so refusing is correct. The test needs a later date. Old and new code both fail it the same way.

| Target | Result | Met? |
|---|---|---|
| 95%+ on unseen questions | 96.93% (95.74% audited) and 97.77% | Yes, on author-written sets |
| 98%+ intent accuracy | 97.82% and 98.73% | Partly |
| 98%+ retrieval accuracy | 96.36% and 96.65% | **No** |
| 100% prevention of private-data disclosure | 0 violations | Yes, on what was tested |
| Zero crashes | 0 | Yes |

Other measures on blind 1 and 2 after the fixes:

| Measure | Blind 1 | Blind 2 |
|---|---:|---:|
| Average per distinct wording | 98.35% | 95.68% |
| Wrong answers | 59 | 18 |
| Unanswered | 3 | 10 |
| False positives (answered when it should not) | 0 | 1 |
| False negatives (refused when it should answer) | 2 | 9 |
| Median / 95th-percentile AI time per question | 1.6 / 33 ms | 2.1 / 29 ms |

**Audit of the checks.** All failures in both sets were read by hand, and none was an evaluator mistake. Reading passes found 24 weak passes in blind 1, such as contradictions ("couldn't find a Honda BR-V", then its plate) and listing deposit amounts when asked about getting a deposit back. These give the 95.74%. In blind 2, 60 sampled passes were read and none was wrong, and a contradiction scan found none. One cosmetic flaw there, a repeated "couldn't find" sentence, is now fixed.

**Code changed after blind 2.** Four small fixes, plus two regressions found by your 236-case evaluation, came after that score. They were checked with unit tests and regression sets only, so 97.77% describes the code just before them.

## 10. Results by category

| Category | Blind 1 before -> after | Blind 2 before -> after |
|---|---:|---:|
| Rental pricing | 92.62% -> 95.13% | 97.33% -> 100% |
| Vehicle specifications | 76.95% -> 100% | 76.49% -> 96.14% |
| Finding a car | 63.08% -> 99.49% | 77.27% -> 95.45% |
| Availability | 100% -> 100% | 100% -> 100% |
| Booking retrieval | 81.03% -> 100% | 85.71% -> 91.43% |
| Admin | 67.97% -> 92.91% | 73.90% -> 98.43% |
| Policy | 87.80% -> 97.56% | 73.08% -> 84.62% |
| Troubleshooting | 98.44% -> 98.44% | 100% -> 100% |
| Conversation | 57.14% -> 97.96% | 68.75% -> 100% |
| Security | 100% -> 100% | 100% -> 100% |
| Taglish questions (any topic) | 72.71% -> 96.88% | 75.18% -> 95.04% |

Small categories move a lot on a few questions: policy had 26 and bookings 35 in blind 2.

## 11. Security and privacy

- 0 violations in 56 blind attack questions (impersonating an admin, instruction overrides, SQL, other customers' records, company totals, plates, mileage), and 0 in the 30 validation ones.
- Every customer answer in every run was also scanned for other people's names, plates and company totals: 0 found.
- Your 236-case evaluation still reports 0 permission leaks in 27 cases.
- No authorization code changed. The Back-End still applies the role and user from the session. Who-booked questions from customers are refused, and a customer asking for someone else's reservation number gets "couldn't find" with no details.
- Passing these tests does not prove security in general. Tests ran on fixtures, not your live database.

## 12. Limitations and next steps

- **Same author.** I wrote both the fixes and the blind questions, although each blind set was sealed by hash and scored on its first run. Real accuracy with real customers could be lower.
- **Still rules.** Every new set found new wordings the rules miss; the first run on validation 2 was 94.50%. Expect a steady trickle of gaps, not a finished system.
- **Known misses.** "how is the territory" (model names that are ordinary words), "mga sasakyan nyo po", "what do you require from renters", "show what i can book", "is booking online". Tagalog coverage is the thinnest area.
- **Not tested.** The live database, and the full Front-End to Back-End path over HTTP.
- **Not supported by your data.** Hourly rates, discounts and extra charges are not stored, so the AI says so and quotes daily rate times days.

Recommended next steps, in order:
1. Try it on the running system, then decide about committing.
2. Have someone else write 100 to 200 test questions, ideally Taglish speakers.
3. Review anonymised real questions regularly and add what fails.
4. Update the date in `g-v05`.

## Re-running the tests

From `automotive_ai_service`:

```
python scripts/stress_test.py data/evaluation/stress/regression/questions.jsonl out.jsonl --today 2026-11-01
python scripts/stress_test.py data/evaluation/stress/questions_blind2.jsonl out.jsonl --today 2027-06-10 --fixture data/evaluation/stress/fixture_blind2.json
```

The blind sets are spent now that their failures have been read, so write a new one for any new claim. The baseline is read-only in `data/evaluation/stress/baseline_2026-11-07/`, with checksums in `SHA256SUMS.txt`.

## Sources

- [Schema-Guided Dialogue dataset card](https://huggingface.co/datasets/GEM/schema_guided_dialog/blame/main/README.md)
- [CLINC150 dataset card](https://huggingface.co/datasets/clinc_oos/blob/main/README.md)
- [Taglish e-commerce paper author page](https://aclanthology.org/people/jared-rivera)
- [NHTSA complaints flat file](https://catalog.data.gov/dataset/nhtsas-office-of-defects-investigation-odi-complaints-complaints-flat-file)
- [NHTSA vPIC API](https://vpic.nhtsa.dot.gov/api/)
- [SCANIA Component X paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11933314/)
- [SCANIA Component X data catalogue](https://snd.se/en/catalogue/dataset/2024-34)
