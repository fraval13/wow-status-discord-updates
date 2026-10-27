"""Private-community HTTP ingestion service; localhost behind a TLS reverse proxy."""
import asyncio
import logging
import time
from collections import defaultdict, deque

from aiohttp import web

from .schema import ValidationError
from .store import Conflict

log = logging.getLogger(__name__)


def create_app(store):
    attempts = defaultdict(deque)

    @web.middleware
    async def errors(request, handler):
        try:
            return await handler(request)
        except Conflict as exc:
            return web.json_response({'error': str(exc)}, status=409)
        except (ValidationError, ValueError, KeyError, TypeError):
            return web.json_response({'error': 'Invalid request'}, status=400)
        except web.HTTPException:
            raise
        except Exception:
            # Request payloads and credentials must never appear in logs.
            log.error('Internal request failure; inspect server state')
            return web.json_response({'error': 'Internal error'}, status=500)

    app = web.Application(client_max_size=256_000, middlewares=[errors])

    def throttle(request):
        # Never trust forwarded IP headers supplied directly by clients.
        key = request.remote or 'unknown'
        queue = attempts[key]
        now = time.monotonic()
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= 120:
            raise web.HTTPTooManyRequests(headers={'Retry-After': '60'})
        queue.append(now)
        if len(attempts) > 4096:
            for ip in list(attempts):
                if not attempts[ip] or attempts[ip][-1] < now - 60:
                    del attempts[ip]

    async def health(request):
        return web.json_response({'status': 'ok', 'protocol': 1})

    async def redeem(request):
        throttle(request)
        body = await request.json()
        if not isinstance(body, dict):
            raise ValidationError('Expected an object')
        code = body.get('code')
        if not isinstance(code, str) or len(code) > 100:
            raise ValidationError('Invalid code')
        return web.json_response({'token': store.redeem(code)},
                                 headers={'Cache-Control': 'no-store'})

    async def ingest(request):
        throttle(request)
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer ') or len(header) > 200:
            raise web.HTTPUnauthorized()
        owner = store.owner(header[7:])
        if owner is None:
            raise web.HTTPUnauthorized()
        payload = await request.json()
        if store.owner(header[7:]) != owner:
            raise web.HTTPUnauthorized()
        return web.json_response(store.ingest(owner, payload))

    app.router.add_get('/health', health)
    app.router.add_post('/v1/link', redeem)
    app.router.add_post('/v1/upload', ingest)
    return app


async def serve(store, host, port, bot=None):
    runner = web.AppRunner(create_app(store), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, host, port).start()
        if bot:
            await bot()
        else:
            await asyncio.Event().wait()
    finally:
        await runner.cleanup()
