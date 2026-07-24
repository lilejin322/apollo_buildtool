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
functions set invoking bootstrap command 
"""
import pathlib
import subprocess
import os
import shutil
from core.common import get_config
from core import ErrCode

APOLLO_ROOT = get_config("base", "apollo_root")
APOLLO_PACKAGES_PATH = "{}/packages".format(APOLLO_ROOT)
APOLLO_LIB_PATH = "{}/lib".format(APOLLO_ROOT)

def run_module(module_name):
    """run module"""
    #TODO: support arm64
    setup_device_for_amd64()
    #module_name = (module_name.split("-"))[0]
    cyber_launch = shutil.which("cyber_launch")
    if cyber_launch is None or cyber_launch == "":
        ErrCode.send_error(
            ErrCode.ModuleIsNotInstallErr, 
            ["Could not find cyber_launch. Is cyber already installed?"]
        )

    if "." in module_name and module_name.split(".")[-1] == "launch":
        module_launch = module_name
        if not module_launch.startswith("/"):
            module_launch = os.path.join(os.getcwd(), module_launch)
    else:
        module_path = pathlib.Path("/apollo/modules") / module_name
        module_launch = module_path / "launch" / "{}.launch".format(module_name.split("-")[0])
    if not module_launch.exists():
        ErrCode.send_error(
            ErrCode.ModuleIsNotInstallErr, 
            ["Could not find {}. Is it already built?".format(module_name)]
        )

    log_dir = os.path.join(get_config("base", "apollo_root"), "data/log")
    cmd = "{} start {} >{}.log 2>&1 &".format(
        cyber_launch, module_launch, os.path.join(log_dir, module_name)
    )
    subprocess.run(cmd, shell=True)
    return 0

def check_module_is_running(module_name):
    """check module is running"""
    module_path = pathlib.Path("/apollo/modules") / module_name 
    query = module_path / "launch" / "{}.launch".format(module_name.split("-")[0])
    cmd = "pgrep -f \"{}\" | grep -cv '^1$'".format(query)
    num_processes = int(subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT))
    if num_processes == 0:
        return False
    return True

def double_check_module_is_running(module_name):
    """double check module is running"""
    module_path = pathlib.Path("/apollo/modules") / module_name
    query = module_path / "launch" / "{}.launch".format(module_name.split("-")[0])
    cmd = "pgrep -f \"{}\"".format(query)
    try:
        process_pids_str = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8")
    except:
        return
    process_pids = process_pids_str.split("\n")
    for pid in process_pids:
        if pid == "":
            continue
        ppids = subprocess.check_output(
            "ps --ppid {} |awk '{{if (NR>1){{print $1}}}}'".format(pid), 
            shell=True
        ).decode("utf-8")
        for ppid in ppids.split("\n"):
            if ppid == "":
                continue
            subprocess.run("kill -9 {} >/dev/null 2>&1".format(ppid), shell=True)

        subprocess.run("kill -9 {} >/dev/null 2>&1".format(pid), shell=True)

def stop_module(module_name):
    """stop module"""
    cyber_launch = shutil.which("cyber_launch")
    if cyber_launch is None or cyber_launch == "":
        ErrCode.send_error(
            ErrCode.ModuleIsNotInstallErr, 
            ["Could not find cyber_launch. Is cyber already installed?"]
        )
        
    module_path = pathlib.Path("/apollo/modules") / module_name
    module_launch = module_path / "launch" / "{}.launch".format(module_name.split("-")[0])
    if not module_path.exists():
        ErrCode.send_error(
            ErrCode.ModuleIsNotInstallErr, 
            ["Could not find {}. Is it already built?".format(module_name)]
        )
        
    if check_module_is_running(module_name):
        cmd = "{} stop {}".format(cyber_launch, module_launch)
        subprocess.run(cmd, shell=True)
        # sometime cyber_launch cannot kill the process
        double_check_module_is_running(module_name)
    return 0

def setup_device_for_amd64():
    """setup cancard dev"""
    num_ports = 8
    for i in range(num_ports):
        if pathlib.Path("/dev/can{}".format(i)).exists():
            continue
        elif pathlib.Path("/dev/zynq_can{}".format(i)).exists():
            ret = subprocess.run(
                "sudo ln -snf /dev/zynq_can{} /dev/can{} >/dev/null 2>&1".format(i, i), 
                shell=True
            )
            rc = ret.returncode
            if rc != 0:
                ErrCode.send_error(
                    ErrCode.UnknownErr,
                    ["create device file description failed"]
                )
        else:
            break
