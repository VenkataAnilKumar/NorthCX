# NorthCX Licences

Status: Draft. Dependency-specific licence findings are in `00-reference/NorthCX_Reference.md`.

## Policy
- NorthCX core: Apache-2.0 (proposal, undecided).
- Core dependencies must be Apache-2.0, MIT, BSD or equivalent.
- Source-available or restricted licences (including enterprise directories of open projects) are never copied or bundled.
- Directories under separate commercial terms in otherwise open projects are not used.

## Copied code
Code reuse is governed by `05-technical/NorthCX_Code-Reuse-Policy.md`. Verified licences of the reference repositories are in the Reference (section 10). Restricted directories and source-available licences are never copied.

## Process
1. Record licence and version for every new dependency.
2. Check transitive licences in CI.
3. Review attribution and notice obligations before release.
4. Re-verify licences at each major upgrade.

## Open
Final project licence; contributor agreement (DCO vs CLA).
