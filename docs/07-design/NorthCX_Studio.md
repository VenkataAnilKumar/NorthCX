# NorthCX Studio

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

## Planned next
A scenario editor (write and run tests without YAML), knowledge screens (documents, freshness), conversation review with failure tagging, a publish checklist that shows the required checks in one place, and single sign-on. The editor does not yet offer an undo history beyond the saved versions and their diffs.

## Design rules
- Studio never bypasses the platform's controls: it creates versions, and publishing still needs the release gate; production releases still need the release permission.
- Everything Studio does is something the API can do, and is audited the same way.
- Words, not file formats: labels describe what a setting does in the customer's terms.
