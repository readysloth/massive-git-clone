import sys
import asyncio
import argparse
import itertools as it
import multiprocessing as mp

CPU_COUNT = mp.cpu_count()

def split_every(n, iterable):
    iterable = iter(iterable)
    yield from iter(lambda: list(it.islice(iterable, n)), [])


async def clone(repo_clone_url, minimal_depth=False, compress=False):
    directory = '_'.join(repo_clone_url.split('/')[-2:])
    repo_url_and_dir = [repo_clone_url, directory]
    cmd = ["git", "clone", "--recursive"]
    if minimal_depth:
        cmd.append("--depth=1")
    cmd += repo_url_and_dir

    if compress:
        cmd += ["; tar cf -", directory, "| xz -9e -c - >", directory + "tar.xz &&", "rm -rf", directory]

    proc = await asyncio.create_subprocess_shell(' '.join(cmd),
                                                 stdin=asyncio.subprocess.PIPE,
                                                 stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.PIPE)
    print("Cloning {} to {}".format(repo_clone_url, directory))
    proc.stdin.write(b'yes\n'*100)
    return await proc.wait()


async def clone_repos(repo_clone_urls, *args, **kwargs):
    pending_tasks = []
    ev_loop = asyncio.get_event_loop()
    clone_tasks = (ev_loop.create_task(clone(u, *args, **kwargs)) for u in repo_clone_urls)
    for chunk in split_every(CPU_COUNT, clone_tasks):
        done, pending = await asyncio.wait(chunk, return_when=asyncio.FIRST_COMPLETED)
        pending_tasks += pending
        pending_tasks = [pt for pt in pending_tasks if pt not in done]
        while len(pending_tasks) > CPU_COUNT*2:
            done, pending = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)
            pending_tasks += pending
            pending_tasks = [pt for pt in pending_tasks if pt not in done]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repofile", nargs='+', help="file with git repo clone urls")
    parser.add_argument("-m", "--minimal-depth", action='store_true', help="save repos with depth=1")
    parser.add_argument("-z", "--compress", action='store_true', help="compress downloaded repos into tar.xz archive")
    args = parser.parse_args()
    for file in args.repofile:
        if file == '-':
            lines = sys.stdin.readlines()
        else:
            with open(file, 'r') as f:
                lines = f.readlines()
        asyncio.run(clone_repos(map(str.strip, lines),
                                minimal_depth=args.minimal_depth,
                                compress=args.compress,
                                ))

if __name__ == "__main__":
    main()
