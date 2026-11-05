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

# An unsent post that failed in a way no handler expected is tried again after this
# long, while the rest of the queue goes ahead (#26).
UNEXPECTED_RETRY_SECONDS = DISCORD_RETRY_MAX


def expected(exc):
    """Failures the delivery handlers know: Discord's replies, network errors, timeouts."""
    return isinstance(exc, (discord.HTTPException, OSError, asyncio.TimeoutError))


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
        self.paused = {}  # Report kind -> when to try it again after a failure to render.
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
        """Re-read a delivery, build its message and mark it as sending, in one store call,
        so no upload or privacy change lands between the check and the mark."""
        current = self.store.pending(ready_only=True)
        if current is None or current['delivery_id'] != delivery_id:
            return None
        items = self.store.summary_items(current)
        if not items:
            return None
        # Built before the mark, so a formatting failure leaves the rows unsent, not sending.
        content = (upload_summary(items, emojis) if current['settings'].get('discord_delivery') == 'summary'
                   else announcement_message(self.store, current, emojis))
        self.store.deliver_many(items, 'sending')
        return items, content

    def failure(self, exc, claimed, what):
        """How a failed post is recorded, as (status, retry delay), or None to leave it.

        Before the claim nothing was sent, so a transient error requeues the post. After
        it, an unexplained failure may have posted the message: the supervisor's recovery
        marks it uncertain."""
        if isinstance(exc, discord.Forbidden):
            log.error('Discord denied channel access for the %s; fix permissions then '
                      'resolve it', what)
            return 'failed', 0
        if isinstance(exc, discord.HTTPException) and exc.status == 429:
            return 'pending', 60
        if isinstance(exc, discord.HTTPException) and exc.status < 500:
            return 'failed', 0
        if expected(exc):  # Discord server errors, network errors and timeouts.
            return ('uncertain', 0) if claimed else ('pending', 60)
        # Anything else, such as a formatting bug or a network error that is no OSError,
        # sets an unsent post aside, so the restarted loop goes on with the next one
        # instead of failing on the same post forever (#26).
        return None if claimed else ('pending', UNEXPECTED_RETRY_SECONDS)

    async def failed(self, exc, claimed, posted, mark, what):
        """Record a failed post with ``mark(status, delay)``. Anything no handler expects,
        and any failure to record a post that went out, then goes to keep_delivering,
        which logs it, shows it on /health, recovers a claimed send and backs off."""
        outcome = None if posted else self.failure(exc, claimed, what)
        if outcome is not None:
            await mark(*outcome)
        if posted or not expected(exc):
            raise exc

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
            items = await call(self.store.summary_items, item)
            claimed, posted = None, False
            try:
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
                posted = True
                await call(self.store.deliver_many, items, 'sent', message_id=str(message.id))
            except Exception as exc:
                await self.failed(exc, claimed is not None, posted, lambda status, delay: call(
                    self.store.deliver_many, items, status, delay=delay), 'announcement')
            await asyncio.sleep(1)

    async def queued(self, reports):
        """The next recap or status report to post, or None. Recaps are rendered while
        they are read, before there is a row to set aside, so a failure pauses that kind
        of report instead; otherwise the restarted loop would fail on it again before
        posting anything else (#26)."""
        if time.monotonic() < self.paused.get(reports, 0):
            return None
        try:
            return await self.store.call(reports.pending)
        except Exception:
            self.paused[reports] = time.monotonic() + UNEXPECTED_RETRY_SECONDS
            raise

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
        item = await self.queued(recaps)
        if item is None:
            return
        key, current, posted = item['key'], None, False
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            if getattr(getattr(channel, 'guild', None), 'id', None) != self.guild_id:
                await call(recaps.delivery, key, 'failed')
                return
            prefix = emoji('recap', self.custom_emojis()) + ' '  # Before the claim, as in claim().
            current = await call(self.claim_recap, recaps, key)
            if current is None:
                return
            message = await channel.send(prefix + current['text'],
                                         allowed_mentions=discord.AllowedMentions.none())
            posted = True
            await call(recaps.delivery, key, 'sent', str(message.id))
        except Exception as exc:
            await self.failed(exc, current is not None, posted, lambda status, delay: call(
                recaps.delivery, key, status, delay=delay), 'recap')

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
        item = await self.queued(self.standings)
        if item is None:
            return
        key, pages, posted = item['key'], None, False
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
            posted = True
            await call(self.standings.delivery, key, 'sent', sent)
        except Exception as exc:
            await self.failed(exc, pages is not None, posted, lambda status, delay: call(
                self.standings.delivery, key, status, delay=delay), 'daily status report')


def session(store, guild_id, channel_id, token):
    """One Discord session per call, for ``server.run_discord`` to supervise."""
    async def bot(status):
        # A fresh client per session: a closed discord.py client can't restart.
        client = StatusBot(store, guild_id, channel_id)
        status['probe'] = client.state
        async with client:
            await client.start(token)
    return bot
