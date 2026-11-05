"""Guild-scoped commands, private linking and controlled outbox delivery."""
import asyncio
import logging
import time

import discord
from discord import app_commands

from .daily import DailyRecaps
from .formatting import announcement, fit_lines, profile, roster_pages, safe
from .group_status import GroupStatusReports
from .output import daily_status_message, emoji, upload_summary
from .output import message as announcement_message
from .people import decorate, nickname, remember, set_role
from .server import DISCORD_RETRY_FIRST, DISCORD_RETRY_MAX, failure_name
from .weekly import WeeklyRecaps

log = logging.getLogger(__name__)


def unexpected(exc):
    """Log a failure no handler expected, with its traceback, before delivery moves on."""
    log.exception('Discord delivery failed (%s); continuing with the next one',
                  failure_name(exc))


class CommunityTree(app_commands.CommandTree):
    async def interaction_check(self, interaction):
        if interaction.guild_id != self.client.guild_id:
            # Another instance of this bot may own that server; never race its response.
            return False
        store = self.client.store
        await store.call(remember, store, str(interaction.user.id), interaction.user.display_name)
        return True

    async def on_error(self, interaction, error):
        log.error('Discord command failed (%s)', type(error).__name__)
        send = interaction.followup.send if interaction.response.is_done() else \
            interaction.response.send_message
        await send('The command could not complete. Please try again later.', ephemeral=True)


class StatusBot(discord.Client):
    def __init__(self, store, guild_id, channel_id):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.emojis_and_stickers = True
        super().__init__(intents=intents,
                         allowed_mentions=discord.AllowedMentions.none())
        self.store, self.guild_id, self.channel_id = store, guild_id, channel_id
        self.recaps = DailyRecaps(store)
        self.standings = GroupStatusReports(store)
        self.weekly = WeeklyRecaps(store)
        self.tree = CommunityTree(self)
        self.worker = None
        self.delivery_error = None
        self.online = False
        self.register_commands()

    def custom_emojis(self):
        guild = self.get_guild(self.guild_id)
        return {e.name: str(e) for e in guild.emojis
                if e.available and not e.roles} if guild else {}

    async def setup_hook(self):
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.worker = asyncio.create_task(self.keep_delivering())

    async def keep_delivering(self, sleep=asyncio.sleep, clock=time.monotonic):
        """Restart a crashed delivery loop with backoff. The session, and with it the
        slash commands, stays up; /health shows the failure until delivery restarts."""
        delay = DISCORD_RETRY_FIRST
        while True:
            started = clock()
            try:
                await self.deliver()
                return  # The client closed.
            except Exception as exc:
                if clock() - started >= DISCORD_RETRY_MAX:
                    delay = DISCORD_RETRY_FIRST
                self.delivery_error = failure_name(exc)
                log.exception('Discord delivery failed (%s); restarting it in %d s',
                              self.delivery_error, delay)
            await self.recover_sends()
            await sleep(delay)
            delay = min(delay * 2, DISCORD_RETRY_MAX)
            self.delivery_error = None

    async def recover_sends(self):
        # Stopped mid-send: the message may or may not have posted.
        def recover():
            if self.store.recover_interrupted_sends():
                self.store.sync_archives()  # Archives show each delivery's status.
        await self.store.call(recover)

    async def on_ready(self):
        self.online = True

    async def on_resumed(self):
        self.online = True

    async def on_disconnect(self):
        self.online = False  # discord.py keeps is_ready() set while it reconnects.

    def state(self):
        """Health view of this session: None until logged in and the guild cache is ready."""
        if not self.is_ready():
            return None
        if not self.online:
            return {'discord': 'reconnecting'}
        if self.delivery_error:
            return {'discord': 'delivery_retrying', 'discord_error': self.delivery_error}
        return {'discord': 'ready'}

    async def close(self):
        try:
            if self.worker:
                self.worker.cancel()
                try:
                    await self.worker
                except asyncio.CancelledError:
                    pass
                await self.recover_sends()
        finally:
            # A session is retried in the same process, so its HTTP session and
            # gateway must close even when the worker failed.
            await super().close()

    def visible(self):
        return [c for c in self.store.characters() if c['settings']['enabled']]

    @staticmethod
    def matching(chars, name, realm, client):
        return [c for c in chars if c['identity']['name'].casefold() == name.casefold()
                and (not realm or c['identity']['realm'].casefold() == realm.casefold())
                and (not client or c['identity']['client'].casefold() == client.casefold())]

    def register_commands(self):
        # Store work runs through store.call: on the store thread while the service runs,
        # in order with uploads, so the event loop never waits for SQLite (#2).
        call = self.store.call

        @self.tree.command(name='link', description='Privately link your companion uploader')
        async def link(interaction: discord.Interaction):
            code = await call(self.store.create_link, str(interaction.user.id))
            await interaction.response.send_message(
                'One-use code (expires in 10 minutes):\n' + f'`{code}`\n'
                'On your gaming computer open `wow-status desktop` and paste the code to link. '
                'You can also use `wow-status link --url YOUR_SERVICE_URL`. Keep the code private.', ephemeral=True)

        @self.tree.command(name='characters', description='List characters sharing with this server')
        async def characters(interaction: discord.Interaction):
            pages = await call(lambda: roster_pages(self.store, self.visible()))
            await interaction.response.send_message(pages[0], ephemeral=True)
            for page in pages[1:]:
                await interaction.followup.send(page, ephemeral=True)

        @self.tree.command(name='roster', description='Show friends, mains and alts with latest uploads')
        async def roster(interaction: discord.Interaction):
            pages = await call(lambda: roster_pages(self.store, self.visible()))
            await interaction.response.send_message(pages[0], ephemeral=True)
            for page in pages[1:]:
                await interaction.followup.send(page, ephemeral=True)

        @self.tree.command(name='nickname', description='Choose your name for the roster and updates')
        async def choose_nickname(interaction: discord.Interaction, name: str = '', reset: bool = False):
            if not reset and not name.strip():
                await interaction.response.send_message(
                    'Enter a nickname, or reset:True to use your Discord display name.', ephemeral=True)
                return
            try:
                await call(nickname, self.store, str(interaction.user.id), None if reset else name)
            except ValueError:
                await interaction.response.send_message('Use a name of 1–40 characters.', ephemeral=True)
                return
            await interaction.response.send_message('Your display name preference is saved.', ephemeral=True)

        @self.tree.command(name='main', description='Choose your main character; your others become alts')
        async def main(interaction: discord.Interaction, name: str, realm: str = '', client: str = ''):
            owner = str(interaction.user.id)

            def choose():
                matches = self.matching(self.store.characters(owner), name, realm, client)
                if len(matches) == 1:
                    set_role(self.store, owner, matches[0]['id'], 'main')
                return len(matches) == 1
            if not await call(choose):
                await interaction.response.send_message(
                    'Choose one of your Discord-linked characters, or mark your main in the addon for ID-joined groups.',
                    ephemeral=True)
                return
            await interaction.response.send_message('Main character saved; your others are alts.',
                                                     ephemeral=True)

        @self.tree.command(name='settings', description='Set community announcements (Manage Server)')
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.choices(mode=[
            app_commands.Choice(name='Celebrations now; routine activity in recaps', value='celebrations'),
            app_commands.Choice(name='Daily and weekly recaps only', value='daily_only'),
            app_commands.Choice(name='Allow every individually selected announcement', value='all')])
        async def settings(interaction: discord.Interaction, mode: str = '',
                           level_interval: app_commands.Range[int, 1, 100] = 10,
                           loot_quality: app_commands.Range[int, 0, 5] = 4):
            if not interaction.permissions.manage_guild:
                await interaction.response.send_message('Manage Server is required.', ephemeral=True)
                return
            if mode and mode not in ('celebrations', 'daily_only', 'all'):
                await interaction.response.send_message('Unknown announcement mode.', ephemeral=True)
                return

            def save():
                if mode:
                    self.store.set_community_setting('immediate_mode', mode)
                self.store.set_community_setting('level_interval', str(level_interval))
                self.store.set_community_setting('loot_quality', str(loot_quality))
            await call(save)
            await interaction.response.send_message(
                'Community posting filters saved. Collection history and personal privacy stay separate.',
                ephemeral=True)

        @self.tree.command(name='character', description='Show a last-uploaded character profile')
        async def character(interaction: discord.Interaction, name: str,
                            realm: str = '', client: str = ''):
            def show():
                chars = self.matching(self.visible(), name, realm, client)
                return profile(decorate(self.store, chars[0])) if len(chars) == 1 else (
                    'Several characters match. Specify realm and client.' if chars else 'No shared match.')
            await interaction.response.send_message(await call(show), ephemeral=True)

        @self.tree.command(name='activity', description='Show recent shared character milestones')
        async def activity(interaction: discord.Interaction, name: str,
                           realm: str = '', client: str = ''):
            def recent():
                chars = self.matching(self.visible(), name, realm, client)
                if len(chars) != 1:
                    return None
                char = decorate(self.store, chars[0])
                return [announcement(dict(char, **event))
                        for event in self.store.activity(char['id'])[:8]]
            lines = await call(recent)
            if lines is None:
                await interaction.response.send_message(
                    'Specify a unique shared name, realm and client.', ephemeral=True)
                return
            await interaction.response.send_message(
                fit_lines(lines, 1900, '\n\n') or 'No recent shared activity.', ephemeral=True)

        @self.tree.command(name='privacy', description='Inspect, pause, unlink, or delete your data')
        @app_commands.choices(action=[
            app_commands.Choice(name='Show my sharing settings', value='show'),
            app_commands.Choice(name='Pause all sharing and revoke uploaders', value='pause'),
            app_commands.Choice(name='Delete my stored data and unlink uploaders', value='delete')])
        async def privacy(interaction: discord.Interaction, action: str = 'show', confirm: bool = False):
            owner = str(interaction.user.id)
            if action not in ('show', 'pause', 'delete'):
                await interaction.response.send_message('Unknown privacy action.', ephemeral=True)
                return
            if action == 'delete' and not confirm:
                await interaction.response.send_message(
                    'Run `/privacy action:delete confirm:True` to delete stored data and credentials. '
                    'Historical Discord posts are not deleted. Disable the addon first; '
                    'a future enrollment can introduce the character again.', ephemeral=True)
                return
            if action == 'delete':
                await call(self.store.delete, owner)
                text = 'Stored characters, events, credentials and link codes deleted.'
            elif action == 'pause':
                def pause():
                    # One store call, so no upload with the old credentials lands between.
                    self.store.pause(owner)
                    with self.store.db:
                        self.store.db.execute('DELETE FROM installations WHERE owner=?', (owner,))
                        self.store.db.execute('DELETE FROM links WHERE owner=?', (owner,))
                await call(pause)
                text = ('Sharing paused, queued messages removed, uploader credentials revoked. '
                        'Pause the addon too. To resume, link again and export current settings.')
            else:
                lines = []
                for char in await call(self.store.characters, owner):
                    settings = char['settings']
                    fields = ', '.join(k for k, v in settings['fields'].items() if v) or 'none'
                    events = ', '.join(k for k, v in settings['announcements'].items() if v) or 'none'
                    collected = ', '.join(k for k, v in settings['collection'].items() if v) or 'none'
                    lines.append(f"{safe(char['identity']['name'])}: sharing={settings['enabled']}; "
                                 f'profile: {fields}; stored: {collected}; announcements: {events}')
                notice = (
                    '\nFor ID-joined groups, use the companion’s group privacy controls; no Discord link is needed. '
                    'Identity (name, realm, client, GUID) is required for enrollment. '
                    'Consented history is retained in structured per-character JSON until deletion. '
                    'Stored events also feed daily recaps at 00:05 Europe/Oslo. '
                    'Historical Discord messages remain after deletion.')
                # Cut whole character lines so the retention notice is never dropped.
                text = (fit_lines(lines, 1900 - len(notice)) if lines else 'No uploaded characters.') + notice
            await interaction.response.send_message(text, ephemeral=True)

    def schedule(self):
        self.store.expire_incomplete_batches()
        self.recaps.schedule()
        self.weekly.schedule()
        self.standings.prepare()

    def claim(self, delivery_id, emojis):
        """Re-read a delivery and mark it as sending, in one store call, so no upload or
        privacy change lands between the check and the mark; then build its message."""
        current = self.store.pending(ready_only=True)
        if current is None or current['delivery_id'] != delivery_id:
            return None
        items = self.store.summary_items(current)
        if not items:
            return None
        # Built before the mark, so a formatting failure never leaves rows marked as sending.
        content = (upload_summary(items, emojis) if current['settings'].get('discord_delivery') == 'summary'
                   else announcement_message(self.store, current, emojis))
        self.store.deliver_many(items, 'sending')
        return items, content

    async def deliver(self):
        await self.wait_until_ready()
        call = self.store.call
        last_schedule, last_recap = 0, 0
        while not self.is_closed():
            if time.time() - last_schedule > 30:
                await call(self.schedule)
                last_schedule = time.time()
            # A continuous upload backlog must not starve scheduled summaries.
            if time.time() - last_recap >= 60 and await call(self.store.can_post):
                await self.deliver_recap()
                await self.deliver_recap(self.weekly)
                await self.deliver_standings()
                last_recap = time.time()
            item = await call(self.store.pending, ready_only=True)
            if not item:
                await self.deliver_recap()
                await self.deliver_recap(self.weekly)
                await asyncio.sleep(2)
                continue
            delivery_id = item['delivery_id']
            items, claimed = [item], None
            try:
                items = await call(self.store.summary_items, item)
                channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
                if getattr(getattr(channel, 'guild', None), 'id', None) != self.guild_id:
                    await call(self.store.deliver_many, items, 'failed')
                    log.error('Announcement channel does not belong to configured server')
                    continue
                # Re-read after network await so privacy changes cancel pending messages.
                claimed = await call(self.claim, delivery_id, self.custom_emojis())
                if claimed is None:
                    continue
                items, content = claimed
                message = await channel.send(**content, allowed_mentions=discord.AllowedMentions.none())
                await call(self.store.deliver_many, items, 'sent', message_id=str(message.id))
            except discord.Forbidden:
                await call(self.store.deliver_many, items, 'failed')
                log.error('Discord denied channel access; fix permissions then resolve the delivery')
            except discord.HTTPException as exc:
                if exc.status == 429:
                    await call(self.store.deliver_many, items, 'pending', delay=60)
                else:
                    await call(self.store.deliver_many, items,
                               'uncertain' if exc.status >= 500 else 'failed')
            except (OSError, asyncio.TimeoutError):
                await call(self.store.deliver_many, items, 'uncertain')
            except Exception as exc:
                # Anything else, such as a formatting bug or an unexpected network error,
                # costs this delivery only. Without this the worker would restart and pick
                # the same delivery again, so one bad row would stop every post (#26). Once
                # claimed, the message may have posted.
                unexpected(exc)
                await call(self.store.deliver_many, items,
                           'failed' if claimed is None else 'uncertain')
            await asyncio.sleep(1)

    def claim_recap(self, recaps, key):
        """Refresh a recap after awaits and mark it as sending, in one store call: data
        removal must also affect queued recaps."""
        current = recaps.pending()
        if current is None or current['key'] != key:
            return None
        self.store.reserve_post()
        recaps.delivery(key, 'sending')
        return current

    async def deliver_recap(self, recaps=None):
        call = self.store.call
        if not await call(self.store.can_post):
            return
        recaps = recaps or self.recaps
        item = await call(recaps.pending)
        if item is None:
            return
        key, current = item['key'], None
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            if getattr(getattr(channel, 'guild', None), 'id', None) != self.guild_id:
                await call(recaps.delivery, key, 'failed')
                return
            current = await call(self.claim_recap, recaps, key)
            if current is None:
                return
            message = await channel.send(emoji('recap', self.custom_emojis()) + ' ' + current['text'],
                                         allowed_mentions=discord.AllowedMentions.none())
            await call(recaps.delivery, key, 'sent', str(message.id))
        except discord.Forbidden:
            await call(recaps.delivery, key, 'failed')
        except discord.HTTPException as exc:
            if exc.status == 429:
                await call(recaps.delivery, key, 'pending', delay=60)
            else:
                await call(recaps.delivery, key, 'uncertain' if exc.status >= 500 else 'failed')
        except (OSError, asyncio.TimeoutError):
            await call(recaps.delivery, key, 'uncertain')
        except Exception as exc:  # As in deliver(): one bad recap must not stop every post.
            unexpected(exc)
            await call(recaps.delivery, key, 'failed' if current is None else 'uncertain')

    def claim_standings(self, key, emojis):
        """Re-read the report and mark it as sending, in one store call, so a withdrawal
        cancels the unsent report; then build its pages."""
        current = self.standings.pending()
        if current is None or current['key'] != key:
            return None
        name = self.store.db.execute(
            "SELECT value FROM meta WHERE key='active_group_name'").fetchone()
        pages = daily_status_message(current['rows'], current['cutoff'],
                                     name['value'] if name else None, emojis)
        self.store.reserve_post()
        self.standings.delivery(key, 'sending')
        return pages

    async def deliver_standings(self):
        """One frozen cumulative report per group day; never a repeat of unchanged standings."""
        call = self.store.call
        if not await call(self.store.can_post):
            return
        item = await call(self.standings.pending)
        if item is None:
            return
        key, pages = item['key'], None
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            if getattr(getattr(channel, 'guild', None), 'id', None) != self.guild_id:
                await call(self.standings.delivery, key, 'failed')
                log.error('Status channel does not belong to configured server')
                return
            # Re-read after the network await so a withdrawal cancels the unsent report.
            pages = await call(self.claim_standings, key, self.custom_emojis())
            if pages is None:
                return
            sent = []
            for page in pages:
                message = await channel.send(**page, allowed_mentions=discord.AllowedMentions.none())
                sent.append(str(message.id))
            await call(self.standings.delivery, key, 'sent', sent)
        except discord.Forbidden:
            await call(self.standings.delivery, key, 'failed')
            log.error('Discord denied channel access for the daily status report')
        except discord.HTTPException as exc:
            if exc.status == 429:
                await call(self.standings.delivery, key, 'pending', delay=60)
            else:
                await call(self.standings.delivery, key, 'uncertain' if exc.status >= 500 else 'failed')
        except (OSError, asyncio.TimeoutError):
            await call(self.standings.delivery, key, 'uncertain')
        except Exception as exc:  # As in deliver(): one bad report must not stop every post.
            unexpected(exc)
            await call(self.standings.delivery, key, 'failed' if pages is None else 'uncertain')


def session(store, guild_id, channel_id, token):
    """One Discord session per call, for ``server.run_discord`` to supervise."""
    async def bot(status):
        # A fresh client per session: a closed discord.py client can't restart.
        client = StatusBot(store, guild_id, channel_id)
        status['probe'] = client.state
        async with client:
            await client.start(token)
    return bot
