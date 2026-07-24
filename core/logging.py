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
logger
"""
import logging
import sys
import os


APP = os.path.basename(sys.argv[0]).split(".")[0]


"""
colorful logging
"""
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = list(range(8))
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

COLORS = {
    'INFO':     GREEN,
    'WARNING':  YELLOW,
    'DEBUG':    BLUE,
    'ERROR':    RED,
    'CRITICAL': YELLOW
}
    

class ColoredFormatter(logging.Formatter):
    """colored formatter for logger"""
    def __init__(self, msg):
        logging.Formatter.__init__(self, msg)
        
    def format(self, record):
        """format the log"""
        levelname = record.levelname
        if levelname in COLORS:
            if levelname == 'DEBUG':
                record.levelname = COLOR_SEQ % (30 + COLORS[levelname]) + \
                    record.msg.split('#')[0] + RESET_SEQ
                record.msg = COLOR_SEQ % (30 + COLORS[levelname]) + \
                    record.msg.split('#')[-1] + RESET_SEQ
            else:
                record.levelname = COLOR_SEQ % (30 + COLORS[levelname]) + \
                    APP + RESET_SEQ
                record.msg = COLOR_SEQ % (30 + COLORS[levelname]) + levelname + \
                    " " + record.msg.split('#')[-1] + RESET_SEQ
        return logging.Formatter.format(self, record)


def init_logger(name):
    """init logger"""
    logger = logging.getLogger(name)
    color_formatter = ColoredFormatter("[%(levelname)-18s] %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(color_formatter)
    logger.addHandler(console)
    logger.setLevel(logging.INFO)


def get_logger(name):
    """get logger"""
    return logging.getLogger(name)

