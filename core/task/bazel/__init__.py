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
"""bazel executable"""
import sys
import platform
import shutil
from core import ErrCode
from core.action import apollo_prefix
from core.common import get_config

BAZEL_EXECUTABLE = shutil.which("bazel")

class BazelBaseTask(object):
    """base task class"""
    def __init__(self):
        if BAZEL_EXECUTABLE is None:
            ErrCode.send_error(
                ErrCode.BazelErr,
                ["could not find bazel"]
            )

    def _check_necessaries(self, ws):
        build_file = ws / "BUILD"
        if not build_file.is_file():
            raise RuntimeError("BUILD not found")
            
    def _add_basic_args(self, bazel_args, known_options, nproc, memories=0.75, jobs=-1):
        mem_limit = 0.75
        args_str = None
        if type(known_options) == list:
            args_str = " ".join(known_options)
        elif type(known_options) == str:
            args_str = known_options
        else:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["Error type setting of args"]
            )

        if type(bazel_args) == list:
            args_str += " {}".format(" ".join(bazel_args))
        elif type(bazel_args) == str:
            args_str += " {}".format(bazel_args)
        else:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["Error type setting of args"]
            )

        if jobs > 0 and jobs <= int(nproc):
            nproc = jobs

        if memories > 0 and memories <= 1:
            mem_limit = memories

        if "--jobs" not in args_str:
            args_str += " --jobs={}".format(nproc)
        if "--local_ram_resources" not in args_str:
            args_str += " --local_ram_resources=HOST_RAM*{}".format(mem_limit)

        march_config = get_config("compile", "march")
        args_str += " --copt={} --host_copt={}".format(march_config, march_config)
        if platform.machine() == "aarch64":
            args_str += " --copt=-fPIC --host_copt=-fPIC"
        return [args_str]
