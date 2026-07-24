#!/usr/bin/env python3

###############################################################################
# Copyright 2019 The Apollo Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
###############################################################################
"""
apollo build tool
"""
import argparse
import atexit
import os
import getpass
import sys
import pathlib
import signal
import platform
import subprocess

pkg_root = os.path.dirname(os.path.abspath(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, pkg_root)

from core.entry_point import EntryPoints
from core.logging import init_logger, get_logger
from core.common import get_config

init_logger('buildtool')
logger = get_logger('buildtool')

from core import ErrCode

# it may cause apt error
#signal.signal(signal.SIGCHLD, signal.SIG_IGN)


def exit_handler():
    """exit handler"""
    logger.debug('apollo build tool exit.')


def signal_handler(sig, action):
    """signal_handler for subprocess"""
    logger.error('Keyboard interrupt received. Stop all processes.')
    os.killpg(os.getpgid(os.getpid()), signal.SIGKILL)


def set_handler():
    """set all handler"""
    atexit.register(exit_handler)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

entry_points_path = os.path.join(pkg_root, "core", "action")
root_path = pkg_root


class PackageBuilder(object):
    """main class"""
    def __init__(self):
        set_handler()
        self.use_gpu = False
        self.parser = argparse.ArgumentParser(description='build tools of apollo')
        self.parser.add_argument(
            '-v', '--version', action='version', version='9.0.0-alpha3-r10')
        subparsers = self.parser.add_subparsers(help='sub-command')

        if len(sys.argv) <= 1:
            ErrCode.send_error(
                ErrCode.ParamErr, ["command not found! Add -h to show the help message"]
            )

        self.command = sys.argv[1]

        self.entry_points = EntryPoints(entry_points_path, root_path, subparsers, self.command)
        self.parms = self.parser.parse_args()

    # check_* functions below are for passing the arguments to bazel
    # that means check_* functions are for building or installing apollo modules
    # developers must declare similar parameters in buildfile of their module if necessary
    def check_architecture_support(self):
        """check env"""
        supported_archs = "x86_64 aarch64"
        if platform.machine() not in supported_archs:
            ErrCode.send_error(
                ErrCode.ArchErr,
                [
                    "Cpu arch {} is not support!".format(platform.machine()),
                    "Currently, we only supports running on the following CPU archs: {}".format(supported_archs)
                ]
            )

    def check_platfrom_support(self):
        """check env"""
        supported_platfrom = "Linux"
        if platform.system() != supported_platfrom:
            ErrCode.send_error(
                ErrCode.ArchErr,
                [
                    "Platform {} is not support".format(platform.system()),
                    "Currently, we only supports running on the following platfrom: {}".format(supported_platfrom)
                ]
            )

    def check_minimal_memory_requirement(self):
        """check env"""
        minimal_mem_gb = 2.0
        cmd = "free -m | awk '/Mem:/ {printf(\"%0.2f\", $2 / 1024.0)}'"
        actul_mem_gb = float(subprocess.check_output([cmd], shell=True))
        if actul_mem_gb < minimal_mem_gb:
            logger.warning("System memory [%dG] is lower than minium required" \
                "[%dG]. The action could be failed." % (actul_mem_gb, minimal_mem_gb))

    def check_esdcan_use(self):
        """check env"""
        #TODO: confirm where can card lib and header is stored
        apollo_root_dir = os.getenv("APOLLO_ROOT_DIR")
        #TODO read from config
        if apollo_root_dir is None:
            apollo_root_dir = "/opt/apollo/neo"
        if (pathlib.Path(apollo_root_dir) / "include/ntcan.h").is_file() \
            and (pathlib.Path(apollo_root_dir) / "lib/libntcan.so.4").is_file():
            self.use_esd = True
        else:
            self.use_esd = False

    def check_gpu_existence(self):
        """check env"""
        if platform.machine() == "aarch64":
            try:
                driver_existence = subprocess.check_output(["lsmod | grep -q nvgpu"], shell=True)
                cuda_existence = subprocess.check_output(["ldconfig -p | grep -q cudart"], shell=True)
                if driver_existence is not None and cuda_existence is not None:
                    self.use_gpu = True
            except:
                pass
        else:
            try:
                if subprocess.call(['nvidia-smi >/dev/null 2>&1'], shell=True) == 0 and \
                        subprocess.check_output(
                            'nvidia-smi 2>/dev/null | grep "Driver Version"', shell=True) is not None:
                    self.use_gpu = True
            except:
                pass
        if not self.use_gpu:
            logger.warning("Gpu is not available, using cpu instead")

    def check_in_docker_env(self):
        """check env"""
        if not (pathlib.Path("/.dockerenv")).is_file():
            ErrCode.send_error(
                ErrCode.ArchErr,
                ["Build outside of Apollo docker environment is not supported."]
            )

    def generate_env_config(self):
        """add environment variable to .bashrc"""
        #TODO read from config
        logger.info("Reconfigure apollo enviroment setup")

        target_file = list()

        user = getpass.getuser()
        if user == "root":
            """Add env setup to root .bashrc"""
            root_dir = pathlib.Path("/root")
            if root_dir.exists():
                env_file = root_dir / ".bashrc"
                target_file.append(env_file)
        else:
            """Add env setup to users .bashrc"""
            users_root = pathlib.Path("/home")
            user_dir = users_root / user
            if user_dir.exists():
                if user_dir.is_dir():
                    env_file = user_dir / ".bashrc"
                    target_file.append(env_file)

        rc = "source {}/setup.sh".format(get_config("base", "apollo_root"))

        for env_file in target_file:
            content = None
            with env_file.open("r", encoding="utf-8") as f:
                content = f.read()
            env_file_io = env_file.open("a+", encoding="utf-8")
            if content == "":
                env_file_io.write("#! /bin/bash\n")
            if rc not in content:
                env_file_io.write(rc)
            env_file_io.close()

        setup_path = pathlib.Path(pkg_root) / "setup.sh"
        link_target = pathlib.Path(get_config("base", "apollo_root"))
        if not setup_path.exists():
            os.symlink(str(setup_path), str(link_target))


    def main(self):
        """Execute the action logic"""
        self.check_esdcan_use()
        self.check_gpu_existence()
        self.check_in_docker_env()
        self.generate_env_config()
        self.check_architecture_support()
        self.check_platfrom_support()
        self.check_minimal_memory_requirement()

        return self.entry_points.execute(self.command, self.parms, \
            gpu=self.use_gpu, esd=self.use_esd)



def main():
    """main function"""
    obj = PackageBuilder()
    ret = obj.main()
    if ret != 0:
        return ret
    logger.debug("Done, Enjoy!")
    return ret


if __name__ == "__main__":
    sys.exit(main() or 0)

