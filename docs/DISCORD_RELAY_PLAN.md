# Private Discord relay requirements — 30 October 2026

The addon remains an in-game sharing tool. Keep `WoWStatusFeatures.discord=false`:
no Discord options page, checkbox, onboarding, commands or prompts in the addon.
The public homepage does not need a Discord setup flow either.

Only the people who choose to run the desktop companion need to configure the
optional relay. Its opt-in belongs in the companion, not the addon. Do not restore
the old per-character Discord settings to enable the new relay.

## Destinations

Retain the two existing private server destinations:

| Group ID entered in WoW | Existing server route key |
| --- | --- |
| `navsquad` | `466f79683c7465bc3a5ba0` |
| `ronkalot` | `19e32befc180a1cfdea5c3` |

The relay should select only these two groups, and only when the uploader belongs
to the corresponding in-game group. Keep their uploads, summaries and Discord
destinations separate. Do not provision additional Discord routes. Other group
IDs remain valid for normal in-game sharing and are not Discord destinations.

The live gateway already has only these two upstream routes; unknown group routes
return 404. Preserve that routing while implementing the relay.

## Summary behavior

- On an opted-in uploader's reload/logout save, relay eligible announcements from
  its shared account log, including friends' announcements it has received.
- Preserve original source event IDs. Deduplicate at the backend per group and
  client edition, independently of which companion uploaded an event.
- Build summaries from events not already assigned to a summary. Empty uploads
  create no AI request and no Discord message. Briefly coalesce concurrent
  uploads so two companions do not produce two recaps for the same activity.
- Calculate counts and changes in code; AI supplies wording from those facts.
  Save the batch and generated text before sending. Keep delivery state and
  Discord message IDs; do not blindly resend ambiguous deliveries.
- Recovery depends on an online member retaining the relevant events. The relay
  cannot reconstruct unavailable history or bypass game communication rules.

## Implementation status

These are the approved requirements for the proposed relay, not a claim that it
is enabled. The retained companion currently exports opted-in character history;
it does not yet upload the shared journal or generate AI recaps. The existing
addon switch also disables the old exports. Implement the companion-only relay
as a separate path without turning the addon switch on.
