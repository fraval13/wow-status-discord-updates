"""Browser-like Back and breadcrumbs in the main window."""
from test_profile import open_profile
from test_roster import pair, pump


def crumbs(lua):
    return [c['label'] for c in lua.eval('WoWStatusMainWindow.crumbs()').values()]


def link(lua, label):
    count = lua.eval('#WoWStatusMainFrame.crumbs')
    for i in range(1, count + 1):
        c = lua.eval(f'WoWStatusMainFrame.crumbs[{i}]')
        if c.IsShown(c) and label in c.label.text:
            return c
    raise AssertionError(label)


def test_profile_activity_back_and_breadcrumbs():
    mira, thora = pair()
    pump(mira, thora)
    view = open_profile(thora, 'Mira')
    assert crumbs(thora) == ['Home', 'Characters', 'Mira']
    view.activity.OnClick(view.activity)
    assert crumbs(thora) == ['Home', 'Characters', 'Mira', 'Activity']
    assert thora.eval('WoWStatusActivityLog.character') == 'mira-testrealm'
    # Back: the profile again.
    back = thora.eval('WoWStatusMainFrame.back')
    back.OnClick(back)
    assert thora.eval('WoWStatusMainWindow.active()') == 'characters' and view.IsShown(view)
    assert crumbs(thora) == ['Home', 'Characters', 'Mira']
    # The Characters crumb: the list, without the profile.
    characters = link(thora, 'Characters')
    characters.OnClick(characters)
    assert not view.IsShown(view) and crumbs(thora) == ['Home', 'Characters']
    # Back to the profile, then Home.
    back.OnClick(back)
    assert view.IsShown(view)
    home = link(thora, 'Home')
    home.OnClick(home)
    assert thora.eval('WoWStatusMainWindow.active()') == 'overview' and crumbs(thora) == ['Home']


def test_tabs_are_steps_too():
    _, thora = pair()
    thora.eval('WoWStatusMainWindow.show')('records')
    thora.eval('WoWStatusMainWindow.show')('activity')
    assert crumbs(thora) == ['Home', 'Activity']
    thora.eval('WoWStatusMainWindow.back')()
    assert thora.eval('WoWStatusMainWindow.active()') == 'records'
