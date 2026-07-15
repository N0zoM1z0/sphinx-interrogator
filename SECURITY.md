# Security policy

## Supported scope

This repository is a research sandbox rather than a deployed service. Security reports are nevertheless welcome for issues such as:

- accidental exposure of the private challenge secret through the public protocol or logs;
- a boundary violation that lets Interrogator import or inspect SphinxVM internals;
- unsafe parsing or command execution in local tooling;
- dependency or CI configuration that creates an avoidable supply-chain risk.

## Reporting

Open a private GitHub security advisory for the eventual repository. Do not include live credentials, real victim data, or instructions targeting systems outside this repository.

## Non-goals

The synthetic timing fault is intentional and is not a vulnerability to report. Difficulty calibration problems should be filed as ordinary benchmark issues.
