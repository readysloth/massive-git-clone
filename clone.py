import os
import sys
import asyncio
import argparse
import itertools as it
import multiprocessing as mp

CPU_COUNT = mp.cpu_count()

def split_every(n, iterable):
    iterable = iter(iterable)
    yield from iter(lambda: list(it.islice(iterable, n)), [])


async def archive_exists(path):
    archive_path = path + ".tar.xz"
    if os.path.exists(archive_path):
        test_proc = await asyncio.create_subprocess_shell("xz -t {}".format(archive_path),
                                                          stdin=asyncio.subprocess.PIPE,
                                                          stdout=asyncio.subprocess.PIPE,
                                                          stderr=asyncio.subprocess.PIPE)
        await test_proc.wait()
        if not test_proc.returncode:
            return True
    return False


async def compress(queue):
    active_compressors = []
    ev_loop = asyncio.get_event_loop()

    while True:
        path = await queue.get()
        if not path:
            return await asyncio.wait(active_compressors)
        archive_path = path + ".tar.xz"
        cmd = ["tar cf -", path, "| xz -9e -c - >", archive_path, "&& rm -rf", path]

        proc = await asyncio.create_subprocess_shell(' '.join(cmd),
                                                     stdin=asyncio.subprocess.PIPE,
                                                     stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.PIPE)
        print("Compressing {} to {}".format(path, archive_path))
        if len(active_compressors) > CPU_COUNT // 2:
            await asyncio.wait(active_compressors)
        active_compressors.append(ev_loop.create_task(proc.wait()))


async def clone(repo_clone_url, queue, minimal_depth=False, resume=False):
    directory = '_'.join(repo_clone_url.split(':')[-1].split('/')[-2:])
    if resume and await archive_exists(directory):
        return

    repo_url_and_dir = [repo_clone_url, directory]
    cmd = ["git", "clone", "--recursive"]
    if minimal_depth:
        cmd.append("--depth=1")
    cmd += repo_url_and_dir

    print("Cloning {} to {}".format(repo_clone_url, directory))
    proc = await asyncio.create_subprocess_shell(' '.join(cmd),
                                                 stdin=asyncio.subprocess.PIPE,
                                                 stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.PIPE)
    await proc.wait()
    await queue.put(directory)


async def process_repos(repo_clone_urls, queue, *args, **kwargs):
    ev_loop = asyncio.get_event_loop()
    clone_tasks = (ev_loop.create_task(clone(u, queue, *args, **kwargs)) for u in repo_clone_urls)
    pending_tasks = []
    for chunk in split_every(CPU_COUNT, clone_tasks):
        done, pending = await asyncio.wait(chunk+pending_tasks, return_when=asyncio.FIRST_COMPLETED)
        pending_tasks += pending
        pending_tasks = [pt for pt in pending_tasks if pt not in done]
        while len(pending_tasks) > CPU_COUNT*2:
            done, pending = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)
            pending_tasks = [pt for pt in pending_tasks if pt not in done]
    if pending_tasks:
        await asyncio.wait(pending_tasks)
    await queue.put(None)


async def async_cloning(repo_clone_urls, *args, do_compress=False, **kwargs):
    queue = asyncio.Queue()

    async def dummy():
        while True:
            if not await queue.get():
                break


    if do_compress:
        return await asyncio.gather(process_repos(repo_clone_urls, queue, *args, **kwargs),
                                    compress(queue))
    return await asyncio.gather(process_repos(repo_clone_urls, queue, *args, **kwargs),
                                dummy(queue))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repofile", nargs='+', help="file with git repo clone urls")
    parser.add_argument("-m", "--minimal-depth", action='store_true', help="save repos with depth=1")
    parser.add_argument("-z", "--compress", action='store_true', help="compress downloaded repos into tar.xz archive")
    parser.add_argument("-r", "--resume", action='store_true', help="resume interrupted download")
    args = parser.parse_args()
    for file in args.repofile:
        if file == '-':
            lines = sys.stdin.readlines()
        else:
            with open(file, 'r') as f:
                lines = f.readlines()
        asyncio.run(async_cloning(map(str.strip, lines),
                                  minimal_depth=args.minimal_depth,
                                  do_compress=args.compress,
                                  resume=args.resume))

if __name__ == "__main__":
    main()
