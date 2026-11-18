"""Sharing a group's secret name requires an explicit, local first opt-in."""
import pytest
from test_roster import pair, pump


def setup():
    own, friend = pair()
    own.execute('WoWStatusGroups.update("dawnwatch\\nSecret Garden", "Frank")')
    group = own.eval('(WoWStatusGroups.key("Secret Garden"))')
    pump(own, friend)
    own.eval('SlashCmdList.WOWSTATUS')('groups')
    row = next(row for row in own.eval('WoWStatusGroupWindow.rows').values() if row.id == group)
    return own, friend, group, row


def tick(row, enabled):
    row.listed.SetChecked(row.listed, enabled)
    row.listed.OnClick(row.listed)


def test_first_opt_in_keeps_the_name_private_until_confirmed():
    own, friend, group, row = setup()
    tick(row, True)
    dialog = own.eval('WoWStatusGroupListingConfirm')
    assert dialog.IsShown(dialog)
    assert not row.listed.GetChecked(row.listed)
    assert own.eval('WoWStatusGroups.isListed')(group) is False
    assert 'cannot take back' in dialog.body.text
    assert 'Anyone with the name can join' in dialog.body.text
    assert not any(text.startswith('G ') for text in pump(own, friend, start=200))
    dialog.accept.OnClick(dialog.accept)
    assert own.eval('WoWStatusGroups.isListed')(group) is True
    assert own.eval('WoWStatusDB.listing_confirmed')[group] is True
    assert row.listed.GetChecked(row.listed)
    assert row.listedLabel.text == "Sharing this group's name with my other groups"
    assert any(text.startswith('G ') for text in pump(own, friend, start=300))


@pytest.mark.parametrize('cancel', ['button', 'close'])
def test_cancelling_does_not_enable_sharing_or_remember_consent(cancel):
    own, friend, group, row = setup()
    tick(row, True)
    dialog = own.eval('WoWStatusGroupListingConfirm')
    if cancel == 'button':
        dialog.cancel.OnClick(dialog.cancel)
    else:
        dialog.Hide(dialog)  # Escape / B uses UISpecialFrames.
    # A stale callback after closing cannot enable sharing either.
    dialog.accept.OnClick(dialog.accept)
    assert own.eval('WoWStatusGroups.isListed')(group) is False
    assert own.eval('next(WoWStatusDB.listing_confirmed)') is None
    assert not any(text.startswith('G ') for text in pump(own, friend, start=200))
    tick(row, True)
    assert dialog.IsShown(dialog)


def test_consent_is_per_group_and_rejoining_requires_a_new_opt_in():
    own, _, group, row = setup()
    tick(row, True)
    dialog = own.eval('WoWStatusGroupListingConfirm')
    dialog.accept.OnClick(dialog.accept)
    tick(row, False)
    assert not dialog.IsShown(dialog)
    tick(row, True)
    assert own.eval('WoWStatusGroups.isListed')(group) is True
    assert not dialog.IsShown(dialog)  # Already explicitly approved on this account.
    own.execute('WoWStatusGroups.update("dawnwatch", "Frank")')
    assert own.eval('WoWStatusDB.listing_confirmed')[group] is None
    assert own.eval('WoWStatusGroups.isListed')(group) is False
    own.execute('WoWStatusGroups.join("Secret Garden")')
    assert own.eval('WoWStatusGroups.isListed')(group) is False
    own.eval('WoWStatusGroups.requestListing')(group, True)
    assert dialog.IsShown(dialog)


def test_confirming_after_removal_cannot_rejoin_or_list_the_group():
    own, friend, group, row = setup()
    tick(row, True)
    dialog = own.eval('WoWStatusGroupListingConfirm')
    own.execute('WoWStatusGroups.update("dawnwatch", "Frank")')
    dialog.accept.OnClick(dialog.accept)
    assert own.eval('WoWStatusGroups.isListed')(group) is False
    assert own.eval('WoWStatusDB.account_groups')[group] is None
    assert not any(text.startswith('G ') for text in pump(own, friend, start=200))


def test_audience_deduplicates_other_groups_and_excludes_self_and_this_group():
    own, _, group, _ = setup()
    own.execute('''
        WoWStatusGroups.join("Third Circle")
        local garden = WoWStatusGroups.key("Secret Garden")
        WoWStatusPopups.peers = function(id)
            if id == garden then return {"OnlyHere-TestRealm"} end
            return {"Thora-TestRealm", "Bob-TestRealm", "Mira-TestRealm"}
        end
    ''')
    assert own.eval('WoWStatusGroups.listingAudience')(group) == 2
    own.eval('WoWStatusGroups.requestListing')(group, True)
    body = own.eval('WoWStatusGroupListingConfirm.body.text')
    assert '2 known friends' in body and 'Others may receive it later' in body


def test_the_question_and_active_state_are_translated_and_the_list_scrolls():
    own, _, group, row = setup()
    own.eval('WoWStatusLocale.set')('nn')
    own.eval('SlashCmdList.WOWSTATUS')('groups')
    tick(row, True)
    dialog = own.eval('WoWStatusGroupListingConfirm')
    assert 'Alle som kjenner namnet' in dialog.body.text
    assert 'ikkje ta tilbake' in dialog.body.text
    # Buttons were created after the locale changed, so both labels are translated.
    assert dialog.accept.text == 'Del namnet' and dialog.cancel.text == 'Avbryt'
    dialog.accept.OnClick(dialog.accept)
    assert row.listedLabel.text.startswith('Deler namnet')
    assert own.eval('WoWStatusGroupWindow.scroll.child == WoWStatusGroupWindow.list') is True
    assert own.eval('WoWStatusGroups.isListed')(group) is True
