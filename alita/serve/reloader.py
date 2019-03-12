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


def _find_observable_paths(extra_files=None):
    """Finds all paths that should be observed."""
    rv = set(os.path.dirname(os.path.abspath(x))
             if os.path.isfile(x) else os.path.abspath(x)
             for x in sys.path)

    for filename in extra_files or ():
        rv.add(os.path.dirname(os.path.abspath(filename)))

    for module in list(sys.modules.values()):
        fn = getattr(module, '__file__', None)
        if fn is None:
            continue
        fn = os.path.abspath(fn)
        rv.add(os.path.dirname(fn))

    return _find_common_roots(rv)


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


def _find_common_roots(paths):
    """Out of some paths it finds the common roots that need monitoring."""
    paths = [x.split(os.path.sep) for x in paths]
    root = {}
    for chunks in sorted(paths, key=len, reverse=True):
        node = root
        for chunk in chunks:
            node = node.setdefault(chunk, {})
        node.clear()

    rv = set()

    def _walk(node, path):
        for prefix, child in node.items():
            _walk(child, path + (prefix,))
        if not node:
            rv.add('/'.join(path))
    _walk(root, ())
    return rv


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
        signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
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
                    subprocess.run(["pkill", "-P", str(worker_process.pid)])
                    worker_process.terminate()
                    self.run()
                    self.trigger_reload(filename)
            self._sleep(self.interval)


def run_auto_reload(extra_files=None, interval=1, _log=None):
    try:
        AutoReloadLoop(extra_files, interval, _log).run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    run_auto_reload()
