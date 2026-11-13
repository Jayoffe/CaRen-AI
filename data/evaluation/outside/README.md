# Outside questions: a first-run test of the chat assistant

The assistant's own test sets were written by the people who also fixed it, so they show that
nothing broke, not how well it understands new people. This folder is for 100 to 200 questions
written by someone who has **not** seen those sets, ideally including Taglish speakers.

## For the person writing the questions

Fill in `questions_template.csv` (Excel or Google Sheets, saved as CSV). Delete the five example
rows first. One row per question:

| Column | What to write |
|---|---|
| `id` | Any unique label, e.g. `q001` |
| `role` | `customer` or `admin`: who is asking |
| `category` | A short topic word of your choice, e.g. `pricing`, `booking`, `car_problem`, `taglish` |
| `question` | The question exactly as a real person would type it: typos, Taglish and short forms are welcome |
| `must_mention` | Words a correct answer must contain. Separate required items with `;` and alternatives with `\|` (e.g. `4,500;deposit\|security`). Leave empty if any sensible answer is fine |
| `must_not_mention` | Words that would make the answer wrong, separated by `;` (e.g. another customer's name) |
| `expected_kind` | `answer` (should answer), `refuse` (must not reveal it), `notfound` (thing does not exist), `clarify` (should ask a question back), or `smalltalk` |
| `notes` | Anything that helps when reviewing |

Write questions about anything a customer or an administrator of a car-rental site might ask:
prices, availability, booking, payment, cancelling, requirements, the cars' features, car problems
and maintenance. The answers come from the test data below, not from the live site.

### Test data the assistant answers from

The test "today" is **2026-11-01**. The customer asking is **Ana Santos**; the administrator is
**Fleet Admin**.

| Car | Type | Seats | Gearbox | Fuel | Per day | Deposit | Status | GPS |
|---|---|---:|---|---|---:|---:|---|---|
| Toyota Vios | Sedan | 5 | Automatic | Gasoline | PHP 1,500 | PHP 3,000 | available | no |
| Toyota Fortuner | SUV | 7 | Automatic | Diesel | PHP 3,500 | PHP 6,000 | available | yes |
| Honda City | Sedan | 5 | CVT | Gasoline | PHP 1,700 | PHP 3,000 | rented (not shown to customers) | no |
| Toyota Hiace | Van | 12 | Manual | Diesel | PHP 4,200 | PHP 8,000 | maintenance (not shown to customers) | no |

Every car has air conditioning. Rentals are 3 to 7 days (8 to 21 as a special-duration request),
priced at the daily rate times the number of days; the deposit is separate.

| Reservation | Customer | Car | Dates | Status | Total |
|---|---|---|---|---|---:|
| #41 | Ana Santos | Toyota Vios | 2026-11-05 to 2026-11-08 | pending (awaiting payment) | PHP 4,500 |
| #17 | Ana Santos | Honda City | 2026-09-01 to 2026-09-03 | completed | PHP 3,400 |
| #52 | Ben Cruz | Toyota Fortuner | 2026-11-20 to 2026-11-23 | confirmed | PHP 10,500 |

A customer must never see another customer's name, bookings or plate numbers.

## Scoring (for the developer)

From `automotive_ai_service`, with the PHP CLI available:

```
python scripts/score_outside_questions.py data/evaluation/outside/questions_template.csv
```

The first run seals the file: its SHA-256 and date go into `data/evaluation/outside/seal.json`.
That first score is the honest one. Any later run on a changed file, or after fixing the
assistant against these questions, is reported as **not a first run**. Results are written next
to the CSV (`*_results.jsonl`, `*_summary.json`).
