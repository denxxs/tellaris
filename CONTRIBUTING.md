# Contributing to Project Tellaris

Thanks for helping. Issues and pull requests are welcome.

## Ground rules
- Every number in the simulation needs a published source. If no data exists, leave the value empty rather than guess.
- Never commit API keys, tokens or anything in `backend/var/`.
- Run the checks before opening a pull request: `cd backend && python -m pytest`, and in `frontend/`: `npx tsc --noEmit && npx eslint app components lib`.

## Licence of contributions
Project Tellaris is released under the GNU Affero General Public License v3.0 (see `LICENSE`).
The project owner (GitHub user denxxs) also offers it under other terms, including commercial
licences and hosted services. So that every part of the project can be offered both ways, each
contribution needs this agreement.

By submitting a contribution (code, data, documentation or anything else) you agree that:

1. You wrote it yourself, or you have the right to submit it under these terms.
2. It is licensed to everyone under the AGPL-3.0, like the rest of the project.
3. You also grant the project owner (GitHub user denxxs), and any company they assign this grant
   to, a perpetual, worldwide, non-exclusive, royalty-free, irrevocable licence to use, copy,
   modify, distribute, sublicense and relicense your contribution under any terms, including
   proprietary and commercial ones. This includes a licence to any of your patents that your
   contribution would infringe.
4. You keep the copyright in your contribution and may use it however you like.

Add this line to your pull request description to confirm:

> I agree to the contribution terms in CONTRIBUTING.md.
