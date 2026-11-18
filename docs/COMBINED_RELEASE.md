# Combined pull-request release

This integration combines the 40 pull requests reviewed on 18 November 2026.
It preserves their commit ancestry so GitHub can identify the merged work. One
push to the existing main branch prepares one release, consuming all pending
changelog.d notes together. No individual feature merge is pushed to production.
The owner's original working tree is separate and its uncommitted work is excluded.

## Integration decisions

- Every Labs experiment starts off. The bingo grid and personal countdown share
  the same Configure interface; races also have a controller-accessible editor.
- Ordinary dates and Records weeks follow the viewer's local timezone. Bingo
  keeps a shared Monday-to-Sunday Oslo calendar so members in different timezones
  get the same objectives and count the same events.
- The status line gives quiet-hours information priority over race progress and
  the personal countdown. Neither experiment creates extra group traffic.
- Countdown targets use the option schema and a new character migration. Manual
  Hardcore selection and group-name consent retain their separate migrations.
- Deathless streaks are hidden when a positive shared death count has no known
  logged boundary. Other characters' level-ups cannot win your private race.
- The cap record explicitly states that timing starts at first recorded activity.
- The Nynorsk homepage includes the current main-window demonstration and privacy
  statement. Its page is included in both the sitemap and public verification.
- The code receives the MIT licence proposed in PR #281; original creative assets
  retain the terms described in README.md. The owner's instruction to merge all
  PRs supplies the requested approval for that draft.

## Remaining feature scope

These are experimental first versions, rather than completion of every related
issue. Chronicles appear beneath last week's Records list when opened; automatic
login generation, separate Activity cards and personality-specific chapters remain
future work. Seasonal captions use approximate fixed holiday dates, a small shared
caption bank and no seasonal border. The transport, sharing-policy and page-layout
refactors establish their first shared helpers; the remaining migrations of their
callers remain separate work. No new caption catalogue or voice recordings are
promised by this integration.

When we play derives coarse patterns from activity already shared with group
members. Its privacy explanation appears in both the addon and homepage. It has
no separate opt-out; existing hidden-character and mute filters apply.

## Owner's live checks

Mocked tests do not establish real WoW API availability, rendering, controller
behavior or realm/faction delivery. Check first opening Options, Groups and
Notifications in all four editions; the longer settings page; the Hardcore
fallback in Classic Era and Forever; and controller navigation of Labs Configure,
the race editor, countdown, bingo and CSV copy dialog. Check in-instance login
sync against a friend's actual received data. See LIVE_POPUPS.md for the broader
checklist.

The Nynorsk homepage is checked in a browser at widths 1440, 820, 390 and 320;
in-game layouts still need a live client. CurseForge's project licence selector
must be updated by the owner to match the code licence if it still says All Rights
Reserved. GitHub's private vulnerability reporting should be enabled for the new
security-report link.
