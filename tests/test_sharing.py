"""The shared kind-to-switch map and owner lookup (#225)."""
import pytest

from test_addon import STUBS, make_lua


@pytest.mark.parametrize('kind,category', [
    ('raid', 'dungeon'), ('epicmount', 'mount'), ('questprogress', 'quest'),
    ('professionprogress', 'profession'), ('level', 'level'), ('death', 'death'),
    ('loot', 'loot'), ('dungeon', 'dungeon'), ('zone', 'zone'),
])
def test_every_kind_answers_to_one_collection_switch(kind, category):
    lua = make_lua(STUBS)
    assert lua.eval(f'WoWStatusSharing.category("{kind}")') == category


def test_owner_lookup_needs_both_guid_and_client():
    lua = make_lua(STUBS)
    lua.execute('''
        local db={characters={a={identity={guid="G1",client="retail"}},b={identity={guid="G1",client="vanilla"}}}}
        assert(WoWStatusSharing.ownerOf(db,{owner="G1",client="vanilla"})==db.characters.b)
        assert(WoWStatusSharing.ownerOf(db,{owner="G2",client="vanilla"})==nil)
        assert(WoWStatusSharing.ownerOf(nil,{owner="G1",client="vanilla"})==nil)
    ''')
