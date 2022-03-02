import sys
import asyncio
import argparse
import itertools as it
import multiprocessing as mp
from urllib.parse import urlparse

CPU_COUNT = mp.cpu_count()


def split_every(n, iterable):
    iterable = iter(iterable)
    yield from iter(lambda: list(it.islice(iterable, n)), [])


async def clone(repo_clone_url):
    parsed_url = urlparse(repo_clone_url)

    anon_repo_clone_url = "{}://anon:anon@{}{}".format(
        parsed_url.scheme, parsed_url.netloc, parsed_url.path
    )
    cmd = ["git", "clone", "--recursive", anon_repo_clone_url]
    proc = await asyncio.create_subprocess_shell(" ".join(cmd))
    return await proc.wait()


async def clone_repos(repo_clone_urls):
    pending_tasks = []
    ev_loop = asyncio.get_event_loop()
    clone_tasks = (ev_loop.create_task(clone(u)) for u in repo_clone_urls)
    for chunk in split_every(CPU_COUNT, clone_tasks):
        done, pending = await asyncio.wait(chunk)
        pending_tasks += pending
        pending_tasks = [pt for pt in pending_tasks if pt not in done]
        if len(pending_tasks) > CPU_COUNT * 2:
            await asyncio.gather(*pending_tasks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repofile", nargs="+", help="file with git repo clone urls")
    args = parser.parse_args()
    for file in args.repofile:
        if file == "-":
            lines = sys.stdin.readlines()
        else:
            with open(file, "r") as f:
                lines = f.readlines()
        asyncio.run(clone_repos(map(str.strip, lines)))


if __name__ == "__main__":
    main()
