# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately, not in a public issue. Use GitHub's private vulnerability reporting for this repository (Security tab, "Report a vulnerability"). Include what you found, how to reproduce it, and what you think the impact is.

We will acknowledge a report and aim to share a plan for a fix; this is an early-stage open-source project and response times are best effort. Please give us a reasonable time to fix before publishing details.

## What is in scope

The backend (`src/backend`), the Studio web console (`src/web`), the browser SDK and widget (`src/sdk`), and the deployment files. Out of scope: weaknesses that need access to the host or database, third-party services you connect, and denial of service by sheer traffic volume.

## What we have done and what we have not

Our threat model, the review we did and its findings are in `docs/06-security/`. No independent penetration test has been done yet.
