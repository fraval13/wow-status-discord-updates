# Security

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub: go to the repository's
**Security** tab → **Report a vulnerability** (GitHub's private vulnerability
reporting). That opens a private advisory that only the maintainer can see, and
it lets us fix the problem before it is described in public.

If private reporting is not available to you, open a public issue that says only
*"security report, please get in touch"* — no details — and wait to be contacted.

Please include, as far as you can:

- what an attacker can do, and what they need in order to do it;
- which edition and addon version you saw it in;
- the smallest sequence of steps that shows it.

You will get an acknowledgement when the report is read. This is a hobby project
maintained by one person, so there is no guaranteed response time, and there is
no bug bounty.

## What is worth reporting

The addon runs inside the game client and talks only to other players' clients,
so the interesting ground is what one player can learn about or do to another:

- **Group names.** A group ID is a shared secret: it is how the addon decides who
  may read your progress. Anything that lets a group name be guessed, enumerated,
  logged, or recovered from traffic or from a listing is a real problem.
- **Data leaking past a privacy choice.** The per-character field switches and
  the hidden-character choices are meant to be honoured everywhere a value is
  recorded, shown, sent or relayed. A path that ignores one is worth reporting.
- **Accepting something that should be rejected.** Log entries, roster messages
  and equipment payloads from a non-member, from a forged sender, or beyond their
  size and rate limits.
- **The homepage and the release pipeline.** Anything that could put a file into
  a public download, or onto the site, that is not built from a committed
  revision.
- **Anything in this repository that should not be public.** If you find a token,
  a private configuration file or a real group name committed here, that is a
  security report, not an issue.

Please do **not** report:

- bugs with no security consequence — those are ordinary issues, and welcome as
  such;
- that the addon shares your progress with the group you joined, or that someone
  you gave your group name to can read it: that is what joining a group means;
- findings from attacking Blizzard's servers or other players' computers. Do not
  do that, and do not send us the results.

## Scope

This repository: the addon, the homepage and its build, the deployment scripts
and the preserved Python companion. The hosted site and its group services are
covered as far as the code here controls them.

## Handling

Reports are read by the maintainer. A fix ships in an ordinary release; a release
note says that something was fixed, and names the reporter if they want to be
named. Nothing about a report is published before a fix is out, unless the
reporter asks for it.
