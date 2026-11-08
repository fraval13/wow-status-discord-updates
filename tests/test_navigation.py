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


def back_button(lua):
    return lua.eval('WoWStatusMainFrame.back')


def history(lua):
    steps = lua.eval('WoWStatusMainWindow.history()')
    return [(s.page, s.profile, s.character) for s in steps.values()]


def test_a_page_with_nothing_behind_it_offers_no_back_button():
    _, thora = pair()
    thora.eval('WoWStatusMainWindow.show')('activity')
    assert history(thora) == []
    assert thora.eval('WoWStatusMainWindow.canGoBack()') is False
    assert back_button(thora).IsShown(back_button(thora)) is False
    # Pressing it anyway (a controller's B, Profile's own Back) reports nothing done.
    assert thora.eval('WoWStatusMainWindow.back()') is False


def test_a_step_that_would_redraw_the_open_page_is_no_step_at_all():
    # The symptom reported in game: Back on Activity led straight back to Activity.
    _, thora = pair()
    thora.eval('WoWStatusMainWindow.show')('activity')
    thora.execute('table.insert(WoWStatusMainWindow.history(), {page="activity"})')
    assert thora.eval('WoWStatusMainWindow.canGoBack()') is False
    assert back_button(thora).IsShown(back_button(thora)) is False
    assert thora.eval('WoWStatusMainWindow.back()') is False
    assert history(thora) == []          # the dead step is dropped, not followed
    assert thora.eval('WoWStatusMainWindow.active()') == 'activity'


def test_back_passes_over_dead_steps_to_the_last_real_one():
    _, thora = pair()
    thora.eval('WoWStatusMainWindow.show')('records')
    thora.eval('WoWStatusMainWindow.show')('activity')
    thora.execute('table.insert(WoWStatusMainWindow.history(), {page="activity"})')
    assert thora.eval('WoWStatusMainWindow.canGoBack()') is True
    assert back_button(thora).IsShown(back_button(thora)) is True
    assert thora.eval('WoWStatusMainWindow.back()') is True
    assert thora.eval('WoWStatusMainWindow.active()') == 'records'
    assert history(thora) == []


def test_moving_between_pages_still_offers_back():
    _, thora = pair()
    thora.eval('WoWStatusMainWindow.show')('characters')
    thora.eval('WoWStatusMainWindow.show')('activity')
    assert thora.eval('WoWStatusMainWindow.canGoBack()') is True
    assert back_button(thora).IsShown(back_button(thora)) is True
    assert thora.eval('WoWStatusMainWindow.back()') is True
    assert thora.eval('WoWStatusMainWindow.active()') == 'characters'
