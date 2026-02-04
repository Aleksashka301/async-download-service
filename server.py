import aiofiles
import argparse
import asyncio
import logging
import os

from aiohttp import web


parser = argparse.ArgumentParser()
parser.add_argument('--path', default='test_photos', help='Указать путь до директории с папками фото')
parser.add_argument('--delay', action='store_true', help='Включить задержку ответа')
parser.add_argument('--no_log', action='store_true', help='Отключить логирование')
args = parser.parse_args()

path_archives = args.path
CHUNK_SIZE = 400 * 1024


async def archive(request):
    archive_hash = request.match_info['archive_hash']

    if not os.path.exists(f'{path_archives}/{archive_hash}'):
        raise web.HTTPNotFound(text='Архив не существует или был удален')

    response = web.StreamResponse()
    response.headers['Content-Type'] = 'application/zip'
    response.headers["Content-Disposition"] = (
        f'attachment; filename="photos_{archive_hash}.zip"'
    )

    await response.prepare(request)

    process = await asyncio.create_subprocess_exec(
        'wsl', 'bash', '-c',
        f'cd "{path_archives}/{archive_hash}" && zip -r - .',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE
    )

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(
                    process.stdout.read(CHUNK_SIZE),
                    timeout=1
                )
            except asyncio.TimeoutError:
                if request.transport.is_closing():
                    break
                continue

            if not chunk:
                break

            logger.info('Sending archive chunk ...')

            try:
                await response.write(chunk)
            except (ConnectionResetError, ConnectionError):
                logger.warning('Client disconnected')
                break

            if args.delay:
                await asyncio.sleep(1)

    except asyncio.CancelledError:
        logger.warning('Task was cancelled')

    finally:
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.communicate(), timeout=3)
            except (ProcessLookupError, asyncio.TimeoutError):
                logger.warning('Zip did not stop gracefully, killing...')
                process.kill()
                await process.communicate()

    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r', encoding='utf-8') as index_file:
        index_contents = await index_file.read()

    return web.Response(text=index_contents, content_type='text/html')


if __name__ == '__main__':
    logging.basicConfig(
        format= u'%(filename)s [line:%(lineno)d]# %(levelname)s [%(asctime)s] - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)

    if args.no_log:
        logging.disable(logging.CRITICAL)

    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archive),
    ])
    web.run_app(app)
