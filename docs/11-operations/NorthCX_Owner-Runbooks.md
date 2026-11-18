# Owner runbooks

Status: **Ready to follow.** Updated: 2026-11-10. These are the things only the owner can do, with the steps and the check at the end of each. Nothing here is automatic.

## 1. Make your own template signing key

The built-in agent templates ship signed with a **development key**. Before a release, replace it with yours so the "signed and verified" badge means your signature.

```bash
python scripts/sign_templates.py --generate-key ~/northcx-release-key.pem
python scripts/sign_templates.py --key ~/northcx-release-key.pem
git add src/backend/northcx/template_library/signing_key.pub src/backend/northcx/template_library/SIGNATURES.json
git commit -m "Sign the built-in templates with the release key"
```

Keep `northcx-release-key.pem` offline and backed up; commit only the public key and the signature list. Whenever a built-in template changes, run the second command again. **Check:** `pytest tests/test_org_templates.py` passes, and the Agent Hub shows each built-in as "signed and verified". A built-in that was changed after signing shows as changed and cannot be installed.

## 2. Run the scenarios against a live model

All the automated tests use a scripted model. Before relying on an agent, run its scenarios against a real one.

1. Set `ANTHROPIC_API_KEY` (or your provider settings) and start the server without `NORTHCX_DEMO`.
2. In the Admin app open **Build, Simulations** and run the agent's scenarios in **live** mode (or `POST /v1/simulations/runs` with `mode: live`). Scenarios that need a real model are marked in the scenario list.
3. For a model change, use the model comparison: run the same saved version against the candidate (`model` with `mode: live`) and compare pass rates.
4. For the staff assistants and routines, open the Workspace, ask each assistant a question you know the answer to, and check it cites sources and does not claim to have sent or changed anything.

**Check:** every required scenario passes live, and you have read at least five real replies for each agent you will release. Record the date, model and result in the release note.

## 3. Test single sign-on against your identity provider

OpenID Connect is built; SAML is not.

1. Register the application with your provider with the redirect URI in the Deployment Guide (`NORTHCX_SSO_REDIRECT_URI`), and set `NORTHCX_SSO_ISSUER`, `NORTHCX_SSO_CLIENT_ID` and `NORTHCX_SSO_CLIENT_SECRET`.
2. Set how people get roles: `NORTHCX_SSO_ROLE_MAP` (`group=role`), or `NORTHCX_SSO_USE_GROUPS=1` to use groups made in the Admin app, plus `NORTHCX_SSO_DEFAULT_ROLE` and `NORTHCX_SSO_ALLOWED_DOMAINS`.
3. Sign in as a person in a group with a role, a person in no mapped group, and a person from a domain you did not allow.
4. If you use SCIM, point your provider at the SCIM endpoint and check a created, changed and removed person.

**Check:** the first person lands with the right role, the second and third are refused, the Admin app's People page shows their groups, and the audit log shows each sign-in. If you need SAML, put an identity broker that speaks OpenID Connect in front of it; native SAML is a larger piece of work (an XML signature library and its security review) and is not in this build.

## 4. Allow a second tenant on a real deployment

Tenant isolation is built and tested, but `NORTHCX_TENANCY_PREVIEW=1` is still required to create a second tenant. Lift it only after:

- [ ] the penetration test in the [brief](../08-governance-safety/NorthCX_Penetration-Test-Brief.md) is done and every cross-tenant finding is fixed, with a regression test each;
- [ ] the server runs as an ordinary database role (the start-up check says so if not);
- [ ] `NORTHCX_PLATFORM_KEY` and `NORTHCX_MASTER_KEY` are set and held only by you;
- [ ] backups are whole-database and tested;
- [ ] you have read the [isolation threat model](../08-governance-safety/NorthCX_Tenant-Isolation-Threat-Model.md) and accept its known gaps.

Then change the guard in `northcx/tenancy.py` (`TenantService.create`) and the start-up check in `northcx/bootstrap/storage.py`, and record the decision in the decision log.

## 5. Tag 1.0.0

The version is `1.0.0rc1` in `northcx/__init__.py`, `pyproject.toml` and every `package.json` under `src` (a test checks they agree).

1. Make sure the full backend suite, both frontend suites and both browser smoke tests pass on `main`.
2. Change the version everywhere to `1.0.0` in one commit and update the top of `CHANGELOG.md`.
3. Tag and push: `git tag -a v1.0.0 -m "NorthCX 1.0.0"` then `git push origin v1.0.0`.

**Check:** `pytest tests/test_release.py` passes, and the Admin app's footer shows `1.0.0` to signed-in users.

## 6. Decide the open-versus-commercial question (D1)

Decision D1 is not made and must be before any billing work. The working assumption in the plan is open core, with everything built so far staying open. Record the decision in the decision log.
