# NorthCX Studio

Status: **Built**. Updated: 2026-11-09. Master for: the Studio on main today.

Studio is the part of the console where someone who does not write code changes an agent safely. It is built in steps; the first is the agent editor.

## Agent editor (U1) — as built
Open an agent, choose **Edit in Studio**. The form starts from what is live in production and covers everything an agent file can say:
- **Instructions** in plain language, with a character count.
- **Model and limits**: model, most steps per message, token limit per message.
- **Tools**: tick the ones the agent may use. Each shows whether it only reads or changes things, and whether it can need approval.
- **Checks**: reply and tool checks (the policy library, with its settings editable as JSON), customer-message checks, tool-result checks.
- **Always send to a person**: topics with the patterns that trigger them and an optional message to the customer.
- **Brand voice**: tone, guidelines, words to avoid (enforced), sign-off.
- **Skills**: tick a skill and choose strict, guided or free.
- **Style per channel**: optional wording for sms, email, web.

**Live checks.** After each change (a short pause), the page asks the server to check the agent without saving it. The side panel shows "The agent is valid" or every problem found (unknown tool, a check with a missing setting, a topic without a name), what differs from production, and whether it is already the latest saved version. Save is disabled until the agent is valid and different.

**Save and try.** *Save as new version* stores a version; nothing goes live. *Try it in dev* releases that version to the dev environment (no proof needed there) and opens the test console on dev, so the editor can talk to the change straight away. The link to the versions page is where required scenarios are run and the version is published through the release gate and environments, as always.

**Roles.** People who can create versions (developers and above) can edit; others can read the form but not change it.

## Scenario editor (U3) — as built
Simulations lists every scenario with its source (file or saved) and a **New scenario** button. The editor describes a test in plain terms: name, agent, what it checks, whether it is required to release, tags; the **conversation** (what the customer says and, after each message, the agent's expected status, tools called, and words the reply must or must not contain); checks across the whole conversation (tools never called, most model calls, text that must never reach the model); and the **model script** (the answers replayed in offline runs, as replies or tool calls with JSON input). A side panel checks the scenario live and says exactly what is wrong. **Save** stores it; **Run it now (offline)** runs just this scenario and shows pass or fail with the reasons; **Edit as text** shows the scenario as JSON or YAML for anything the form does not cover. A scenario can be drafted from a real conversation (`GET /v1/sessions/{id}/scenario-draft`) and saved here.

Rules that keep the release gate honest:
- Saved scenarios live in the database next to the scenario files. A file scenario wins on a name clash and cannot be changed in the editor.
- Editing a scenario changes its digest, so earlier passes no longer count and the gate asks for a new run. Renaming is not allowed (save under the new name, delete the old).
- Developers can write ordinary scenarios. Deciding which scenarios are **required** (creating, changing, relaxing or deleting one) needs the release permission, because that decides what may be released. Every change is audited.
- An agent made from a template can save the template's tests with it (`saveScenarios`); a developer's copies are optional until a release manager marks them required.

## Knowledge screens (U6) — as built
The Knowledge page manages the documents agents answer from:
- **Sources**: create one (for example "Help centre") with an optional "out of date after N days"; delete one with all its documents.
- **Documents**: a table of title, source, number of passages and when each was last reviewed, with an "out of date" badge, a source filter and an "out of date only" filter. **Add document** takes a title, optional link, and text or Markdown, typed, pasted or loaded from a file (up to 500,000 characters); headings split it into passages. **Edit** opens the original text, and saving replaces the old passages. "Mark as reviewed today" resets the document's freshness clock without changing the text.
- **Try a question**: type what a customer might ask and see the passages the agent would find, numbered the way answers cite them, with their section, date and an out-of-date flag. "Nothing relevant was found" tells you a customer asking this would get no answer from the documents.
Changing knowledge can also re-run tagged scenarios (see the regression settings). Reading needs `knowledge:read`; changing needs `knowledge:write` (developers and admins). Not built: web page crawling, PDF and Word files, and per-document history.

## Planned next
 (documents, freshness), conversation review with failure tagging, a publish checklist that shows the required checks in one place, and single sign-on. The editor does not yet offer an undo history beyond the saved versions and their diffs.

## Design rules
- Studio never bypasses the platform's controls: it creates versions, and publishing still needs the release gate; production releases still need the release permission.
- Everything Studio does is something the API can do, and is audited the same way.
- Words, not file formats: labels describe what a setting does in the customer's terms.
