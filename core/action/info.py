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
list verb implement
"""
import os

import core.action
from core import ErrCode
from core.logging import get_logger
from core.topological_order import build_order
from core.version_decide.decider import DeciderInterface
from pathlib import Path

logger = get_logger("apollo")


def get_action_name():
    """get action name"""
    return "info"


def get_action_description():
    """get action description"""
    return "list package depends infomation based on a specific compilation parameter"


class Action(core.action.Action):
    """list action class"""
    def __init__(self):
        super().__init__()
        self.decider = DeciderInterface()
        self.cyberfile_gpu = False
        self.cyberfile_dbg = False
        self.cyberfile_dev = True
        self.with_indirect = False
        self.args = None
        pass
    
    def execute(self, args, **kwargs):
        """main logic of action"""
        self.set_args(args)
        ret = self.process_args()
        if ret != 0:
            return ret

        logger.info("Compile parameters:")
        logger.info("  using gpu: {}".format(self.cyberfile_gpu))
        logger.info("  using debug mode: {}".format(self.cyberfile_dbg))

        self._search_package_in_workspace(self.workspace)

        # construct targets by targets' path
        targets = self.construct_targets_desc()

        # change name base on build config
        new_targets, path_to_desc = self.change_target_name(
            targets, self.cyberfile_dev, self.cyberfile_dbg, self.cyberfile_gpu
        )
        
        if self.spec_dir:
            targets = new_targets
            package_desc = path_to_desc[self.query]
        elif self.depends_on:
            # search remote all depends
            all_remote_desc = []
            proceed_desc = []

            self.decider.metadata_cli.init_all_cyberfile()
            for pkg_name in self.decider.metadata_cli.cyberfile_source:
                cyberfile_content = self.decider.metadata_cli.cyberfile_source[pkg_name] 
                descs = self.identifier.identify_all(cyberfile_content)
                all_remote_desc += descs
            for pkg_desc in all_remote_desc:
                if self.query["name"] in [i.name for i in pkg_desc.deps]:
                    proceed_desc.append(pkg_desc)
            
            self.format_remote_information(proceed_desc, self.query["name"])
            return 0
        else:
            package_cyberfiles = str(
                self.decider.metadata_cli.acquire_cyberfile(self.query["name"])
            )
            if package_cyberfiles == "None":
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    [
                        "Can not find {}".format(self.query["name"]),
                        "The possible compilation parameters of some packages are restricted",
                        "Such as the perception package only have 'perception-gpu-dev' but no 'perception-dev'"
                    ],
                    exit=False
                )
                return ErrCode.ParamErr

            package_descs = self.identifier.identify_all(package_cyberfiles)
            if self.query["version"] == "":
                self.query["version"] = str(
                    self.decider.metadata_cli.get_latest_version(self.query["name"])
                )
            if self.query["version"] not in [pkg_desc.version for pkg_desc in package_descs]:
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    [
                        "Version {} is not matched with available version {}, skip it".format(
                            self.query["version"], 
                            self.decider.metadata_cli.get_available_version_format(self.query["name"])
                        )
                    ],
                    exit=False
                )
                return ErrCode.ParamErr

            for package_desc in package_descs:
                if package_desc.version == self.query["version"]:
                    targets = [package_desc]
                    break
            package_desc = targets[0]
        logger.info("According parameters above to analysis depends of {}".format(package_desc.name))
        # version determine
        self.decider(targets)
        version_results = self.decider.get_result()
        desc_poll = self.decider.cyberfile_source

        # topological order all targets
        targets, g = build_order([], targets, version_results, desc_poll)

        self.format_information(package_desc, g)
        return 0
    
    def format_remote_information(self, proceed_desc, query_desc_name):
        """format remote packages' depends"""
        if len(proceed_desc) < 1:
            logger.info("There are no packages directly depend on {}".format(query_desc_name))
            return
        logger.info("These following packages directly depend on {}:".format(query_desc_name))
        temp = list()
        for index, desc in enumerate(proceed_desc):
            temp.append(desc)
            if (index + 1) % 4 == 0:
                package_format = ["({})".format(i.name) for i in temp]
                logger.info("  {}".format(", ".join(package_format)))
                temp = list()
        package_format = [i.name for i in temp]
        if len(package_format) > 1:
            logger.info("  {}".format(", ".join(package_format))) 

    def format_information(self, pkg_desc, g):
        """format local packages' depends"""
        delimiter = "|"
        if self.with_indirect:
            childs = g._get_node_by_name(pkg_desc.name).return_all_childs()
            logger.info("{} depends on these following packages:".format(pkg_desc.name))
            proceed_depends = [
                {"name": child, "version": childs[child].version} for child in childs
            ]
        else:
            logger.info("{} directly depends on the following packages:".format(pkg_desc.name))
            proceed_depends = []
            for dep in pkg_desc.deps:
                proceed_depends.append({
                    "name": dep.name, 
                    "version": dep.version_format
                })
                proceed_depends[-1]["version"] = proceed_depends[-1]["version"] \
                    if proceed_depends[-1]["version"] != "" else self.decider.metadata_cli.get_latest_version(dep.name)
        
        temp = list()
        for index, dep in enumerate(proceed_depends):
            temp.append(dep)
            if (index + 1) % 4 == 0:
                package_format = ["({}{}{})".format(i["name"], delimiter, i["version"]) for i in temp]
                logger.info("  {}".format(", ".join(package_format)))
                temp = list()
        package_format = ["({}{}{})".format(i["name"], delimiter, i["version"]) for i in temp]
        if len(package_format) > 1:
            logger.info("  {}".format(", ".join(package_format))) 
            

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            'query', type=str.lstrip, metavar="[query]",
            help="the package name or stored path of which package's depends you want to list"
        )
        parser.add_argument(
            '--depends-on', action="store_true", default=False,
            help="list those packages information which are directly dependent on the package"
        )
        parser.add_argument(
            '--with-indirect', action="store_true", default=False,
            help="list the package all depends, direct and indirect"
        )
        parser.add_argument(
            '--directory', action="store_true", default=False,
            help="list the package infomation which stored in the directory"
        )
        parser.add_argument(
            '--gpu', action='store_true', default=False,
            help='with compilation in GPU parameter'
        )
        parser.add_argument(
            '--cpu', action='store_true', default=False,
            help='with compilation in CPU parameter'
        ) 
        parser.add_argument(
            '--dbg', action='store_true', default=False,
            help='with compilation in debugging parameter'
        )
        

    def set_args(self, args):
        """set runtime arguments"""
        self.args = args

    def process_args(self):
        """process arguments"""
        self.workspace = os.getcwd()
        self.depends_on = True if self.args.depends_on == True else False
        self.spec_dir = True if self.args.directory == True else False
        if self.depends_on and self.spec_dir:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["parameter 'depends-on' and 'directory' are both set to True and it's invalid setting"],
                exit=False
            )
            return ErrCode.ParamErr
        elif not self.depends_on and not self.spec_dir and self.args.query is None:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["package is not set!"],
                exit=False
            )
            return ErrCode.ParamErr

        workspace = Path(self.workspace) / "WORKSPACE"
        if not workspace.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find WORKSPACE in {}".format(self.workspace)],
                exit=False
            )
            return ErrCode.FileIoErr
        
        if not self.spec_dir:
            package = self.args.query
            self.query = {
                "name":     package,
                "version":  ""
            } if "=" not in package else {
                "name":     package.split("=")[0], 
                "version":  package.split("=")[1]
            }
        else:
            if self.args.query[0] != "/":
                self.query = os.path.abspath(os.path.join(self.workspace, self.args.query))
            else:
                self.query = self.args.query
            wrapper = Path(self.query) / "cyberfile.xml"
            if not wrapper.exists():
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["There is no package stored in {}".format(str(self.query))],
                    exit=False
                )
                return ErrCode.FileIoErr

            if not self.query.startswith(self.workspace):
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    ["Package in {} is outside of the workspace {}".format(self.query, self.workspace)],
                    exit=False
                ) 
                return ErrCode.ParamErr

        if self.args.cpu and self.args.gpu:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["Compilation parameter can not set both --cpu and --gpu"],
                exit=False
            ) 
            return ErrCode.ParamErr
        elif self.args.gpu:
            self.cyberfile_gpu = True
        else:
            self.cyberfile_gpu = False
        
        if self.args.dbg:
            self.cyberfile_dbg = True
            self.cyberfile_dev = False
        else:
            self.cyberfile_dbg = False
            self.cyberfile_dev = True 

        if self.args.with_indirect:
            self.with_indirect = True

        return 0    
        
