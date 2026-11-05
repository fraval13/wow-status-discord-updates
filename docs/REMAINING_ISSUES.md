# Open-issue audit — 5 November 2026

Checked after pulling main at `6b41750`. No game client, private group
configuration, player SavedVariables, or production service was changed.

| Issue | Finding and action |
| --- | --- |
| [#5](https://github.com/fraval13/wow-status-discord-updates/issues/5) | Already fixed: the encounter count is the third lockout return. Existing regression coverage verifies the documented tuple. The normal-dungeon API question stays under #25. |
| #85 — minimap | Owner confirmed on 5 November that the minimap worked in their live check the previous day and is handling the issue closure. No further geometry change is needed. |
| [#25](https://github.com/fraval13/wow-status-discord-updates/issues/25) | Fixed empty Classic profession-list fallback, empty mount-collection fallback, Era outgoing-message restrictions, settings-call failure fallback, and channel selection tracking/restoration without the optional getter. Live API availability, normal dungeon completion, realm/faction transport, protected calls and channel limits remain live checks. The owner explicitly deferred all game-client testing on 5 November; do not claim these checks passed. |
| [#87](https://github.com/fraval13/wow-status-discord-updates/issues/87) | Added successful first raid encounters, conservative epic mount-item acquisition, large banners and Firsts medals. No raid-clear claim is inferred from an arbitrary boss. Mount item metadata and inventory APIs must be available; Retail scaling mounts and class-quest mounts are unsupported. |
| [#88](https://github.com/fraval13/wow-status-discord-updates/issues/88) | Added per-character opt-in compact recap sharing, strict fixed-phrase validation, and quiet bounded log recovery. The sender name is supplied by the existing popup/log card rather than arbitrary recap text. |
| [#1](https://github.com/fraval13/wow-status-discord-updates/issues/1) | Server rotation completed on 5 November: both exposed routes return 404, two replacement routes are healthy, old data is retained privately, and the receiver now uses root-only private configuration. Replacement names were delivered in a mode-0600 owner handoff outside the repository. The addon/companion retirement guard prevents reuse of the known exposed groups; members must obtain replacements privately and update their selections when next playing. |

New live kinds use `WSTATUS8`, which old receivers ignore. The existing journal
reader ignores unknown kinds without accusing their sender of invalid log data;
updated receivers retain the same event IDs, group scope, limits and quiet sync.
Private recaps retain empty group scope and cannot be offered to peers. Turning
sharing off revokes the owner's group scopes through the existing privacy path.

Channel selection follows Blizzard's
[ChannelList](https://github.com/Gethe/wow-ui-source/blob/live/Interface/AddOns/Blizzard_Channels/ChannelList.lua):
`GetSelectedChannelIDAndSupportsText` supplies the initial UI selection, and a
secure hook observes subsequent native selections so an asynchronous roster read
does not undo a user's later change. Missing UI frames remain supported.

## Live acceptance still required

- Forever minimap: owner confirmed the fix works in a live client; issue #85 is resolved.
- Each edition: start up, open settings in/out of combat, observe professions,
  and exchange a new milestone and quiet login history with a second account.
- Raid: a failed encounter produces nothing; first success produces one banner
  and log card; repeat kills do not duplicate it. Unsupported clients skip it.
- Classic epic mount: purchase an epic mount item, allow its information to load,
  and check the banner/medal. Ordinary mounts and already-owned epic mounts
  must not trigger this milestone. Missing evidence produces no invented event.
- Recaps: confirm the default is private; opt in on one character, end a session,
  and check live delivery and quiet catch-up. Test an older recipient too: no
  popup or invalid-log warning should appear for the unsupported new kinds.
- Channels: open Chat Channels on a different channel; read the group roster;
  confirm the selection returns. Change selection while a read is pending and
  confirm the addon does not overwrite the new choice.
