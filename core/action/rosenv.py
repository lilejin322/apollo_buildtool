# !/usr/bin/env python3
###############################################################################
# Copyright 2023 The Apollo Authors. All Rights Reserved.
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
config commnad
"""
import os
import subprocess

from core import ErrCode
from core.action import Action as CoreAction
from core.package_descriptor import PackageDesc
from core.version_decide.decider import DeciderInterface
from core.logging import get_logger

logger = get_logger('buildtool')

code_dict = {
    "focal": ["foxy", "galactic"],
    "jammy": ["humble", "iron"]
}
ros_apt_repo_path = "/etc/apt/sources.list.d/ros2.list"
ros_key_request_url = "https://raw.githubusercontent.com/ros/rosdistro/master/ros.key"
apollo_cached_ros_key_request_url = "https://apollo-system.cdn.bcebos.com/archive/9.0/ros.key"
ros_key_path = "/usr/share/keyrings/ros-archive-keyring.gpg"
ros_repo_url = "http://packages.ros.org/ros2/ubuntu"

def get_action_name():
    """action name config
    """
    return 'rosenv'


def get_action_description():
    """action description
    """
    return 'prepare ros env'


class Action(CoreAction):
    """config action
    """

    def __init__(self):
        super().__init__()
        self.ubuntu_code_name = \
            subprocess.check_output("lsb_release -cs", shell=True).decode("utf-8").strip()
        if self.ubuntu_code_name not in code_dict:
            ErrCode.send_error(
                ErrCode.ParamErr,
                [f"Not support distribution {self.ubuntu_code_name}"]
            )
        self.args = None
        self.workspace = os.getcwd()
        self.rosdep = "rosdep"

    @staticmethod
    def add_argument(parser):
        """add login command parser
        """
        parser.add_argument(
            '-c', '--code-name', type=str.lstrip,
            help='specify the ros code name', default="")
        parser.add_argument(
            '-p', '--with-ros-pkg', type=str.lstrip,
            help='specify ros package source path', default='')
        parser.add_argument(
            '-t', '--tsinghua_proxy', action='store_true',
            help='use tsinghua proxy to rosdep', default=False) 

    def process_args(self):
        """process args
        """
        return

    def execute(self, args, **kwargs):
        """execute the config command
        """
        global ros_key_request_url, apollo_cached_ros_key_request_url
        if not os.path.exists(os.path.join(self.workspace, "WORKSPACE")):
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["Can't prepare rosenv outside workspace"]
            )
        self.set_args(args)
        if self.args.tsinghua_proxy:
            ros_key_request_url = apollo_cached_ros_key_request_url 
        ros_code_name_label_file = os.path.join(self.workspace, ".rosenv")
        if os.path.exists(ros_code_name_label_file):
            preset_codename = subprocess.check_output(
                "cat {}".format(ros_code_name_label_file), shell=True).decode("utf-8").strip()
            if self.args.code_name == "":
                self.args.code_name = preset_codename
            else:
                if self.args.code_name != preset_codename:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        [f"args {self.args.code_name}, while preset {preset_codename}"]
                    )
        else:
            if self.args.code_name == "":
                self.args.code_name = code_dict[self.ubuntu_code_name][-1]
            else:
                if self.args.code_name not in code_dict[self.ubuntu_code_name]:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        [f"{self.ubuntu_code_name} not support ros {self.args.code_name}"]
                    )
            subprocess.run(
                f'echo {self.args.code_name} > {ros_code_name_label_file}', shell=True)
        
        # add repo
        if not os.path.exists(ros_apt_repo_path):
            logger.info(f"execute > sudo curl {ros_key_request_url} -o {ros_key_path}")
            ret = subprocess.run(
                f"sudo curl {ros_key_request_url} -o {ros_key_path}", shell=True)
            if ret.returncode != 0:
                ErrCode.send_error(
                    ErrCode.NetworkIoError, [
                        "Download ros repo key failed!",
                        "Please ensure that you have access to:",
                        f"\t{ros_key_request_url}"
                    ]
                )
            arch = subprocess.check_output("dpkg --print-architecture", shell=True).decode("utf-8").strip()
            cmd = f'echo "deb [arch={arch} signed-by={ros_key_path}] {ros_repo_url} {self.ubuntu_code_name} main"'
            cmd = cmd + f' | sudo tee {ros_apt_repo_path} > /dev/null'
            logger.info(f"execute > {cmd}")
            ret = subprocess.run(cmd, shell=True)
            if ret.returncode != 0:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    [f"Generate ros repo file of apt failed!"]
                )
        # ros env install
        ret = subprocess.run(
            f"dpkg -l ros-{self.args.code_name}-desktop > /dev/null 2>&1", shell=True)
        if ret.returncode != 0:
            logger.info(f"execute > sudo apt install ros-{self.args.code_name}-desktop")
            cmd = "sudo apt update"
            cmd = cmd + f" && sudo apt install -y ros-{self.args.code_name}-desktop"
            # cmd = cmd + f" ros-{self.args.code_name}-cyclonedds"
            # cmd = cmd + f" ros-{self.args.code_name}-rmw-cyclonedds-cpp" 
            cmd = cmd + f" python3-rosdep python3-colcon-common-extensions"
            install_ret = subprocess.run(cmd, shell=True)
            if install_ret.returncode != 0:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    [f"Install ros-{self.args.code_name}-desktop failed!"]
                )
        logger.info(f"execute > mkdir -p ros_ws") 
        subprocess.run(f"mkdir -p ros_ws", shell=True)

        if self.args.tsinghua_proxy:
            ts_pip_proxy = "-i https://pypi.tuna.tsinghua.edu.cn/simple"
            ret = subprocess.run(f"pip3 install {ts_pip_proxy} rosdepc >/dev/null", shell=True)
            if ret.returncode != 0:
                logger.warning("Install rosdep tsinghua proxy failed, use rosdep instead")
            else:
                self.rosdep = "rosdepc"
                ret = subprocess.run(f"which {self.rosdep} >/dev/null", shell=True)
                if ret.returncode != 0:
                    self.rosdep = "~/.local/bin/rosdepc"
                    ret = subprocess.run(f"which {self.rosdep} >/dev/null", shell=True)
                    if ret.returncode != 0:
                        logger.warning("tsinghua proxy setup failed, use rosdep instead")
                        self.rosdep = "rosdep"

        # update ros repo
        logger.info(f"execute > sudo rosdep init")
        ret = subprocess.run(
            f"source /opt/ros/{self.args.code_name}/setup.sh"
            f" && sudo -E {self.rosdep} init >/dev/null", shell=True, executable='/bin/bash')
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.NetworkIoError, [
                    "init ros depends failed!",
                    "You may add -t arg to use tsinghua proxy"
                ]
            )
        logger.info(f"execute > rosdep update")
        ret = subprocess.run(f"{self.rosdep} update >/dev/null", shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.NetworkIoError, [
                    "Update ros depends failed!",
                    "You may add -t arg to use tsinghua proxy"
                ]
            )

        if self.args.with_ros_pkg != "":
            if not self.args.with_ros_pkg.startswith('/'):
                self.args.with_ros_pkg = os.path.join(
                    self.workspace, self.args.with_ros_pkg)
            if not os.path.exists(self.args.with_ros_pkg):
                logger.warning(
                    f"{self.args.with_ros_pkg} not exists, skip to install deps")
                return
            logger.info(f"execute > cp {self.args.with_ros_pkg} ros_ws/")
            ret = subprocess.run(f"cp -r {self.args.with_ros_pkg} ros_ws/", shell=True)
            if ret.returncode != 0:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    [f"Copy ros packages failed!"]
                )
            logger.info("execute > rosdep install --from-paths"
                            f" src --ignore-src --rosdistro={self.args.code_name} -y") 
            ret = subprocess.run("pushd ros_ws && rosdep install --from-paths src --ignore-src"
                f" --rosdistro={self.args.code_name} -y && popd", shell=True, executable='/bin/bash')
            if ret.returncode != 0:
                ErrCode.send_error(
                    ErrCode.NetworkIoError,
                    [f"rosdep install depends failed!"]
                )
        logger.info("Finish ros env setup, run the following command:")
        if self.args.with_ros_pkg != "":
            print("\tsource ros_ws/install/setup.sh")
        else:
            print(f"\tsource /opt/ros/{self.args.code_name}/setup.sh")
        logger.info("to configure the ros environment variable")
            