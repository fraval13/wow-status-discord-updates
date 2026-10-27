# Experimental in-game friend level popups

This adds a separate in-game channel path alongside exported uploads and Discord.
A real level-up can send a short message into a dedicated custom chat channel;
other opted-in addons turn accepted messages into an on-screen popup.

**Written, not tested.** No addon, game, service or tests were run on the work
computer. Validate this on your actual Classic Era clients at home. Cross-guild,
realm, faction and Forever support are not promised. Game chat restrictions may
prevent automatic sending; the addon does not bypass them.

For the new flow, select free-text IDs in `/wstatus groups`; popup channels follow
those IDs automatically, with no per-alt trust list requirement. See [GROUPS.md](GROUPS.md).
The manual channel/trust setup below is an optional legacy mode.

## Setup with two friends

Each person must install this addon version, log into a supported Classic Era
character, and choose the same channel. Channel names must begin with `WStatus`
and use letters/numbers, up to 30 characters. Pick your own group-specific suffix.

```text
/wstatus popup channel WStatusOurGang
/join WStatusOurGang
/wstatus popup on
/wstatus popup trust Thora-RealmName Frank
```

Replace `Thora-RealmName` with the actual sender character and realm, omitting
spaces in the realm. Add each participating alt separately. The optional final
label (`Frank`) is a local display preference. Without it the popup uses the
character's name. Names without a realm are interpreted on your own realm.

The receiving list is local and independent of Discord `/link` and nicknames; the
addon cannot fetch the Discord roster. It trusts the actual game chat sender, not
a name claimed inside the message. Matching a local label does not verify Discord
identity. Empty trust lists accept nobody. Up to 200 character entries are supported.

Each sender must separately enable broadcasting and already consent to sharing
that character's level:

```text
/wstatus popup send on
```

Enable **Share this character**, the **level** profile field, and **level** event
collection in `/wstatus`. A real `PLAYER_LEVEL_UP` then queues a broadcast. Every
real level can notify friends, independent of Discord milestone filters. Synthetic
`/wstatus test` events are not broadcast. Reception can be enabled even if the
receiving character does not share its own data.

The popup says, for example, **Frank’s Thora reached level 25!** if you supplied a
local label. These are player-reported channel updates, not verified service data.
Both characters must actually be able to communicate through the chosen channel.
Offline recipients do not receive an automatic replay; delayed Discord updates and
the daily recap remain available through the existing exported pipeline.

## Transport and privacy

This first transport uses **ordinary visible channel messages**, for example:

```text
WSTATUS1 LEVEL 25 1793000000 1792990000-123456-8
```

The fields are protocol version, event type, level, timestamp and a short event
nonce. Character identity comes from the game-provided chat sender. No Discord
name, bot token, uploader credential, account password or API key is sent. People
in that channel can read the messages even without the addon. This is not encrypted
private delivery and is not a hidden addon-message prefix. Channel management and
who can join belong to your group; use the game's channel controls as appropriate.

The implementation uses `CHAT_MSG_CHANNEL`, `GetChannelName` and the chat sending
API, following [Blizzard's mirrored chat API/event documentation](https://raw.githubusercontent.com/Gethe/wow-ui-source/classic/Interface/AddOns/Blizzard_APIDocumentationGenerated/ChatInfoDocumentation.lua).
The addon does not automatically join channels, hide messages, bypass chat
lockdown, or claim cross-faction communication. Actual client restrictions may make
this experiment unsuitable; report the result before relying on it.

Popup reception, outbound broadcasts and sound are off by default. Local preferences
are account-wide across your alts and persist in this addon's SavedVariables.
Outgoing data is still gated by the current character's sharing/privacy controls;
pausing cancels queued broadcasts. Trust entries and short deduplication metadata
stay local and are excluded from companion uploads. Received friend updates are
never inserted into your character's own event history, leveling graph or JSON.

## Popup behavior

- Accepted messages show for about six seconds, with at least seven seconds between
  displays. Sound is off unless explicitly enabled.
- Popups wait until out of combat, and an active popup is held if combat starts.
- Untrusted senders, other channels, self echoes, malformed payloads, implausible
  Classic levels and old messages are rejected.
- Sender/level duplicates are suppressed for ten minutes, including a saved short
  cache across reloads; senders are also rate-limited.
- Incoming queues are bounded to 20; queued displays expire after ten minutes.
- Outgoing queues are bounded to 10. Missing channels, combat or reported chat
  restrictions hold the attempt for up to two minutes.
- Successful API calls are labeled **attempted_no_receipt**. There is no receipt
  proving anyone saw the popup. A raised/failed send is not blindly retried.

## Commands and local preview

```text
/wstatus popup test
/wstatus popup sound on
/wstatus popup sound off
/wstatus popup status
/wstatus popup untrust Thora-RealmName
/wstatus popup send off
/wstatus popup off
```

`popup test` requires reception enabled and shows a local preview only; it sends
nothing and does not create recorded progress. `popup status` reports preferences,
channel membership and the last send state. `popup off` disables reception and
broadcasting, hides the current popup and clears pending queues. It does not leave
your manually joined chat channel; use the game's `/leave` command if desired.
Changing channel clears pending queues so old-channel messages do not leak into the
new selection. The setup panel's **Popup help** button prints the command list.

## Home acceptance

1. Install with WoW closed. Confirm nothing sends or displays before opt-in.
2. Use `popup on` and `popup test` to check position, duration, optional sound and
   combat deferral locally; no network messages or graph points should appear.
3. With two consenting friends on a reachable same-faction/realm channel, trust
   each other's actual character names and enable sending/sharing on each sender.
4. Perform a real level-up; confirm one channel message and one popup at the other
   client. Confirm cross-guild behavior in the actual client.
5. Repeat a received message: no duplicate popup. Untrusted senders, wrong channels,
   stale messages, altered payload names and self echoes must not produce popups.
6. Level while in combat; verify deferred behavior. Pause sharing before a blocked
   send can leave: no later broadcast. Turning popups off must clear queued displays.
7. Check `popup status` when not joined or chat sending is restricted. Do not treat
   a successful function call as delivery evidence; record the receiver's result.
8. Verify relog behavior and each alt's privacy controls. Test a second realm/faction
   only to establish actual reachability, without assuming it should work.

Authored mock tests cover opt-in, trust, duplicates, malformed inputs, combat,
privacy cancellation, local preview and channel-send calls. They have not run here.
