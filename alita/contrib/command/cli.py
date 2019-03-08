"""
Command line interface for alit.
"""
import os
import sys
import platform
import traceback
import click
import logging
from alita import __version__
from .utils import OSUtils


def get_system_info():
    python_info = "python {}.{}.{}".format(sys.version_info[0],
                                           sys.version_info[1],
                                           sys.version_info[2])
    platform_system = platform.system().lower()
    platform_release = platform.release()
    platform_info = "{} {}".format(platform_system, platform_release)
    return "{}, {}".format(python_info, platform_info)


def config_logging(file_name=None):
    log_formatter = logging.Formatter("%(asctime)s: %(message)s")
    root_logger = logging.getLogger()

    if file_name:
        file_handler = logging.FileHandler(file_name)
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)


@click.group()
@click.version_option(version=__version__,
                      message='%(prog)s %(version)s, {}'
                      .format(get_system_info()))
@click.option('--project-dir',
              help='The project directory.  Defaults to CWD')
@click.option('--debug/--no-debug',
              default=False,
              help='Print debug logs to stderr.')
@click.pass_context
def cli(ctx, project_dir, debug=False):
    if project_dir is None:
        project_dir = os.getcwd()
    else:
        project_dir = os.path.abspath(project_dir)
    ctx.obj['project_dir'] = project_dir
    ctx.obj['debug'] = debug
    ctx.obj["os_utils"] = OSUtils()
    os.chdir(project_dir)


def main():
    try:
        return cli(obj={})
    except Exception as ex:
        print(ex)
        click.echo(traceback.format_exc(), err=True)
        return 2
