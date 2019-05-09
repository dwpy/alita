import os
import sys
import time
import signal
import logging
import subprocess
from itertools import chain
from multiprocessing import Process


def _iter_module_files():
    """This iterates over all relevant Python files.  It goes through all
    loaded files from modules, all files in folders of already loaded modules
    as well as all files reachable through a package.
    """
    # The list call is necessary on Python 3 in case the module
    # dictionary modifies during iteration.
    for module in list(sys.modules.values()):
        if module is None:
            continue
        filename = getattr(module, '__file__', None)
        if filename:
            if os.path.isdir(filename) and \
               os.path.exists(os.path.join(filename, "__init__.py")):
                filename = os.path.join(filename, "__init__.py")

            old = None
            while not os.path.isfile(filename):
                old = filename
                filename = os.path.dirname(filename)
                if filename == old:
                    break
            else:
                if filename[-4:] in ('.pyc', '.pyo'):
                    filename = filename[:-1]
                yield filename


def _get_args_for_reloading():
    """Returns the executable. This contains a workaround for windows
    if the executable is incorrectly reported to not have the .exe
    extension which can cause bugs on reloading.
    """
    rv = [sys.executable]
    py_script = sys.argv[0]
    if os.name == 'nt' and not os.path.exists(py_script) and \
       os.path.exists(py_script + '.exe'):
        py_script += '.exe'
    if os.path.splitext(rv[0])[1] == '.exe' and os.path.splitext(py_script)[1] == '.exe':
        rv.pop(0)
    rv.append(py_script)
    rv.extend(sys.argv[1:])
    return rv


def kill_process_children_unix(pid):
    """Find and kill child processes of a process (maximum two level).

    :param pid: PID of parent process (process ID)
    :return: Nothing
    """
    root_process_path = "/proc/{pid}/task/{pid}/children".format(pid=pid)
    if not os.path.isfile(root_process_path):
        return
    with open(root_process_path) as children_list_file:
        children_list_pid = children_list_file.read().split()

    for child_pid in children_list_pid:
        children_proc_path = "/proc/%s/task/%s/children" % (
            child_pid,
            child_pid,
        )
        if not os.path.isfile(children_proc_path):
            continue
        with open(children_proc_path) as children_list_file_2:
            children_list_pid_2 = children_list_file_2.read().split()
        for _pid in children_list_pid_2:
            try:
                os.kill(int(_pid), signal.SIGTERM)
            except ProcessLookupError:
                continue
        try:
            os.kill(int(child_pid), signal.SIGTERM)
        except ProcessLookupError:
            continue


def kill_process_children_osx(pid):
    """Find and kill child processes of a process.

    :param pid: PID of parent process (process ID)
    :return: Nothing
    """
    subprocess.run(["pkill", "-P", str(pid)])


def kill_process_children(pid):
    """Find and kill child processes of a process.

    :param pid: PID of parent process (process ID)
    :return: Nothing
    """
    if sys.platform == "darwin":
        kill_process_children_osx(pid)
    elif sys.platform == "linux":
        kill_process_children_unix(pid)
    else:
        pass  # should signal error here


def kill_program_completly(proc):
    """Kill worker and it's child processes and exit.

    :param proc: worker process (process ID)
    :return: Nothing
    """
    kill_process_children(proc.pid)
    proc.terminate()
    os._exit(0)


class ReloadLoop(object):
    name = None
    _sleep = staticmethod(time.sleep)

    def __init__(self, extra_files=None, interval=1, _log=None):
        self.extra_files = set(os.path.abspath(x)
                               for x in extra_files or ())
        self.interval = interval
        self._log = _log or self._loop_log
        self.logger = logging.getLogger(__name__)

    def _loop_log(self, type, message, *args, **kwargs):
        getattr(self.logger, type)(message.rstrip(), *args, **kwargs)

    def run(self):
        pass

    def restart_with_reloader(self):
        """Spawn a new Python interpreter with the same arguments as this one,
        but running the reloader thread.
        """
        while True:
            self._log('info', ' * Restarting with %s' % self.name)
            args = _get_args_for_reloading()
            new_environ = os.environ.copy()
            new_environ['SERVER_RUN_MAIN'] = 'true'
            cmd = " ".join(args)
            worker_process = Process(
                target=subprocess.call,
                args=(cmd,),
                kwargs={
                    "cwd": os.getcwd(),
                    "shell": True,
                    "env": new_environ
                },
            )
            worker_process.start()
            return worker_process

    def trigger_reload(self, filename):
        self.log_reload(filename)
        sys.exit(3)

    def log_reload(self, filename):
        filename = os.path.abspath(filename)
        self._log('info', ' * Detected change in %r, reloading' % filename)


class AutoReloadLoop(ReloadLoop):
    name = 'stat'

    def run(self):
        mtimes = {}
        worker_process = self.restart_with_reloader()
        signal.signal(
            signal.SIGTERM, lambda *args: kill_program_completly(worker_process)
        )
        signal.signal(
            signal.SIGINT, lambda *args: kill_program_completly(worker_process)
        )
        while True:
            for filename in chain(_iter_module_files(),
                                  self.extra_files):
                try:
                    mtime = os.stat(filename).st_mtime
                except OSError:
                    continue

                old_time = mtimes.get(filename)
                if old_time is None:
                    mtimes[filename] = mtime
                    continue
                elif mtime > old_time:
                    kill_process_children(worker_process.pid)
                    worker_process.terminate()
                    worker_process = self.restart_with_reloader()
                    mtimes[filename] = mtime
                    break
            self._sleep(self.interval)


def run_auto_reload(extra_files=None, interval=1, _log=None):
    try:
        AutoReloadLoop(extra_files, interval, _log).run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    run_auto_reload()
