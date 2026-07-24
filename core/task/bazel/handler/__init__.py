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
"""Common class and function during building procedure"""
import os
import subprocess
import sys
import time
from pathlib import Path
from core.package_descriptor import Status

from core import ErrCode
from core.logging import get_logger
from core.common import get_template, get_config, get_setup
from core.action import apollo_prefix
from core.package_descriptor import PackageDesc
from core.package_identification.identifier import PackageIdentification
from core.package_identification.identifier import singleton

logger = get_logger('buildtool')

delimiter = "#######################################APOLLO#######################################"

def progressbar(it, length, prefix="", out=sys.stdout,):
    """get the progressbar output of procedure"""
    count = length
    start = time.time()
    try:
        size = int(os.get_terminal_size().columns / 4)
    except:
        size = 5
    def show(j):
        if count == 0:
            return
        x = int(size * j / count)
        remaining = ((time.time() - start) / j) * (count - j)
        
        mins, sec = divmod(remaining, 60)
        time_str = f"{int(mins):02}:{sec:05.2f}"
        
        print(f"  {prefix}[{'#'*x}{('.'*(size-x))}] {j}/{count} Est wait {time_str}",
            end='\r', file=out, flush=True)
        
    for i, item in enumerate(it):
        yield item
        show(i + 1)
    # clear last line
    try:
        print(" " * os.get_terminal_size().columns, end="\r")
    except:
        pass

def _is_deprecated_package(pkg_desc):
    normal_path = os.path.join(
        get_config("base", "apollo_root"),
        get_config("base", "package_meta_prefix"),
        pkg_desc.name
    )
    if os.path.exists(normal_path):
        return False
    return True

@singleton
class Procedure(object):
    """Procedure class is to store all build procedure"""
    def __init__(self):
        self.init_func_info_list = list()
        self.workspace_deps_list = list()
        self.workspace_deps_dict = dict()
        self.replace_content_list = list()
        self.third_wrapper_info_list = list()
        self.runtime_lib_path = list()
        self.online = True
        self.installed_packages = None
        self._check_network()

    def _check_network(self):
        cmd = ["curl", get_config("api", "login"), ">/dev/null 2>&1"]
        if subprocess.call(" ".join(cmd), shell=True) != 0:
            self.online = False

    def get_network_status(self):
        return self.online

    def init_installed_packages(self):
        if self.installed_packages is not None:
            return
        self.installed_packages = dict()
        dpkg_raw_output_pakcages = list()
        dpkg_formatted_output = list()

        cmd = "dpkg -l"
        dpkg_raw_output_list = subprocess.check_output(cmd, shell=True).decode("utf-8").split("\n")
        
        for single_line in dpkg_raw_output_list:
            if single_line.startswith("ii"):
                dpkg_raw_output_pakcages.append(single_line)
        
        for package_line in dpkg_raw_output_pakcages:
            package_info_list = list()
            package_raw_info_list = package_line.split(" ")
            for package_raw_info in package_raw_info_list:
                if package_raw_info != "":
                    package_info_list.append(package_raw_info)
            dpkg_formatted_output.append(package_info_list)

        for package_info in dpkg_formatted_output:
            if ":" in package_info[1]:
                package_info[1] = package_info[1].split(":")[0]
            self.installed_packages[package_info[1]] = package_info[2]
        return

    def add_runtime_lib_path(self, path):
        """add runtime depend lib path"""
        self.runtime_lib_path.append(path)

    def add_init_func_info(self, init_func_wrapper):
        """add init function infomation"""
        self.init_func_info_list.append(init_func_wrapper)

    def add_workspace_dep(self, dep, pkg_desc):
        """add workspace depend"""
        if dep is None:
            return
        if dep in [self.workspace_deps_dict[k] for k in self.workspace_deps_dict]:
            duplicate_dep = None
            for k in self.workspace_deps_dict:
                if self.workspace_deps_dict[k] == dep:
                    duplicate_dep = k
                    break
            ErrCode.send_error(
                ErrCode.ModuleConflictErr,
                [
                    "multiple external packages duplicated",
                    "{} -> {}".format(duplicate_dep, dep),
                    "{} -> {}".format(pkg_desc.name, dep),
                ]
            )
        self.workspace_deps_dict[pkg_desc.name] = dep
        #self.workspace_deps_list.append(dep)

    def add_replace_content(self, src):
        """add replace content"""
        self.replace_content_list.append(src)

    def add_third_wrapper_info(self, third_binary_info):
        """add infomation of third-wrapper package"""
        self.third_wrapper_info_list.append(third_binary_info)

    def init_workspace(self, workspace_file_path, targets, index):
        """init user workspace"""
        grpc_in_targets = False
        rule_proto_in_targets = False
        bazel_skylib_in_targets = False

        if index < len(targets):
            for i in range(index+1):
                if "grpc" in targets[i].name:
                    grpc_in_targets = True
                if "rules-proto" in targets[i].name:
                    rule_proto_in_targets = True
                if "bazel-skylib" in targets[i].name:
                    bazel_skylib_in_targets = True

        workspace_wrapper = Path(workspace_file_path)
        if not workspace_wrapper.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find {}".format(workspace_file_path)],
                exit=False
            )
            return False
        workspace_content = None
        with workspace_wrapper.open("r+", encoding="utf-8") as f:
            workspace_content = f.readlines()
        for i in range(len(workspace_content)):
            while "\n" in workspace_content[i]: 
                workspace_content[i] = workspace_content[i].replace("\n", "")

        if delimiter in workspace_content:
            generated_content_index = list()
            for i in range(len(workspace_content)):
                if delimiter in workspace_content[i]:
                    generated_content_index.append(i)
            if len(generated_content_index) == 2:
                start_index, end_index = generated_content_index[0], generated_content_index[1]
                up_content = []
                down_content = []
                if start_index > 0:
                    up_content += workspace_content[: start_index]
                if end_index < len(workspace_content) - 1:
                    down_content += workspace_content[end_index + 1: ]
            elif len(generated_content_index) == 0:
                pass
            else:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["Process WORKSPACE file error!"],
                    exit=False
                )
                return False
        else:
            up_content = workspace_content
            down_content = []

        user_up_content = "\n".join(up_content)
        user_down_content = "\n".join(down_content) 

        init_content = get_template("workspace.in")
        init_content += '\nload("//dev/bazel:deps.bzl", "init_deps")\ninit_deps()\n'
        
        if grpc_in_targets:
            grpc_init_content = 'load("@com_github_grpc_grpc//bazel:grpc_deps.bzl", "grpc_deps")\ngrpc_deps()\nload("@com_github_grpc_grpc//bazel:grpc_extra_deps.bzl", "grpc_extra_deps")\ngrpc_extra_deps()\n'
        else:
            grpc_init_content = ''
        
        if rule_proto_in_targets:
            rule_proto_content = 'load("@rules_proto//proto:repositories.bzl", "rules_proto_dependencies", "rules_proto_toolchains")\nrules_proto_dependencies()\nrules_proto_toolchains()\n'
        else:
            rule_proto_content = ''
        
        if bazel_skylib_in_targets:
            bazel_skylib_content = 'load("@bazel_skylib//:workspace.bzl", "bazel_skylib_workspace")\nbazel_skylib_workspace()\n'
        else:
            bazel_skylib_content = '' 
        
        workspace_content = delimiter + init_content + bazel_skylib_content + grpc_init_content + rule_proto_content + delimiter + "\n"
        workspace_content = user_up_content + "\n" + workspace_content + user_down_content
        
        with workspace_wrapper.open("w+", encoding="utf-8") as f:
            f.write(workspace_content)

        apollo_root = get_config("base", "apollo_root")
        content = get_setup()
        if content is None:
            return False
        with open(os.path.join(apollo_root, "setup.sh"), "w+", encoding="utf-8") as f:
            f.write(content)
        return True
    
    def init_workspace_deps(self, childs_dict):
        """import workspace depends"""
        childs = [childs_dict[i].name for i in childs_dict]
        self.workspace_deps_list = []
        for child in childs:
            if child in self.workspace_deps_dict:
                self.workspace_deps_list.append(self.workspace_deps_dict[child])
        self.workspace_deps_list = ",".join(self.workspace_deps_list).split(",")
        self.workspace_deps_list.sort()

    def import_depends(self, workspace_path: str, **kwargs):
        """import depends for building package"""
        dev_path = "dev/bazel/"
        deps_file_stored_path = Path(workspace_path) / dev_path
        if not deps_file_stored_path.exists():
            _create_pre_folders("dev/bazel/", workspace_path)
        deps_file_wrapper = deps_file_stored_path / "deps.bzl"
        if deps_file_wrapper.exists():
            deps_file_wrapper.unlink()

        load_headers = "\n".join(
            [i.load_header for i in self.third_wrapper_info_list]
        ) if len(self.third_wrapper_info_list) > 0 else "\n"

        init_func_content = "def clean_dep(dep):\n    return str(Label(dep))\n"

        init_func_content += "\n".join(
            [i.content for i in self.init_func_info_list]
        ) if len(init_func_content) > 0 else "\n"

        entry_func = "def init_deps():\n"
        entry_func_content = "\n".join(
            ["    {}()".format(i.name) for i in self.third_wrapper_info_list]
        ) if len(self.third_wrapper_info_list) > 0 else "    pass"
        entry_func_content += "\n" 
        entry_func_content += "\n".join(
            ["    {}()".format(i.name) for i in self.init_func_info_list]
        ) if len(self.init_func_info_list) > 0 else ""
        if entry_func_content == "":
            entry_func_content = "    pass"
        
        content = load_headers + "\n" + init_func_content + "\n" + entry_func + entry_func_content
        with deps_file_wrapper.open("w+", encoding="utf-8") as f:
            f.write(content)

        # Replace src and import workspace depends
        if kwargs["target"] == True:
            bazel_support_file_wrapper = Path(workspace_path) / "tools" / "package" / "rules_cc.patch"
            bazel_support_default_file_wrapper = Path(workspace_path) / "tools" / "package" / "rules_cc.release.patch"
            if not bazel_support_default_file_wrapper.exists():
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["Can not find apollo-neo-tools depend!"],
                    ["Import it to cyberfile.xml"],
                    exit=False
                ) 
                return False

            with bazel_support_default_file_wrapper.open("r", encoding="utf-8") as f:
                bazel_support_default_content = f.read()

            childs_desc = kwargs["childs"]
            self.init_workspace_deps(childs_desc)

            bazel_support_replace_content = bazel_support_default_content.replace("@@SRC_REPLACEMENT@@", ",".join(self.replace_content_list))
            bazel_support_replace_content = bazel_support_replace_content.replace("@@GEN_WS_DEPS@@", ",".join(self.workspace_deps_list))

            with bazel_support_file_wrapper.open("w+", encoding="utf-8") as f:
                f.write(bazel_support_replace_content)

        return True


class ThirdBinaryInfo(object):
    """third-wrapper package information"""
    def __init__(self, load_header, name):
        self.load_header = load_header
        self.name = name

class InitWrapper(object):
    """inif function info wrapper"""
    def __init__(self, content, name):
        self.content = content
        self.name = name


def link_target(src: str, dst: str):
    """link function"""
    if not Path(src).exists():
        logger.warning("Source {} does not exist".format(src))
        return False
    dst_wrapper = Path(dst)
    if dst_wrapper.is_symlink():
        subprocess.run("sudo rm -f {}".format(dst), shell=True)

    if dst_wrapper.exists():
        logger.warning("Path {} is occupied".format(dst))
        return False
    
    try:
        subprocess.run("sudo ln -snf {} {}".format(src, dst), shell=True)
        # os.symlink(src, dst)
    except Exception as ex:
        logger.warning("Create soft link error: {}".format(str(ex)))
        return False
    return True

def func_name_check(func_name: str, pkg_desc: PackageDesc):
    """check function name is valid and modify it"""
    if pkg_desc.type.startswith("third"):
        func_name = "{}{}".format(apollo_prefix, func_name)
    elif pkg_desc.type == "module":
        func_name = "{}{}".format(apollo_prefix, func_name)
    elif pkg_desc.type == "system":
        func_name = "{}{}".format("system-", func_name)
    else:
        pass
    while "-" in func_name:
        func_name = func_name.replace("-", "_")
    while "." in func_name:
        func_name = func_name.replace(".", "")
    return func_name

def _read_origin_package_name(pkg_desc: PackageDesc):
    cyberfile_in_ws_content = None 
    package_cyberfile = Path(pkg_desc.workspace) / "cyberfile.xml"
    with package_cyberfile.open("r", encoding="utf-8") as f:
        cyberfile_in_ws_content = f.read()

    ider = PackageIdentification()
    local_desc = PackageDesc()
    ider.identify(local_desc, cyberfile_in_ws_content)
    if local_desc.status == Status.INVALID:
        ErrCode.send_error(
            ErrCode.PackageAttrErr,
            ["{} with invalid status".format(local_desc.name)]
        )

    return local_desc.name

def _determine_repo_name(pkg_desc: PackageDesc):
    if pkg_desc._local_name is None:
        return pkg_desc.name if not pkg_desc.name[0].isdigit() \
            else "{}-{}".format("placeholder", pkg_desc.name)
    else:
        return pkg_desc._local_name if not pkg_desc._local_name[0].isdigit() \
            else "{}-{}".format("placeholder", pkg_desc._local_name) 

def _dertermine_workspace_dep_name(pkg_desc: PackageDesc):
    if pkg_desc.expose is None or pkg_desc.expose == "True":
        if _determine_repo_name(pkg_desc).startswith("//"):
            # third_wrapper expose
            head = _determine_repo_name(pkg_desc)
            if pkg_desc._lib_names is None:
                lib_name = head.split("/")[-1]
                lib_name_list = [lib_name]
            else:
                lib_name_list = pkg_desc._lib_names.split(",")
    
            return ",".join(["{}:{}".format(head, i) for i in lib_name_list])
        else:
            head = "@{}".format(_determine_repo_name(pkg_desc))
    
            if pkg_desc._lib_names is None:
                return "{}//:{}".format(head, _determine_repo_name(pkg_desc))

            lib_name_list = pkg_desc._lib_names.split(",")
            return ",".join(["{}//:{}".format(head, lib_name) for lib_name in lib_name_list])
    else:
        return None

def _package_name_to_dir(name: str):
    return name.replace(apollo_prefix, "")

def generate_init_func_content(pkg_desc: PackageDesc, deps_file: str, workspace: str, local=False):
    """generate init function content"""
    template = get_template("deps.in")
    if template is None:
        return template
    func_name = "{}_repo".format(pkg_desc.name)
    func_name = func_name_check(func_name, pkg_desc)
    # if local:
    #     # it seem the repo name of package in workspace can not affect building process
    #     # it is not necessary to reset it's repo name
    #     # if pkg_desc.workspace is not None:
    #     #     name = _read_origin_package_name(pkg_desc)
    #     # else:
    #     name = _determine_repo_name(pkg_desc)
    #     path = os.path.join(
    #         get_config("base", "apollo_root"), 
    #         "packages", 
    #         "{}".format(pkg_desc.name),
    #         "local"
    #     )
    # else:
    #     name = _determine_repo_name(pkg_desc)
    #     path = os.path.join(
    #         get_config("base", "apollo_root"), 
    #         "packages", 
    #         "{}".format(pkg_desc.name),
    #         "latest"
    #     )
    name = _determine_repo_name(pkg_desc)
    if _is_deprecated_package(pkg_desc):
        path = os.path.join(
            get_config("base", "apollo_root"), 
            "packages", 
            "{}".format(pkg_desc.name),
            "latest"
        )
    else:
        path = get_config("base", "apollo_root")
    
    deps_file_bazel_format = _build_wrapper_to_bazel_format(deps_file, workspace)

    template = template.replace("@@FUNC@@", func_name)
    template = template.replace("@@NAME@@", name)
    template = template.replace("@@BUILD_FILE@@", deps_file_bazel_format)
    template = template.replace("@@LOCAL_PATH@@", path)

    return InitWrapper(template, func_name)

def generate_third_binary_init_func_content(pkg_desc: PackageDesc, deps_file: str, workspace: str):
    template = get_template("deps.in")
    if template is None:
        return template
    func_name = "{}_repo".format(pkg_desc.name)
    func_name = func_name_check(func_name, pkg_desc)

    name = _determine_repo_name(pkg_desc)
    #if pkg_desc._local_name is None:
    #    name = pkg_desc.name
    #else:
    #    name = pkg_desc._local_name

    path = os.path.join(
        get_config("base", "apollo_root"), 
        "packages", 
        "{}".format(pkg_desc.name),
        "latest"
    )

    deps_file_bazel_format = _build_wrapper_to_bazel_format(deps_file, workspace)
    template = template.replace("@@FUNC@@", func_name)
    template = template.replace("@@NAME@@", name)
    template = template.replace("@@BUILD_FILE@@", deps_file_bazel_format)
    template = template.replace("@@LOCAL_PATH@@", path)
    return InitWrapper(template, func_name) 
    

def generate_system_package_content(pkg_desc: PackageDesc, deps_file: str, workspace: str):
    """generate system package content"""
    template_build = get_template("system.BUILD.in")
    template_init_func = get_template("deps.in")
    if template_build is None or template_init_func is None:
        return None, None
    
    name = _determine_repo_name(pkg_desc)
    #if pkg_desc._local_name is None:
    #    name = pkg_desc.name
    #else:
    #    name = pkg_desc._local_name

    if pkg_desc.so_names is None:
        lib = ""
    else:
        lib = "\n".join(["\"-l{}\",".format(i) for i in pkg_desc.so_names.split(",")])

    template_build = template_build.replace("@@NAME@@", name)
    template_build = template_build.replace("@@LIB@@", lib)

    func_name = "{}_repo".format(pkg_desc.name)
    func_name = func_name_check(func_name, pkg_desc)
    path = "/usr/include"
    
    deps_file_bazel_format = _build_wrapper_to_bazel_format(deps_file, workspace)
    template_init_func = template_init_func.replace("@@FUNC@@", func_name)
    template_init_func = template_init_func.replace("@@NAME@@", name)
    template_init_func = template_init_func.replace("@@BUILD_FILE@@", deps_file_bazel_format)
    template_init_func = template_init_func.replace("@@LOCAL_PATH@@", path)

    return InitWrapper(template_init_func, func_name), template_build

def _build_wrapper_to_bazel_format(deps_file, workspace):
    """change absolute of build file to bazel accepted format"""
    deps_file_bazel_format = deps_file.replace(workspace, "")
    if deps_file_bazel_format.startswith("/"):
        deps_file_bazel_format = "/{}".format(deps_file_bazel_format)
    else:
        deps_file_bazel_format = "//{}".format(deps_file_bazel_format)
    deps_file_bazel_format_list = deps_file_bazel_format.split("/")
    former_value = deps_file_bazel_format_list[0: len(deps_file_bazel_format_list)-1]
    build_file = deps_file_bazel_format_list[-1]
    deps_file_bazel_format = "{}:{}".format("/".join(former_value), build_file)
    return deps_file_bazel_format


def _null_func(pkg_desc: PackageDesc):
    return 

def _create_pre_folders(src: str, workspace: str, buildfile=True):
    pre_folders = src.split("/")
    pre_folders = pre_folders[: len(pre_folders)-1]
    root = workspace
    for i in pre_folders:
        root = os.path.join(root, i)
        os.makedirs(root, exist_ok=True)
        if buildfile:
            (Path(root) / "BUILD").touch()
