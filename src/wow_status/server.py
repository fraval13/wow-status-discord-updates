"""Private-community HTTP ingestion service; localhost behind a TLS reverse proxy."""
import asyncio
import hmac
import ipaddress
import logging
import os
import secrets
import time

from aiohttp import web

from . import journal_relay, limits
from .group_routing import canonical_group, group_key, group_label
from .group_routing import group_id as validate_group_id
from .people import remember
from .schema import ValidationError, string
from .store import Conflict

log = logging.getLogger(__name__)

# One IPv6 host or home network controls at least a whole /64, so throttling
# individual IPv6 addresses would give it effectively unlimited budgets.
IPV6_THROTTLE_PREFIX = 64
# Stateless translation prefixes carrying an IPv4 client in the low 32 bits:
# RFC 6052 well-known NAT64 and RFC 2765 SIIT IPv4-translated addresses.
IPV4_TRANSLATION_PREFIXES = (ipaddress.ip_network('64:ff9b::/96'),
                             ipaddress.ip_network('::ffff:0:0:0/96'))


def _embedded_ipv4(ip):
    """IPv4 address carried by a translated or tunnelled IPv6 address, if any."""
    if any(ip in prefix for prefix in IPV4_TRANSLATION_PREFIXES):
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip.sixtofour is not None:
        return ip.sixtofour  # The site's 6to4 router, which owns 2002:V4::/48.
    if ip.teredo is not None:
        return ip.teredo[1]
    return None


def throttle_identity(address):
    """Return the per-source throttle identity for a client address.

    IPv4 and IPv4-mapped addresses key on the IPv4 address. NAT64, SIIT, 6to4
    and Teredo addresses key on their embedded global IPv4 address, or on the
    exact address when that IPv4 is not global. Loopback and unspecified IPv6
    keep their exact address. Other IPv6 addresses collapse to their /64
    network. Non-IP values pass through.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    if ip.is_loopback or ip.is_unspecified:
        return str(ip)
    embedded = _embedded_ipv4(ip)
    if embedded is not None:
        # A translator or relay owns the surrounding /64, not the client, and
        # non-global values must not become loopback/private IPv4 keys.
        return str(embedded) if embedded.is_global else str(ip)
    return str(ipaddress.ip_network((ip, IPV6_THROTTLE_PREFIX), strict=False))


# A failed Discord session is retried after this many seconds, doubling up to the cap.
# At most 144 session starts a day stays far below Discord's daily budget of 1,000,
# which a 10-second restart loop would exhaust (Discord then resets the token).
DISCORD_RETRY_FIRST = 30
DISCORD_RETRY_MAX = 600


def discord_state(status):
    """Health view of the Discord bot: no credentials, messages or user data."""
    if status is None:
        return {'discord': 'disabled'}
    probe = status.get('probe')
    live = probe() if probe is not None else None
    if live:
        return live
    report = {'discord': status.get('state', 'starting')}
    if status.get('error'):
        report['discord_error'] = status['error']
    return report


def failure_name(exc):
    """Exception class plus Discord's HTTP status and error code, when it has them."""
    if not type(exc).__module__.startswith('discord'):
        return type(exc).__name__  # e.g. aiohttp's deprecated `code` alias of `status`
    details = [str(value) for value in (getattr(exc, 'status', None), getattr(exc, 'code', None))
               if isinstance(value, int)]
    return ' '.join([type(exc).__name__] + details)


async def run_discord(bot, status, first=DISCORD_RETRY_FIRST, cap=DISCORD_RETRY_MAX,
                      sleep=asyncio.sleep, clock=time.monotonic):
    """Run the bot until cancelled. Its failures never stop ingestion: they are logged,
    shown on /health and retried with backoff, instead of exiting the whole service."""
    delay = first
    while True:
        status.update(state='starting', probe=None)
        status.pop('error', None)
        started = clock()
        failure = None
        try:
            await bot(status)
        except Exception as exc:  # Any bot failure must leave ingestion running.
            failure = exc
        if clock() - started >= cap:
            delay = first  # A long healthy session earns a quick reconnect.
        error = failure_name(failure) if failure else 'Stopped'
        status.update(state='retrying', probe=None, error=error)
        # The traceback names discord.py frames and Discord's reply, never the token.
        log.error('Discord bot stopped (%s); ingestion continues, retrying in %d s', error, delay,
                  exc_info=failure)
        await sleep(delay)
        delay = min(delay * 2, cap)


def create_app(store, group=None, name=None, trust_proxy=False, discord=None):
    if group is not None:
        group = validate_group_id(group)
        previous = store.db.execute("SELECT value FROM meta WHERE key='active_group_id'").fetchone()
        if previous and previous['value'] != group:
            raise ValueError('Use a separate database for each group')
        with store.db:
            store.db.execute("INSERT OR REPLACE INTO meta VALUES('active_group_id',?)", (group,))
        if name is not None:
            name = group_label(name)
            if group_key(name) != group:
                raise ValueError('Group name does not match group key')
            previous_name = store.db.execute("SELECT value FROM meta WHERE key='active_group_name'").fetchone()
            if previous_name and canonical_group(previous_name['value']) != canonical_group(name):
                raise ValueError('Group name collision: use a different database/name')
            with store.db:
                store.db.execute("INSERT OR REPLACE INTO meta VALUES('active_group_name',?)", (name,))

    @web.middleware
    async def errors(request, handler):
        try:
            if request.method == 'POST' and request.content_type != 'application/json':
                raise web.HTTPUnsupportedMediaType()
            return await handler(request)
        except limits.Limited as exc:
            return web.json_response({'error': 'Temporarily limited; retry retained data'}, status=429,
                                     headers={'Retry-After': str(exc.retry_after)})
        except Conflict as exc:
            return web.json_response({'error': str(exc)}, status=409)
        except (ValidationError, ValueError, KeyError, TypeError, RecursionError, OverflowError):
            return web.json_response({'error': 'Invalid request'}, status=400)
        except web.HTTPException:
            raise
        except Exception:
            # Request payloads and credentials must never appear in logs.
            log.error('Internal request failure; inspect server state')
            return web.json_response({'error': 'Internal error'}, status=500)

    app = web.Application(client_max_size=256_000, middlewares=[errors])

    async def background(app):
        # While the service runs, SQLite work and archive rebuilds happen on the store and
        # archive threads, so a large upload never stalls /health or the Discord bot (#2).
        store.start_background()
        # The one full rebuild at startup (new code or a renamed group), on the archive thread.
        await store.call(store.sync_archives)
        yield
        await store.stop_background_from_loop()

    app.cleanup_ctx.append(background)

    def client_ip(request):
        # Only an explicitly trusted local reverse proxy may supply this header.
        remote = request.remote or 'unknown'
        if trust_proxy and remote in ('127.0.0.1', '::1'):
            forwarded = request.headers.get('X-WoW-Client-IP', '')
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
        return remote

    def address_scope(request, operation):
        return operation + ':' + store.digest(throttle_identity(client_ip(request)))

    async def throttle(request, operation, count, seconds):
        await store.call(store.request_budget, address_scope(request, operation), count, seconds)

    def authenticated_budget(owner, operation):
        count = limits.PRIVACY_PER_MINUTE if operation == 'privacy' else limits.UPLOADS_PER_MINUTE
        store.request_budget(operation + ':' + owner, count, 60)

    async def health(request):
        return web.json_response({'status': 'ok', 'protocol': 1, 'service': 'wow-character-status',
                                  'revision': os.environ.get('WOW_STATUS_REVISION'),
                                  **discord_state(discord)})

    async def redeem(request):
        await throttle(request, 'link', limits.AUTH_FAILURES_PER_IP_MINUTE, 60)
        body = await request.json()
        if not isinstance(body, dict):
            raise ValidationError('Expected an object')
        code = body.get('code')
        if not isinstance(code, str) or len(code) > 100:
            raise ValidationError('Invalid code')
        return web.json_response({'token': await store.call(store.redeem, code)},
                                 headers={'Cache-Control': 'no-store'})

    def correct_group(request):
        value = request.headers.get('X-WoW-Group', '')
        return group is not None and hmac.compare_digest(value.encode(), group.encode())

    async def enroll_group(request):
        await throttle(request, 'enroll', limits.ENROLLMENTS_PER_IP_HOUR, 3600)
        if not correct_group(request):
            raise web.HTTPForbidden()
        body = await request.json()
        if not isinstance(body, dict) or body.get('group_id') != group:
            raise ValidationError('Wrong group')
        if name is not None and canonical_group(body.get('group_name')) != canonical_group(name):
            raise web.HTTPForbidden()
        owner = 'group:' + secrets.token_urlsafe(12)
        player = body.get('player_name') or ('Friend ' + owner[-6:])
        string(player, 'player name', 40)

        def enroll():
            store.request_budget('enroll:group', limits.ENROLLMENTS_PER_GROUP_DAY, 86400)
            token = store.redeem(store.create_link(owner))
            remember(store, owner, player, source='addon' if body.get('player_name') else 'unavailable')
            return token
        return web.json_response({'token': await store.call(enroll), 'owner': owner},
                                 headers={'Cache-Control': 'no-store'})

    async def authenticate(request, operation):
        """The installation owner and token, with the owner's request budget charged."""
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer ') or len(header) > 200:
            await throttle(request, 'invalid-auth', limits.AUTH_FAILURES_PER_IP_MINUTE, 60)
            raise web.HTTPUnauthorized()
        if group is not None and not correct_group(request):
            raise web.HTTPForbidden()

        failures = address_scope(request, 'invalid-auth')

        def lookup():
            owner = store.owner(header[7:])
            if owner is None:
                store.request_budget(failures, limits.AUTH_FAILURES_PER_IP_MINUTE, 60)
            else:
                authenticated_budget(owner, operation)
            return owner
        owner = await store.call(lookup)
        if owner is None:
            raise web.HTTPUnauthorized()
        return owner, header[7:]

    async def privacy(request):
        if group is None:
            raise web.HTTPNotFound()
        owner, token = await authenticate(request, 'privacy')
        body = await request.json()
        action = body.get('action') if isinstance(body, dict) else None

        def apply():
            # Re-checked in the same store call as the change, so a credential revoked
            # while the body arrived can't act.
            if store.owner(token) != owner:
                raise web.HTTPUnauthorized()
            if action == 'pause':
                store.pause(owner)
                with store.db:
                    store.db.execute('INSERT OR IGNORE INTO group_pauses VALUES(?)', (owner,))
            elif action == 'resume':
                with store.db:
                    store.db.execute('DELETE FROM group_pauses WHERE owner=?', (owner,))
            elif action == 'delete':
                store.delete(owner)
            else:
                raise ValidationError('Invalid privacy action')
        await store.call(apply)
        return web.json_response({'status': action})

    async def ingest(request):
        owner, token = await authenticate(request, 'upload')
        payload = await request.json()

        def upload():
            # One store call from the credential check to the stored upload, so a pause,
            # deletion or revocation is either fully before it or fully after it.
            if store.owner(token) != owner:
                raise web.HTTPUnauthorized()
            label = None
            if group is not None:
                if not isinstance(payload, dict) or payload.get('group_id') != group:
                    raise ValidationError('Wrong group')
                if name is not None and canonical_group(payload.get('group_name', name)) != canonical_group(name):
                    raise web.HTTPForbidden()
                if store.paused(owner):
                    raise web.HTTPForbidden()
                if 'player_name' in payload:
                    player = payload['player_name']
                    if not isinstance(player, str):
                        raise ValidationError('Invalid player name')
                    # Stored by ingest only once the whole upload is accepted (#10).
                    label = ((string(player, 'player name', 40), 'addon') if player
                             else ('Friend ' + owner[-6:], 'unavailable'))
            return store.ingest(owner, payload, name=label)
        return web.json_response(await store.call(upload))

    async def journal(request):
        # The shared-journal relay (#49) exists only for group destinations.
        if group is None:
            raise web.HTTPNotFound()
        owner, token = await authenticate(request, 'upload')
        payload = await request.json()

        def upload():
            if store.owner(token) != owner:
                raise web.HTTPUnauthorized()
            if not isinstance(payload, dict) or payload.get('group_id') != group:
                raise ValidationError('Wrong group')
            if store.paused(owner):
                raise web.HTTPForbidden()
            return journal_relay.ingest(store, owner, payload)
        return web.json_response(await store.call(upload))

    app.router.add_get('/health', health)
    app.router.add_post('/v1/link', redeem)
    app.router.add_post('/v1/group-enroll', enroll_group)
    app.router.add_post('/v1/privacy', privacy)
    app.router.add_post('/v1/upload', ingest)
    app.router.add_post('/v1/journal', journal)
    return app


async def serve(store, host, port, bot=None, group=None, name=None, trust_proxy=False):
    """Serve ingestion; ``bot(status)``, if given, runs one Discord session per call."""
    status = {} if bot else None
    runner = web.AppRunner(create_app(store, group, name, trust_proxy, discord=status),
                           access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, host, port).start()
        if bot:
            await run_discord(bot, status)
        else:
            await asyncio.Event().wait()
    finally:
        await runner.cleanup()
