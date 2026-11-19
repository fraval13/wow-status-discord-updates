# Shared talents and map positions

Character profiles show a read-only tree below equipment and combat stats. The
owner captures public, committed talent data from their own client: Classic tabs
use the talent APIs, while Forever and Retail use the active trait configuration.
Node positions, ranks, icons and visible connections come from that snapshot.
This is a reconstruction of the tree, rather than the owner's native talent
window; choice nodes show the selected entry. Viewing it never learns a talent
or switches a build. Missing, restricted or staged data retain the last complete
snapshot. An alt needs one login with this feature before its build is available.

Opening a profile requests the build from its owner or an online alt on the same
account. Completed builds are cached for offline viewing; partial transfers never
replace a complete build. No friend relays talent data. **Equipment, talents and
combat stats** controls capture and sending. Hiding a character or stopping
character-list sharing withdraws its shared details. Received caches retain at
most 64 builds or unavailable replies. Each tree is bounded to 384 visible nodes,
512 connections and 16,384 encoded bytes. There are at most four pending requests
and four response jobs, with request tokens, sender/group checks and a twenty-minute
transfer deadline. A response sends at most one 144-byte fragment per second
(two seconds in an instance) through the existing bounded whisper queue.

**Location and map position**, together with **Share my character list**, sends
public coordinates while the character is online and visible. Both clients first
advertise support; older clients receive no continuous coordinate packets.
Positions use the same joined-group transport and native restrictions as other
sharing. They are not saved or relayed. Sending is bounded to one position packet
per second globally and at least five seconds per recipient; larger groups and
busy queues update less frequently. The latest queued position replaces an older
one for the same recipient. Missing or restricted map APIs stop reporting.

World-map markers use the game's map projection. Nearby minimap markers follow
its view radius and rotation; points outside its range are hidden. Hovering either
marker shows the character's name, coordinates and report age. A marker fades
after 15 seconds and expires after 90 seconds without a fresh report. Coordinates
represent reported positions, not a guarantee that a character remains there.
Different instances or unavailable world-map projections cannot supply a marker.

**Friends on the map**, `/wstatus mapfriends`, and the corresponding key binding
open a scrollable list of recent reports. Selecting a friend opens that friend's
map. This list provides controller access to the same information; Escape/B closes
it, and its binding does not take controller buttons during combat.

## Live-client review

Mocks verify packet bounds, privacy, expiry, tree geometry, minimap rotation and
controller discovery. They cannot establish game rendering or API availability.
The owner still needs to check these in each supported client:

- Open your own and a friend's profile; scroll below gear, hover talents and
  compare allocated ranks and node positions with the owner's active build.
- Change and commit a talent build; refresh it from a second updated client.
- Move while a friend watches the world map and minimap; hover both markers,
  rotate/zoom the minimap and change zones. Stop Location sharing and log out.
- Navigate the talent controls and map-friend list with a controller, including
  scrolling, selecting a friend, closing with B, and entering combat.
- Check the level badge and the taller player-ranking rows with long alt names.
- Check delivery across the realm/faction combinations that the game allows.

Native line endpoints follow the client UI's own
[talent-edge implementation](https://github.com/Gethe/wow-ui-source/blob/live/Interface/AddOns/Blizzard_SharedTalentUI/Blizzard_SharedTalentEdgeTemplates.lua).
Map and trait calls follow the client API definitions, including
[Forever map APIs](https://github.com/Gethe/wow-ui-source/blob/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/MapDocumentation.lua),
[minimap APIs](https://github.com/Gethe/wow-ui-source/blob/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/MinimapDocumentation.lua)
and [trait APIs](https://github.com/Gethe/wow-ui-source/blob/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/SharedTraitsDocumentation.lua).
