# !/usr/bin/env python3
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
base class of action
"""
apollo_prefix = "apollo-neo-"
apollo_3rd_prefix = "apollo-neo-3rd-"

import subprocess
import platform
from pathlib import Path
import os
import shutil
import xml.etree.ElementTree as ET
import json
from core import ErrCode

from core import AptContext
from core.common import get_config, get_logger
from core.version_decide.cyberfile import MetaDataCli
from core.package_descriptor import PackageDesc, Status
from core.package_identification.identifier import PackageIdentification
from core.rc_generator import main as generate_apollo_rc_file
from core.task.bazel import BAZEL_EXECUTABLE

logger = get_logger('buildtool')

def get_action_name():
    """get action name"""
    return "base"


def get_action_description():
    """get action description"""
    return "base common"


class Context(object):
    """The context provides the package and the parsed arguments."""

    __slots__ = ('pkg', 'args', 'workspace')

    def __init__(self, args, pkg, workspace=""):
        self.pkg = pkg
        self.args = args
        self.workspace = workspace

class Repository(object):
    """demonstrate the information of repository"""
    def __init__(self, name, version):
        self.name = name
        self.version = version


class Action(object):
    """base action class"""

    def __init__(self, **kwargs):
        self.targets_path = list()
        self.identifier = PackageIdentification()
        self.repositories = list()

    def execute(self, context, **kwargs):
        """
        Execute the main logic of action.

        This method must be overridden in a subclass.

        :param context: The context providing the parsed command line arguments
        :returns: The return code
        """
        raise NotImplementedError

    @staticmethod
    def add_argument(self, parser):
        """add parser argument"""
        raise NotImplementedError

    def _search_package_in_workspace(self, workspace, **kwargs):
        self._search_cyberfile(workspace, **kwargs)
        
    def _search_cyberfile(self, root, **kwargs):
        files = os.listdir(root)
        has_cyberfile = False

        if "cyberfile.xml" in files or ("cyberfile_cpu.xml" in files and "cyberfile_gpu.xml" in files):
            self.targets_path.append(root)
            has_cyberfile = True
                
        if has_cyberfile:
            cyberfile_wrapper = Path(root) / "cyberfile.xml"  
            if cyberfile_wrapper.is_symlink():
                cyberfile_wrapper.unlink()
            if not cyberfile_wrapper.exists():
                if "gpu_if_available" in kwargs and kwargs["gpu_if_available"]:
                    os.symlink(os.path.join(root, "cyberfile_gpu.xml"), str(cyberfile_wrapper))
                else:
                    os.symlink(os.path.join(root, "cyberfile_cpu.xml"), str(cyberfile_wrapper)) 
            return
        for f in files:
            if f.startswith("."):
                continue
            f_desc = Path(os.path.join(root, f))
            if f_desc.is_dir() and not f_desc.is_symlink():
                self._search_cyberfile(str(f_desc), **kwargs)

    def _update_source(self):
        # logger.info("Updating remote source...")
        # cmd = "{} update --allow-insecure-repositories >/dev/null 2>&1".format(AptContext.executable)
        # subprocess.run(cmd, shell=True)
        pass

    def set_args(self, args):
        """set runtime arguments"""
        self.args = args

    def process_args(self):
        """process runtime arguments"""
        raise NotImplementedError

    def set_ld_path(self, **kwargs):
        """set ldconfig config file of search path"""
        root_path = os.path.dirname(
            os.path.abspath(
                os.path.dirname(
                    os.path.dirname(os.path.realpath(__file__))
                )
            )
        )
        update_ldconfig_script_wrapper = Path(root_path) / "scripts" / "update_dylib.sh"
        if not update_ldconfig_script_wrapper.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr, 
                ["Can not find {}".format(str(update_ldconfig_script_wrapper))]
            )

        else:
            output = subprocess.check_output(
                "bash {}".format(update_ldconfig_script_wrapper), shell=True
            ).decode() 
            logger.debug(output)
        
    def get_pkg_real_name(self, name, dev=False, dbg=False, gpu=False):
        """Get real package name by install parameters"""
        new_name = name
        if dev:
            new_name += "-dev"
        if dbg:
            new_name += "-dbg"
        if gpu:
            new_name += "-gpu"
        return new_name

    def clean_bazel_cache(self):
        """clean bazel building cache"""
        logger.info("Clean build cache, it will take a while...")
        cmd = [BAZEL_EXECUTABLE] + ["clean", "--expunge", ">/dev/null 2>&1"]
        ret = subprocess.run(" ".join(cmd), shell=True, stderr=subprocess.STDOUT)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.BazelErr,
                ["Clean build cache failed, ignore and continue to build."],
                exit=False
            )

    def eval_condition(self, condition, gpu):
        """evaluate which depends is consist with condition"""
        if condition == "gpu" and gpu:
            return True
        elif condition == "not gpu" and not gpu:
            return True
        else:
            return False

    def setup_cyberfile(self, cyberfile_path, replace=True, dev=False, dbg=False, gpu=False):
        """Setup final cyberfile by install parameters. """
        if dev and dbg:
            ErrCode.send_error(
                ErrCode.UnknownErr,
                ["Build in both dev and dbg mode!"]
            )

        cyberfile = ET.parse(cyberfile_path)
        root = cyberfile.getroot()

        name = root.find("name")
        old_name = name.text
        # use default setting
        # name.text = self.get_pkg_real_name(name.text, dev=True, dbg=False, gpu=False)

        for dep in root.findall("depend"):
            if not dep.get("condition"):
                continue
            else:
                pass
                if not self.eval_condition(dep.get("condition"), gpu):
                    root.remove(dep)

        if replace:
            cyberfile.write(cyberfile_path)

        return old_name, name.text, ET.tostring(root)

    def change_target_name(self, targets, dev, dbg, gpu):
        """change target name based on build parameter"""
        path_to_desc = dict()
        new_targets = list()
        for target in targets:
            cyberfile_wrapper = Path(target.workspace) / "cyberfile.xml"
            if not cyberfile_wrapper.exists():
                ErrCode.send_error(
                    ErrCode.FileIoErr, 
                    ["{} cyberfile is not existed".format(target.name)]
                )

            _, _, new_cyberfile_xml_bytes = self.setup_cyberfile(
                str(cyberfile_wrapper), replace=False, 
                dev=dev, dbg=dbg, gpu=gpu
            )

            new_target = PackageDesc(target.workspace)
            self.identifier.identify(new_target, new_cyberfile_xml_bytes.decode("utf-8"))
            path_to_desc[target.workspace] = new_target
            new_targets.append(new_target)
        return new_targets, path_to_desc

    def parse_workspace_conf(self):
        """parse the config file of workspace"""
        workspace = os.getcwd()
        if os.path.exists(os.path.join(workspace, ".workspace.json")):
            try:
                repositories_define_path = os.path.join(workspace, ".workspace.json")
                repositories_define = None
                with open(repositories_define_path, "r") as f:
                    repositories_define = json.loads(f.read())
                    for repo in repositories_define["repositories"]:
                        name = repo["name"]
                        version = repo["version"]
                        self.repositories.append(Repository(name, version))
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["parse .workspace.json error: {}".format(str(ex))]
                )
        else:
            self.metacli = MetaDataCli()
            if platform.machine() == "aarch64":
                self.metacli.run([Repository("apollo-core-arm", "latest")])
                latest = self.metacli.get_latest_version("cyber").__str__()
                self.repositories.append(Repository("apollo-core-arm", latest))
            else:
                self.metacli.run([Repository("apollo-core", "latest")])
                latest = self.metacli.get_latest_version("cyber").__str__()
                self.repositories.append(Repository("apollo-core", latest))
            
            # with open(os.path.join(workspace, ".workspace.json"), "w+") as f:
            #     f.write(json.dumps({"apollo-core": {"version": latest}}))

        if len(self.repositories) == 0:
            ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["can find any repository in .workspace.json"]
                )

    def construct_targets_desc(self, **kwargs):
        """construct local package cyberfile"""
        target_set = dict()
        targets = list()

        for target_path in self.targets_path:
            desc = PackageDesc(target_path)

            self.identifier.identify(desc, node=None, ignore_mismatch="ignore_mismatch" in kwargs)
            if desc.name in target_set:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["Different package in workspace have same name: {}".format(desc.name)]
                )

            if desc.status == Status.INVALID:
                #ErrCode.send_error(
                #    ErrCode.PackageAttrErr,
                #    [
                #        "Package in {} with invalid status".format(target_path),
                #        "Abort process"
                #    ]
                #)
                continue
            
            # support workspace imported 3rd package
            if desc.type != "module":
                continue
            
            targets.append(desc)
            target_set[desc.name] = desc
        
        return targets

    def _check_package_location(self, package, workspace):
        if package.workspace:
            attribute_path = os.path.join(workspace, package.real_src_to_related_path())
            if attribute_path != package.workspace:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["Package {} is not in {}".format(package.name, attribute_path)],
                    exit=False
                )
                return False
        return True

    def _setup_rc_files(self, workspace):
        top_level_rc_file_name = ".bazelrc"
        cpplint_file_name = "CPPLINT.cfg"
        rc_files_stored_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "bazel"
        )
        top_level_rc_file = os.path.join(rc_files_stored_path, top_level_rc_file_name)
        workspace_rc_dst = os.path.join(workspace, top_level_rc_file_name)
        if not os.path.isfile(top_level_rc_file):
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["Cannot find Apollo rc files."],
                ["Reinstall buildtool may solve this problem."],
                exit=True
            )
        if Path(workspace_rc_dst).is_symlink():
            Path(workspace_rc_dst).unlink()
        if not os.path.isfile(workspace_rc_dst):
             shutil.copy(top_level_rc_file, workspace_rc_dst)
        
        try:
            generate_apollo_rc_file()
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                [str(ex)],
                exit=True,
            )

        cpplint_file = os.path.join(rc_files_stored_path, cpplint_file_name)
        dst = os.path.join(workspace, cpplint_file_name)
        if not os.path.isfile(cpplint_file):
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["Cannot find Apollo cpplint files."],
                ["Reinstall buildtool may solve this problem."],
                exit=True
            )
        if Path(dst).is_symlink():
            Path(dst).unlink()
        if not os.path.isfile(dst):
             shutil.copy(cpplint_file, dst)


    def _check_status_before_build(self, packages):
        for package in packages:
            if package.status != Status.VALID: 
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    [
                        "package with {} status can not be processed! package={}".format(
                            package.status, package.name
                        )
                    ],
                    exit=False
                )
                return False
            package.check_real_src()
        return True

    def _process_basic_known_build_args(self, gpu_available, args):
        known_opt = None
        if args.cpu and args.gpu:
            logger.info("CPU and GPU mode both use. Use GPU mode instead.")
            if gpu_available:
                known_opt = "--config=gpu"
            else:
                logger.info("GPU is not available. Use CPU mode.")
                known_opt = "--config=cpu" 
        elif not args.cpu and not args.gpu:
            if gpu_available:
                known_opt = "--config=cpu"
            else:
                known_opt = "--config=cpu"
        else:
            if args.cpu:
                known_opt = "--config=cpu" 
            else:
                if gpu_available:
                    known_opt = "--config=gpu"
                else:
                    logger.info("GPU is not available. Use CPU mode.")
                    known_opt = "--config=cpu"
        return known_opt
