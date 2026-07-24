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
an action for deploying release file
"""
import os
import subprocess
import core
import shutil
from core import ErrCode
from core.action import Context
from distutils.dir_util import copy_tree
from argparse import Namespace
from core.package_descriptor import PackageDesc
from core.topological_order import build_order
from core.task.bazel.build import BazelBuildTask
from core.version_decide.decider import DeciderInterface
from core.logging import get_logger
from core.common import get_config

logger = get_logger('buildtool')
release_path = ".deb_local"
apt = shutil.which("apt")
tar = shutil.which("tar")

def get_action_name():
    """get action name"""
    return "deploy"

def get_action_description():
    """get action description"""
    return "deploy the release file"

class Action(core.action.Action):
    """pack action class"""
    def __init__(self):
        super().__init__()
        self.workspace = os.getcwd()

    def execute(self, args, **kwargs):
        """main logic of action"""
        deploy_pkg = []
        f = args.file[0]
        if f is None or not os.path.exists(f):
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Invalid release file input"])
        os.makedirs(release_path, exist_ok=True)
        ret = subprocess.run(" ".join(
            [tar, "-xzvf", f, "-C", release_path, ">/dev/null", "2>&1"]), shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Decompress release file failed. Make sure the file is valid"])
        logger.info("Install the release file, which may require an Internet connection")
        ret = subprocess.run("mv -f ./{}/.workspace.json ./".format(release_path), shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Loading .workspace.json failed. Make sure the file is valid"])

        self.parse_workspace_conf()
        self.decider = DeciderInterface(self.repositories)

        if not os.path.exists("./WORKSPACE"):
            with open("./WORKSPACE", "w+") as f:
                f.write("")

        targets = []
        local_file_targets_name = {}
        try:
            for f in os.listdir(release_path):
                if f.endswith(".cyberfile"):
                    desc = PackageDesc()
                    self.identifier.identify_offline_package(desc, os.path.join(release_path, f))
                    targets.append(desc)
                    local_file_targets_name[f.replace(".cyberfile", "")] = desc.name
            # version determine
            targets = self.decider(targets)
            version_results = self.decider.get_result()
            desc_poll = self.decider.cyberfile_source
            
            # topological order all targets
            targets, graph = build_order(targets, targets, version_results, desc_poll)

            builder = BazelBuildTask()

            process_package_path = os.path.join(release_path, "process_package")
            for t in targets:
                t.check_real_src()
                if t.name not in [local_file_targets_name[k] for k in local_file_targets_name]:
                    builder.run(
                        Context(
                            args=Namespace(
                                builder_args="", known_options="", workspace="",
                                gpu=True, dbg=False, dev=False, memories=0.75,
                                jobs=-1, childs=graph._get_node_by_name(t.name).return_all_childs(),
                                gpu_if_available=True, install_dep_only=False,), 
                            pkg=t)
                    )
                else:
                    for k in local_file_targets_name:
                        if local_file_targets_name[k] == t.name:
                            deb_name = f"{k}.deb"
                            break
                    install_deb_path = os.path.join(release_path, deb_name)
                    target_name = t.name
                    logger.info("Install {}".format(target_name))
                    cmd = "{} {} {} {} 2>&1 && {} {} {} {} 2>&1".format(
                        "dpkg", "-x", install_deb_path, process_package_path,
                        "dpkg", "-e", install_deb_path, process_package_path)

                    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                    if p.returncode != 0:
                        ErrCode.send_error(ErrCode.AptErr,
                            ["Encouter error during decompress {}, detail:".format(i)],
                            exit=False)
                        print("\033[36mstdout\033[0m: {}".format(p.stdout.decode("utf-8")), end="")
                        print("\033[36mstderr\033[0m: {}".format(p.stderr.decode("utf-8")), end="")
                        ErrCode.send_error(ErrCode.AptErr, ["Aborting process"])
                    
                    prerm_in_package = os.path.join(process_package_path, "prerm") 
                    postrm_in_package = os.path.join(process_package_path, "postrm")  
                    preinst_in_package = os.path.join(process_package_path, "preinst") 
                    postinst_in_package = os.path.join(process_package_path, "postinst")

                    if not os.path.exists(prerm_in_package) or \
                        not os.path.exists(postrm_in_package) or \
                        not os.path.exists(preinst_in_package) or \
                        not os.path.exists(postinst_in_package):
                        ErrCode.send_error(ErrCode.PackageAttrErr,
                            [
                                "{} is missing install and rm scripts".format(i),
                                "please check the relese procedure",
                            ],
                        )

                    meta_path = os.path.join(get_config("base", "apollo_root"),
                            get_config("base", "package_meta_prefix"), target_name)
                    prerm = "{}/prerm".format(meta_path)
                    postrm = "{}/postrm".format(meta_path)
                    preinst = "{}/preinst".format(meta_path) 
                    postinst = "{}/postinst".format(meta_path) 

                    if os.path.exists(prerm):
                        cmd = "sudo {}".format(prerm)
                        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) 
                        if p.returncode != 0:
                            ErrCode.send_error(ErrCode.PackageAttrErr,
                                [
                                    "delete {} error, causing by invalid rm scripts".format(target_name),
                                    "please contact apollo maintainers"
                                ],
                            )
                    if os.path.exists(postrm):
                        cmd = "sudo {}".format(postrm)
                        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) 
                        if p.returncode != 0:
                            ErrCode.send_error(ErrCode.PackageAttrErr,
                                [
                                    "delete {} error, causing by invalid rm scripts".format(target_name),
                                    "please contact apollo maintainers"
                                ],
                            )

                    cmd = "sudo {}".format(preinst_in_package)
                    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) 
                    if p.returncode != 0:
                        ErrCode.send_error(ErrCode.PackageAttrErr,
                            ["preinst {} error, please contact apollo maintainers".format(target_name)],
                        )
                    
                    copy_tree("{}/".format(os.path.join(
                            process_package_path, get_config("base", "apollo_root")[1:])), 
                        "{}/".format(get_config("base", "apollo_root")))

                    cmd = "sudo {}".format(postinst_in_package)
                    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) 
                    if p.returncode != 0:
                        ErrCode.send_error(ErrCode.PackageAttrErr,
                            ["postinst {} error, please contact apollo maintainers".format(target_name)],
                        )
                    
                    # copy scripts
                    shutil.copy2(prerm_in_package, prerm)
                    shutil.copy2(postrm_in_package, postrm)
                    shutil.copy2(preinst_in_package, preinst)
                    shutil.copy2(postinst_in_package, postinst)

                    os.remove(install_deb_path)
                    shutil.rmtree(process_package_path)
            for i in os.listdir(release_path):
                if not i.endswith(".deb"):
                    continue
                install_deb_path = os.path.join(release_path, i)
                target_name = local_file_targets_name[i.replace(".deb", "")]

                logger.info("Install {}".format(target_name))
                cmd = "{} {} {} {} 2>&1 && {} {} {} {} 2>&1".format(
                    "dpkg", "-x", install_deb_path, process_package_path,
                    "dpkg", "-e", install_deb_path, process_package_path)

                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                if p.returncode != 0:
                    ErrCode.send_error(ErrCode.AptErr,
                        ["Encouter error during decompress {}, detail:".format(i)],
                        exit=False)
                    print("\033[36mstdout\033[0m: {}".format(p.stdout.decode("utf-8")), end="")
                    print("\033[36mstderr\033[0m: {}".format(p.stderr.decode("utf-8")), end="")
                    ErrCode.send_error(ErrCode.AptErr, ["Aborting process"])
                
                prerm_in_package = os.path.join(process_package_path, "prerm") 
                postrm_in_package = os.path.join(process_package_path, "postrm")  
                preinst_in_package = os.path.join(process_package_path, "preinst") 
                postinst_in_package = os.path.join(process_package_path, "postinst")

                if not os.path.exists(prerm_in_package) or \
                    not os.path.exists(postrm_in_package) or \
                    not os.path.exists(preinst_in_package) or \
                    not os.path.exists(postinst_in_package):
                    ErrCode.send_error(ErrCode.PackageAttrErr,
                        [
                            "{} is missing install and rm scripts".format(i),
                            "please check the relese procedure",
                        ],
                    )

                meta_path = os.path.join(get_config("base", "apollo_root"),
                        get_config("base", "package_meta_prefix"), target_name)
                prerm = "{}/prerm".format(meta_path)
                postrm = "{}/postrm".format(meta_path)
                preinst = "{}/preinst".format(meta_path) 
                postinst = "{}/postinst".format(meta_path) 

                if os.path.exists(prerm):
                    cmd = "sudo {}".format(prerm)
                    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) 
                    if p.returncode != 0:
                        ErrCode.send_error(ErrCode.PackageAttrErr,
                            [
                                "delete {} error, causing by invalid rm scripts".format(target_name),
                                "please contact apollo maintainers"
                            ],
                        )
                if os.path.exists(postrm):
                    cmd = "sudo {}".format(postrm)
                    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) 
                    if p.returncode != 0:
                        ErrCode.send_error(ErrCode.PackageAttrErr,
                            [
                                "delete {} error, causing by invalid rm scripts".format(target_name),
                                "please contact apollo maintainers"
                            ],
                        )

                cmd = "sudo {}".format(preinst_in_package)
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) 
                if p.returncode != 0:
                    ErrCode.send_error(ErrCode.PackageAttrErr,
                        ["preinst {} error, please contact apollo maintainers".format(target_name)],
                    )
                
                copy_tree("{}/".format(os.path.join(
                        process_package_path, get_config("base", "apollo_root")[1:])), 
                    "{}/".format(get_config("base", "apollo_root")))

                cmd = "sudo {}".format(postinst_in_package)
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) 
                if p.returncode != 0:
                    ErrCode.send_error(ErrCode.PackageAttrErr,
                        ["postinst {} error, please contact apollo maintainers".format(target_name)],
                    )
                
                # copy scripts
                shutil.copy2(prerm_in_package, prerm)
                shutil.copy2(postrm_in_package, postrm)
                shutil.copy2(preinst_in_package, preinst)
                shutil.copy2(postinst_in_package, postinst)

                os.remove(install_deb_path)
                shutil.rmtree(process_package_path)

        except:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["proceed release file failed."])

        for release_pkg in local_file_targets_name:
            release_pkg_name = local_file_targets_name[release_pkg]
            self.cache_install_target(self.workspace, release_pkg_name)
        
        enable_ros = False
        with_ros_source = False
        with_ros_install = False
        if os.path.exists(os.path.join(release_path, ".rosenv")):
            subprocess.run("cp -f {} ./".format(
                os.path.join(release_path, ".rosenv")), shell=True)
            enable_ros = True
        if os.path.exists(os.path.join(release_path, "src")):
            # subprocess.run("rsync -avr {}/ ros_ws/src/ >/dev/null 2>&1".format(
            #     os.path.join(release_path, "src")))
            with_ros_source = True
        
        sub_args = ""
        if args.tsinghua_proxy:
            sub_args = sub_args + "-t"
        if with_ros_source:
            sub_args = sub_args + " -p {}".format(os.path.join(release_path, "src"))
            
        ret = subprocess.run(f"buildtool rosenv {sub_args}", shell=True)
        if ret.returncode != 0:
            exit(ret.returncode)

        if os.path.exists(os.path.join(release_path, "install")):
            subprocess.run("rsync -avr {}/ ros_ws/install/ >/dev/null".format(
                os.path.join(release_path, "install")), shell=True)
            with_ros_install = True
        
        shutil.rmtree(release_path)

        logger.info("Complete to deployment!")

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument("-f", "--file",
            nargs=1, type=str.lstrip,
            help="Specify the release file.")
        parser.add_argument('-t', '--tsinghua_proxy', action="store_true",
            help='use tsinghua proxy to rosdep if including ros pkg', default=False) 