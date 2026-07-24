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
apt information class
"""
import enum
import shutil
import getpass
import sys
from core.logging import get_logger

logger = get_logger("apollo")

class AptContext(object):
    """apt context"""
    executable = shutil.which('apt') if getpass.getuser() == "root" else "sudo " + shutil.which('apt') 
    install_args = ["install", "-y", "--allow-unauthenticated"]
    reinstall_args = ["install", "--reinstall", "-y", "--allow-unauthenticated"]
    uninstall_args = ['remove', '-y', ">/dev/null 2>&1"]


class AptStatus(enum.Enum):
    """return status of apt"""
    NOT_FOUND = 100
    COMPLETE = 0


class ErrCode(enum.Enum):
    """
    error codes class
    """
    AptErr = 400001
    ArchErr = 400002
    ModuleIsNotInstallErr = 400003
    ActionNotFoundErr = 400004
    ActionIsLoadedErr = 400005
    ModuleConflictErr = 400006
    ModuleMismatchedErr = 400007
    KeyErr = 400008
    FileIoErr = 400010
    BazelErr = 400011
    PackageAttrErr = 400012
    ParamErr = 400013
    OccupiedErr = 400014
    UnittestFailedErr = 400015
    NetworkIoError = 400016
    UnknownErr = 440000

    def send_error(error_code, hints=None, solutions=None, exit=True):
        """
        log the error and possible hints and solutions
        """
        logger.error("Encounter {}".format(error_code))
        if hints:
            if type(hints) == list:
                for hint in hints:
                    logger.error("hint: {}".format(hint))
            else:
                logger.error("hint: {}".format(hints))
        if solutions:
            if type(solutions) == list:
                for solution in solutions:
                    logger.error("solution: {}".format(solution))
            else:
                logger.error("solution: {}".format(solutions))
        if exit:
            sys.exit(error_code.value)