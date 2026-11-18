"""Labs: seasonal captions during holidays (#242)."""
import pytest

from test_addon import make_lua


@pytest.mark.parametrize('day,name', [
    ('10-31', 'hallows'), ('12-25', 'winterveil'), ('01-01', 'winterveil'), ('01-30', 'lunar'),
    ('02-14', 'love'), ('06-15', None), ('03-01', None), ('12-14', None),
])
def test_the_right_holiday_on_a_given_date(day, name):
    lua = make_lua()
    assert lua.eval(f'(WoWStatusFlavour.holiday("{day}"))') == name


def seasonal_count(lua, day):
    lua.execute(f'''
        WoWStatusFeatures.init(WoWStatusDB)
        WoWStatusFeatures.set("seasonal", true)
        local real=WoWStatusFlavour.holiday
        WoWStatusFlavour.holiday=function() return real("{day}") end
        __season={{}}
        local _,captions=real("{day}")
        if captions then for _,c in ipairs(captions) do __season[c]=true end end
        __count=0
        for i=1,140 do
            local item={{kind="level",level=10,sender="Mira-TestRealm",nonce="1-"..i}}
            local text=WoWStatusFlavour.text(item)
            if __season[text] then __count=__count+1 end
        end
    ''')
    return lua.eval('__count')


def test_some_captions_turn_festive_on_a_holiday_only_and_only_when_switched_on():
    lua = make_lua()
    assert 5 <= seasonal_count(lua, '12-25') <= 60
    assert seasonal_count(make_lua(), '06-15') == 0
    off = make_lua()
    off.execute('''
        local real=WoWStatusFlavour.holiday
        WoWStatusFlavour.holiday=function() return real("12-25") end
        __n=0
        local _,captions=real("12-25")
        for i=1,60 do
            local text=WoWStatusFlavour.text({kind="level",level=10,sender="Mira-TestRealm",nonce="1-"..i})
            for _,c in ipairs(captions) do if text==c then __n=__n+1 end end
        end
    ''')
    assert off.eval('__n') == 0


def test_nynorsk_has_every_seasonal_caption():
    lua = make_lua()
    for day in ('10-31', '12-25', '01-30', '02-14'):
        assert lua.eval(f'''(function()
            local _,captions=WoWStatusFlavour.holiday("{day}")
            for _,c in ipairs(captions) do if not WoWStatusLocale.NN[c] then return c end end
            return true end)()''') is True
