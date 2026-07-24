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
support function of identifier
"""
from core import ErrCode




TARGET_MAPPER = dict()
TARGET_MAPPER['cmake'] = "CMakeLists.txt"
TARGET_MAPPER['bazel'] = "BUILD"


def get_target_file_name(target: str):
    try:
        return TARGET_MAPPER[target]
    except KeyError:
        ErrCode.send_error(
            ErrCode.PackageAttrErr,
            ["target {} is not implemented, pass".format(target)],
            exit=False
        )
        raise NotImplementedError


