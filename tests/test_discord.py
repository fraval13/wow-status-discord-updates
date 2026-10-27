import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from wow_status.discord_bot import StatusBot
from wow_status.formatting import announcement


def test_mentions_and_private_fields_never_enter_introduction(store, payload):
    payload['identity']['name'] = '@everyone'
    store.ingest('owner', payload)
    message = announcement(store.pending())
    assert '@everyone' not in message
    assert 'PRIVATE' not in message


async def test_commands_are_guild_scoped_and_need_no_message_content(store):
    bot = StatusBot(store, 123, 456)
    try:
        assert bot.intents.message_content is False
        assert {c.name for c in bot.tree.get_commands()} == {
            'link', 'characters', 'character', 'activity', 'privacy'}
        interaction = SimpleNamespace(guild_id=999,
                                      response=SimpleNamespace(send_message=AsyncMock()))
        assert await bot.tree.interaction_check(interaction) is False
        interaction.response.send_message.assert_awaited_once()
    finally:
        await bot.close()


async def test_deleting_data_during_channel_fetch_cancels_delivery(store, payload):
    store.ingest('owner', payload)
    bot = StatusBot(store, 123, 456)
    channel = SimpleNamespace(guild=SimpleNamespace(id=123), send=AsyncMock())
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = lambda _: None

    async def fetch(_):
        store.delete('owner')
        return channel

    bot.fetch_channel = fetch
    task = asyncio.create_task(bot.deliver())
    try:
        await asyncio.sleep(0.05)
        channel.send.assert_not_awaited()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await bot.close()
