import aiofiles
import asyncio
import logging
import os

from aiohttp import web


CHUNK_SIZE = 400 * 1024
PHOTOS_DIR = 'test_photos'


async def archive(request):
    archive_hash = request.match_info['archive_hash']

    response = web.StreamResponse()
    response.headers['Content-Type'] = 'application/zip'
    response.headers["Content-Disposition"] = (
        f'attachment; filename="photos_{archive_hash}.zip"'
    )

    if not os.path.exists(f'{PHOTOS_DIR}/{archive_hash}'):
        raise web.HTTPNotFound(text='Архив не существует или был удален')

    await response.prepare(request)

    process = await asyncio.create_subprocess_exec(
        'wsl', 'bash', '-c',
        f'cd "{PHOTOS_DIR}/{archive_hash}" && zip -r - .',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    try:
        while True:
            chunk = await process.stdout.read(CHUNK_SIZE)
            if not chunk:
                break

            logger.info('Sending archive chunk ...')
            await response.write(chunk)

    except (ConnectionResetError, asyncio.CancelledError):
        logger.warning('Download was interrupted')

    finally:
        logger.info('Stopping zip process...')
        if process.returncode is None:
            process.kill()
            await process.wait()
        logger.info('Zip process stopped')

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

    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archive),
    ])
    web.run_app(app)
