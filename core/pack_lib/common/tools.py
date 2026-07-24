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
"""Tools"""
import subprocess
import os
import shutil
import sys

from core.logging import get_logger

logger = get_logger("deb_maker")

def shell_cmd(cmd, alert_on_failure=True):
    """Execute shell command and return (ret-code, stdout, stderr)."""
    logger.info("SHELL > {}".format(cmd))
    proc = subprocess.Popen(cmd, shell=True, close_fds=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ret = proc.wait()
    stdout = proc.stdout.read().decode('utf-8') if proc.stdout else None
    stderr = proc.stderr.read().decode('utf-8') if proc.stderr else None
    if alert_on_failure and stderr and ret != 0:
        sys.stderr.write('{}\n'.format(stderr))
    return (ret, stdout, stderr)


def is_relative_link(filepath):
    """Find if a file is a relative link."""
    if os.path.islink(filepath):
        link = os.readlink(filepath)
        if not os.path.isabs(link):
            return link
        else:
            return is_relative_link(link)
    else:
        return None


def copy_or_link(src, dst):
    """Copy file if it is not a relative link or recreate the symlink in `dst`."""
    relative_link = is_relative_link(src)
    if relative_link:
        os.symlink(relative_link, dst)
    else:
        shutil.copy2(src, dst)