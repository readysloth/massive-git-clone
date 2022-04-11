import os
import sys
import asyncio
import argparse
import itertools as it
import multiprocessing as mp


CPU_COUNT = mp.cpu_count()


async def wait_all_pending(active_procs, result_queue):
    while len(active_procs) > CPU_COUNT // 2:
        done, pending = await asyncio.wait(active_procs, return_when=asyncio.FIRST_COMPLETED)
        active_procs = [t for t in active_procs if t not in done]
        for t in done:
            await result_queue.put(t.name)
    return active_procs


async def git_unshallow(dir_queue, compress_queue):
    cmd = "git fetch --unshallow && git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*' && git fetch origin"
    active_procs = []
    ev_loop = asyncio.get_event_loop()
    while True:
        directory = await dir_queue.get()
        if not directory:
            if active_procs:
                unshallow_tasks, _ = await asyncio.wait(active_procs)
                for ut in unshallow_tasks:
                    await compress_queue.put(ut.name)
            return await compress_queue.put(None)

        directory = os.path.abspath(directory)
        if not os.path.exists(directory):
            continue
        unshallow_proc = await asyncio.create_subprocess_shell(cmd,
                                                               stdin=asyncio.subprocess.PIPE,
                                                               stdout=asyncio.subprocess.PIPE,
                                                               stderr=asyncio.subprocess.PIPE,
                                                               cwd=directory)
        print("Unshallowing {}".format(directory))
        active_procs = await wait_all_pending(active_procs, compress_queue)
        task = ev_loop.create_task(unshallow_proc.wait())
        setattr(task, "name", directory)
        active_procs.append(task)


async def unpack(files, dir_queue):
    active_procs = []
    ev_loop = asyncio.get_event_loop()

    for file in files:
        file = os.path.abspath(file)
        if not os.path.exists(file):
            continue

        cmd = "tar xf {}".format(file)
        directory = file.removesuffix('.tar.xz')

        try:
            unpack_proc = await asyncio.create_subprocess_shell(cmd)
        except Exception as e:
            print("Corrupted archive!", file)
            continue
        print("Unpacking {}".format(file))
        active_procs = await wait_all_pending(active_procs, dir_queue)
        task = ev_loop.create_task(unpack_proc.wait())
        setattr(task, "name", directory)
        active_procs.append(task)

    if active_procs:
        unpack_tasks, _ = await asyncio.wait(active_procs)
        for ut in unpack_tasks:
            await dir_queue.put(ut.name)
    await dir_queue.put(None)


async def compress(compress_queue, output):
    active_procs = []
    ev_loop = asyncio.get_event_loop()

    while True:
        path = await compress_queue.get()
        if not path:
            if active_procs:
                await asyncio.wait(active_procs)
            return
        archive_path = path + ".tar.xz"
        archive_name = os.path.basename(archive_path)
        archive_path = os.path.join(output, archive_name) if output else archive_path
        cmd = ["tar cf -", path, "| xz -9e -c - >", archive_path, "&& rm -rf", path]

        proc = await asyncio.create_subprocess_shell(' '.join(cmd),
                                                     stdin=asyncio.subprocess.PIPE,
                                                     stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.PIPE)
        print("Compressing {} to {}".format(path, archive_path))
        if len(active_procs) > CPU_COUNT // 2:
            await asyncio.wait(active_procs)
        active_procs.append(ev_loop.create_task(proc.wait()))



async def massive_unshallow(files, do_compress=False, output=''):
    dir_queue, compress_queue = asyncio.Queue(), asyncio.Queue()
    coros = [unpack(files, dir_queue), git_unshallow(dir_queue, compress_queue)]
    if do_compress:
        coros.append(compress(compress_queue, output))
    if output:
        os.makedirs(output, exist_ok=True)
    await asyncio.gather(*coros)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repofile", nargs='+', help="file with git repo clone urls")
    parser.add_argument("-z", "--compress", action='store_true', help="compress unshallowed repos back into tar.xz archive")
    parser.add_argument("-o", "--output", help="output folder")
    args = parser.parse_args()
    for file in args.repofile:
        if file == '-':
            lines = sys.stdin.readlines()
        else:
            with open(file, 'r') as f:
                lines = f.readlines()
        asyncio.run(massive_unshallow(map(str.strip, lines),
                                      do_compress=args.compress,
                                      output=args.output))

if __name__ == "__main__":
    main()
