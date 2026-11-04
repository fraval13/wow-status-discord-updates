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


class CommunityTree(app_commands.CommandTree):
    async def interaction_check(self, interaction):
        if interaction.guild_id != self.client.guild_id:
            # Another instance of this bot may own that server; never race its response.
            return False
        remember(self.client.store, str(interaction.user.id), interaction.user.display_name)
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
            self.recover_sends()
            await sleep(delay)
            delay = min(delay * 2, DISCORD_RETRY_MAX)
            self.delivery_error = None

    def recover_sends(self):
        # Stopped mid-send: the message may or may not have posted.
        if self.store.recover_interrupted_sends():
            self.store.sync_archives()  # Archives show each delivery's status.

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
                self.recover_sends()
        finally:
            # A session is retried in the same process, so its HTTP session and
            # gateway must close even when the worker failed.
            await super().close()

    def visible(self):
        return [c for c in self.store.characters() if c['settings']['enabled']]

    def register_commands(self):
        @self.tree.command(name='link', description='Privately link your companion uploader')
        async def link(interaction: discord.Interaction):
            code = self.store.create_link(str(interaction.user.id))
            await interaction.response.send_message(
                'One-use code (expires in 10 minutes):\n' + f'`{code}`\n'
                'On your gaming computer open `wow-status desktop` and paste the code to link. '
                'You can also use `wow-status link --url YOUR_SERVICE_URL`. Keep the code private.', ephemeral=True)

        @self.tree.command(name='characters', description='List characters sharing with this server')
        async def characters(interaction: discord.Interaction):
            pages = roster_pages(self.store, self.visible())
            await interaction.response.send_message(pages[0], ephemeral=True)
            for page in pages[1:]:
                await interaction.followup.send(page, ephemeral=True)

        @self.tree.command(name='roster', description='Show friends, mains and alts with latest uploads')
        async def roster(interaction: discord.Interaction):
            pages = roster_pages(self.store, self.visible())
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
                nickname(self.store, str(interaction.user.id), None if reset else name)
            except ValueError:
                await interaction.response.send_message('Use a name of 1–40 characters.', ephemeral=True)
                return
            await interaction.response.send_message('Your display name preference is saved.', ephemeral=True)

        @self.tree.command(name='main', description='Choose your main character; your others become alts')
        async def main(interaction: discord.Interaction, name: str, realm: str = '', client: str = ''):
            matches = [c for c in self.store.characters(str(interaction.user.id))
                       if c['identity']['name'].casefold() == name.casefold()
                       and (not realm or c['identity']['realm'].casefold() == realm.casefold())
                       and (not client or c['identity']['client'].casefold() == client.casefold())]
            if len(matches) != 1:
                await interaction.response.send_message(
                    'Choose one of your Discord-linked characters, or mark your main in the addon for ID-joined groups.',
                    ephemeral=True)
                return
            set_role(self.store, str(interaction.user.id), matches[0]['id'], 'main')
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
            if mode:
                self.store.set_community_setting('immediate_mode', mode)
            self.store.set_community_setting('level_interval', str(level_interval))
            self.store.set_community_setting('loot_quality', str(loot_quality))
            await interaction.response.send_message(
                'Community posting filters saved. Collection history and personal privacy stay separate.',
                ephemeral=True)

        @self.tree.command(name='character', description='Show a last-uploaded character profile')
        async def character(interaction: discord.Interaction, name: str,
                            realm: str = '', client: str = ''):
            chars = [c for c in self.visible() if c['identity']['name'].casefold() == name.casefold()
                     and (not realm or c['identity']['realm'].casefold() == realm.casefold())
                     and (not client or c['identity']['client'].casefold() == client.casefold())]
            text = profile(decorate(self.store, chars[0])) if len(chars) == 1 else (
                'Several characters match. Specify realm and client.' if chars else 'No shared match.')
            await interaction.response.send_message(text, ephemeral=True)

        @self.tree.command(name='activity', description='Show recent shared character milestones')
        async def activity(interaction: discord.Interaction, name: str,
                           realm: str = '', client: str = ''):
            chars = [c for c in self.visible() if c['identity']['name'].casefold() == name.casefold()
                     and (not realm or c['identity']['realm'].casefold() == realm.casefold())
                     and (not client or c['identity']['client'].casefold() == client.casefold())]
            if len(chars) != 1:
                await interaction.response.send_message(
                    'Specify a unique shared name, realm and client.', ephemeral=True)
                return
            char = decorate(self.store, chars[0])
            lines = [announcement(dict(char, **event))
                     for event in self.store.activity(char['id'])[:8]]
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
                self.store.delete(owner)
                text = 'Stored characters, events, credentials and link codes deleted.'
            elif action == 'pause':
                self.store.pause(owner)
                with self.store.db:
                    self.store.db.execute('DELETE FROM installations WHERE owner=?', (owner,))
                    self.store.db.execute('DELETE FROM links WHERE owner=?', (owner,))
                text = ('Sharing paused, queued messages removed, uploader credentials revoked. '
                        'Pause the addon too. To resume, link again and export current settings.')
            else:
                lines = []
                for char in self.store.characters(owner):
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

    async def deliver(self):
        await self.wait_until_ready()
        last_schedule, last_recap = 0, 0
        while not self.is_closed():
            if time.time() - last_schedule > 30:
                self.recaps.schedule()
                self.weekly.schedule()
                self.standings.prepare()
                last_schedule = time.time()
            # A continuous upload backlog must not starve scheduled summaries.
            if time.time() - last_recap >= 60 and self.store.can_post():
                await self.deliver_recap()
                await self.deliver_recap(self.weekly)
                await self.deliver_standings()
                last_recap = time.time()
            item = self.store.pending(ready_only=True)
            if not item:
                await self.deliver_recap()
                await self.deliver_recap(self.weekly)
                await asyncio.sleep(2)
                continue
            delivery_id = item['delivery_id']
            items = self.store.summary_items(item)
            try:
                channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
                if getattr(getattr(channel, 'guild', None), 'id', None) != self.guild_id:
                    self.store.deliver_many(items, 'failed')
                    log.error('Announcement channel does not belong to configured server')
                    continue
                # Re-read after network await so privacy changes cancel pending messages.
                current = self.store.pending(ready_only=True)
                if current is None or current['delivery_id'] != delivery_id:
                    continue
                items = self.store.summary_items(current)
                if not items:
                    continue
                self.store.deliver_many(items, 'sending')
                content = (upload_summary(items, self.custom_emojis()) if current['settings'].get('discord_delivery') == 'summary'
                           else announcement_message(self.store, current, self.custom_emojis()))
                message = await channel.send(**content, allowed_mentions=discord.AllowedMentions.none())
                self.store.deliver_many(items, 'sent', message_id=str(message.id))
            except discord.Forbidden:
                self.store.deliver_many(items, 'failed')
                log.error('Discord denied channel access; fix permissions then resolve the delivery')
            except discord.HTTPException as exc:
                if exc.status == 429:
                    self.store.deliver_many(items, 'pending', delay=60)
                else:
                    self.store.deliver_many(items, 'uncertain' if exc.status >= 500 else 'failed')
            except (OSError, asyncio.TimeoutError):
                self.store.deliver_many(items, 'uncertain')
            await asyncio.sleep(1)

    async def deliver_recap(self, recaps=None):
        if not self.store.can_post():
            return
        recaps = recaps or self.recaps
        item = recaps.pending()
        if item is None:
            return
        key = item['key']
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            if getattr(getattr(channel, 'guild', None), 'id', None) != self.guild_id:
                recaps.delivery(key, 'failed')
                return
            # Refresh all content after awaits: data removal must also affect queued recaps.
            current = recaps.pending()
            if current is None or current['key'] != key:
                return
            self.store.reserve_post()
            recaps.delivery(key, 'sending')
            message = await channel.send(emoji('recap', self.custom_emojis()) + ' ' + current['text'],
                                         allowed_mentions=discord.AllowedMentions.none())
            recaps.delivery(key, 'sent', str(message.id))
        except discord.Forbidden:
            recaps.delivery(key, 'failed')
        except discord.HTTPException as exc:
            if exc.status == 429:
                recaps.delivery(key, 'pending', delay=60)
            else:
                recaps.delivery(key, 'uncertain' if exc.status >= 500 else 'failed')
        except (OSError, asyncio.TimeoutError):
            recaps.delivery(key, 'uncertain')

    async def deliver_standings(self):
        """One frozen cumulative report per group day; never a repeat of unchanged standings."""
        if not self.store.can_post():
            return
        item = self.standings.pending()
        if item is None:
            return
        key = item['key']
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            if getattr(getattr(channel, 'guild', None), 'id', None) != self.guild_id:
                self.standings.delivery(key, 'failed')
                log.error('Status channel does not belong to configured server')
                return
            # Re-read after the network await so a withdrawal cancels the unsent report.
            current = self.standings.pending()
            if current is None or current['key'] != key:
                return
            name = self.store.db.execute(
                "SELECT value FROM meta WHERE key='active_group_name'").fetchone()
            pages = daily_status_message(current['rows'], current['cutoff'],
                                         name['value'] if name else None, self.custom_emojis())
            self.store.reserve_post()
            self.standings.delivery(key, 'sending')
            sent = []
            for page in pages:
                message = await channel.send(**page, allowed_mentions=discord.AllowedMentions.none())
                sent.append(str(message.id))
            self.standings.delivery(key, 'sent', sent)
        except discord.Forbidden:
            self.standings.delivery(key, 'failed')
            log.error('Discord denied channel access for the daily status report')
        except discord.HTTPException as exc:
            if exc.status == 429:
                self.standings.delivery(key, 'pending', delay=60)
            else:
                self.standings.delivery(key, 'uncertain' if exc.status >= 500 else 'failed')
        except (OSError, asyncio.TimeoutError):
            self.standings.delivery(key, 'uncertain')

def session(store, guild_id, channel_id, token):
    """One Discord session per call, for ``server.run_discord`` to supervise."""
    async def bot(status):
        # A fresh client per session: a closed discord.py client can't restart.
        client = StatusBot(store, guild_id, channel_id)
        status['probe'] = client.state
        async with client:
            await client.start(token)
    return bot
