"""Linux tool launcher: wait for the command and any orphaned descendants.

Some batch tools return before their workers. Use a subreaper inside the tool
container so its lifetime includes those workers. The outer evaluator supplies
resource limits and kills the entire container on timeout. This standalone file
also runs with the OS Python supplied by older commercial-tool runtime images.
"""
import ctypes
import os
import sys


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Supply a tool command')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Cannot register tool subreaper')
    child = os.fork()
    if child == 0:
        try:
            os.execvp(sys.argv[1], sys.argv[1:])
        except OSError as error:
            print(str(error), file=sys.stderr, flush=True)
            os._exit(126)
    status = 0
    while True:
        try:
            _, result = os.waitpid(-1, 0)
        except InterruptedError:
            continue
        except ChildProcessError:
            break
        if os.WIFSIGNALED(result):
            status = status or 128 + os.WTERMSIG(result)
        elif os.WIFEXITED(result):
            status = status or os.WEXITSTATUS(result)
    raise SystemExit(status)


if __name__ == '__main__':
    main()
