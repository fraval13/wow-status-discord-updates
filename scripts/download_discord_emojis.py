import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

icons = {
    "alliance": "inv_bannerpvp_02",
    "horde": "inv_bannerpvp_01",
    "xp": "inv_misc_book_11",
    "deaths": "ability_rogue_feigndeath",
    "quests": "inv_misc_book_09",
    "location": "inv_misc_map_01",
    "player": "inv_misc_head_human_01",
    "alchemy": "trade_alchemy",
    "blacksmithing": "trade_blacksmithing",
    "enchanting": "trade_engraving",
    "engineering": "trade_engineering",
    "herbalism": "trade_herbalism",
    "leatherworking": "trade_leatherworking",
    "mining": "trade_mining",
    "skinning": "inv_misc_pelt_wolf_01",
    "tailoring": "trade_tailoring",
    "cooking": "inv_misc_food_15",
    "first_aid": "spell_holy_sealofsacrifice",
    "fishing": "trade_fishing",
}
for name in [
    "warrior",
    "paladin",
    "hunter",
    "rogue",
    "priest",
    "shaman",
    "mage",
    "warlock",
    "druid",
]:
    icons[name] = "classicon_" + name
folder = Path(__file__).resolve().parents[1] / "assets/discord-emojis"
folder.mkdir(parents=True, exist_ok=True)


def fetch(pair):
    name, asset = pair
    url = f"https://wow.zamimg.com/images/wow/icons/large/{asset}.jpg"
    try:
        data = urllib.request.urlopen(url, timeout=20).read()
        if not data.startswith(b"\xff\xd8") or len(data) >= 256000:
            raise ValueError("Not a Discord-sized JPEG")
        file = "wow_" + name + ".jpg"
        (folder / file).write_bytes(data)
        return {"name": "wow_" + name, "file": file, "source": url, "bytes": len(data)}
    except Exception as e:
        return {"name": name, "error": str(e)}


# Keep the project-generated level arrow; CDN refreshes must not restore the old
# achievement icon, which has the misleading number 30 painted on it.
manifest_path = folder / "manifest.json"
level = next(entry for entry in json.loads(manifest_path.read_text()) if entry["name"] == "wow_level")
results = list(ThreadPoolExecutor(max_workers=8).map(fetch, icons.items()))
results.insert(2, level)
(folder / "manifest.json").write_text(json.dumps(results, indent=2) + "\n")
print("Downloaded:", sum("file" in r for r in results), "/", len(results))
for r in results:
    if "error" in r:
        print(r)
