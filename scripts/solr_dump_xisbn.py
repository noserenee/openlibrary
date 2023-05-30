"""
    Script for creating a file of similar ISBNs from Solr.
"""
import asyncio
import sys

import httpx

# EG http://localhost:8984/solr/openlibrary/export?editions.fl=key%2Cisbn&editions.q=(%7B!terms%20f%3D_root_%20v%3D%24row.key%7D)%20AND%20language%3Aeng%20AND%20isbn%3A*%20AND%20type%3Aedition&editions.rows=1000000&fl=key%2Ceditions%3A%5Bsubquery%5D&fq=type%3Awork&indent=true&q.op=OR&q=isbn%3A*%20AND%20NOT%20subject%3Atextbook%20AND%20_query_%3A(%7B!parent%20which%3Dtype%3Awork%20v%3D%22language%3Aeng%20AND%20ia_box_id%3A*%22%20filters%3D%22type%3Aedition%22%7D)&sort=key%20asc&wt=json


async def fetch_docs(params: dict[str, str | int], solr_base: str, page_size=100):
    """Stream results from a Solr query. Uses cursors."""
    params = params.copy()
    params['rows'] = page_size

    async with httpx.AsyncClient() as client:
        for attempt in range(5):
            try:
                response = await client.get(
                    f'{solr_base}/select',
                    params=params,
                    timeout=60,
                )
                response.raise_for_status()
                break
            except (httpx.RequestError, httpx.HTTPStatusError):
                if attempt == 4:
                    raise
                await asyncio.sleep(2)
        data = response.json()
        return data['response']['docs']


async def stream_bounds(params: dict[str, str | int], solr_base: str, page_size=100):
    """Stream bounds from a Solr query. Uses cursors."""
    params = params.copy()
    params['rows'] = page_size
    params['cursorMark'] = '*'
    numFound = None
    seen = 0

    # Keep session open and retry on connection errors
    transport = httpx.AsyncHTTPTransport()
    async with httpx.AsyncClient(transport=transport) as client:
        while True:
            print(f'FETCH {params["cursorMark"]}', file=sys.stderr)
            if numFound:
                print(f'{seen/numFound=}', file=sys.stderr)

            for attempt in range(5):
                try:
                    response = await client.get(
                        f'{solr_base}/select',
                        params=params,
                        timeout=60,
                    )
                    response.raise_for_status()
                    break
                except (httpx.RequestError, httpx.HTTPStatusError):
                    if attempt == 4:
                        raise
                    await asyncio.sleep(2)
            data = response.json()
            numFound = data['response']['numFound']
            seen += page_size
            yield data['response']['docs'][0]['key'], data['response']['docs'][-1][
                'key'
            ]
            if data['nextCursorMark'] == params['cursorMark']:
                break
            params['cursorMark'] = data['nextCursorMark']


async def main(
    solr_base='http://localhost:8984/solr/openlibrary',
    workers=10,
    page_size=100,
):
    """
    :param solr_base: Base URL of Solr instance
    :param workers: Number of workers to use
    :param page_size: Number of results to fetch per query
    """
    galloping_params = {
        'q': 'isbn:* AND NOT subject:textbook AND _query_:({!parent which=type:work v="language:eng AND ia_box_id:*" filters="type:edition"})',
        'fq': 'type:work',
        'sort': 'key asc',
        'fl': 'key',
        'wt': 'json',
    }

    # This is a performance hack
    # this returns pairs like ('/works/OL1W', '/works/OL200W'), ('/works/OL201W', '/works/OL300W')
    # which we can use to make multiple queries in parallel

    # Now create an async worker pool to fetch the actual data
    async def fetch_bounds(bounds):
        print(f'[ ] FETCH {bounds=}', file=sys.stderr)
        start, end = bounds
        result = ''
        for doc in await fetch_docs(
            {
                'q': f'key:["{start}" TO "{end}"] AND {galloping_params["q"]}',
                'fq': 'type:work',
                'fl': 'key,editions:[subquery]',
                'editions.q': '({!terms f=_root_ v=$row.key}) AND language:eng AND isbn:*',
                'editions.fq': 'type:edition',
                'editions.fl': 'key,isbn',
                'editions.rows': 1_000_000,
                'wt': 'json',
            },
            solr_base,
            page_size=page_size * 2,
        ):
            isbns = {
                isbn
                for ed in doc['editions']['docs']
                for isbn in ed['isbn']
                if len(isbn) == 13
            }
            if len(isbns) > 1:
                result += ' '.join(isbns) + '\n'
        print(f'[x] FETCH {bounds=}', file=sys.stderr)
        print(result, flush=True)

    # now run 10 workers in async pool to process the bounds
    running = set()
    async for bounds in stream_bounds(galloping_params, solr_base, page_size=page_size):
        if len(running) >= workers:
            done, running = await asyncio.wait(
                running, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task.result()
        running.add(asyncio.create_task(fetch_bounds(bounds)))

    # wait for all workers to finish
    await asyncio.wait(running)


if __name__ == '__main__':
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
