# Studio usability gate (WP 4.8, R11)

Status: script written 2026-11-22. **Not run.** It needs a real CX lead who has not used NorthCX; no result, time or quote exists, and none is claimed. The release checklist lists it as an open item.

## Who and what
- **Participant:** one person who leads or works in customer support, has never used NorthCX, is not an engineer, and has not seen this script. Run at least three, one at a time; the gate is judged per person.
- **Task:** starting from a clean install in demo mode, create an agent from a ready-made template, connect it to a tool, test it, and release it, without help.
- **Setup:** a fresh `docker compose up -d --build --wait` with `NORTHCX_DEMO=1`, Studio open on the home page, a screen recording, one observer who may not speak except to read the prompts below. The demo model is keyword rules, not an AI, so the task judges the screens and wording, not answer quality.

## Prompts (read aloud, one at a time; do not explain the screen)
1. "Your shop wants an agent that answers order-status questions. Set one up."
2. "Check that it answers 'where is my order 2077' correctly. Add one example of your own as a saved test."
3. "Change the agent so that refunds over a limit of your choice need a person to approve."
4. "Make it live."
5. "Show me what a customer would see if it tried to refund 240 and what a person has to do about it."

## What the observer records
For each prompt: start and end time (from the recording), number of wrong clicks (a click that leads to a screen the participant then leaves without using), every point where the participant stops for more than 20 seconds, every question they ask, every word they say they do not understand, and whether they finished unaided.

## Gate (proposed; the owner confirms or changes the numbers before the first session)
The gate passes when, for at least three of the first three or four participants:
- all five prompts are finished without the observer helping;
- the whole task takes no more than 45 minutes;
- no screen needs an explanation of a word or button from the observer.

Failing any bullet for a participant is a finding, not a verdict on the participant. Each finding gets a work item (wording, layout, missing step) and the gate is run again with a new participant. Results go in `docs/12-project/NorthCX_Agent-Platform-Plan.md` with the date and the count of participants; names and recordings are not committed.

## Why the numbers are proposals
No time for a first agent has been measured. 45 minutes and the 20-second stop are starting points chosen so the result is checkable, not figures from data. Replace them once the first sessions show what is normal.
