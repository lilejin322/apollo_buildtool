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
[
    FOREGROUND_COLOR_BLACK,
    FOREGROUND_COLOR_RED,
    FOREGROUND_COLOR_GREEN,
    FOREGROUND_COLOR_YELLOW,
    FOREGROUND_COLOR_BLUE,
    FOREGROUND_COLOR_MAGENTA,
    FOREGROUND_COLOR_CYAN,
    FOREGROUND_COLOR_WHITE,
] = [x + 30 for x in range(8)]
FOREGROUND_COLORS = {
    FOREGROUND_COLOR_BLACK,
    FOREGROUND_COLOR_RED,
    FOREGROUND_COLOR_GREEN,
    FOREGROUND_COLOR_YELLOW,
    FOREGROUND_COLOR_BLUE,
    FOREGROUND_COLOR_MAGENTA,
    FOREGROUND_COLOR_CYAN,
    FOREGROUND_COLOR_WHITE,
}
[
    BACKGROUND_COLOR_BLACK,
    BACKGROUND_COLOR_RED,
    BACKGROUND_COLOR_GREEN,
    BACKGROUND_COLOR_YELLOW,
    BACKGROUND_COLOR_BLUE,
    BACKGROUND_COLOR_MAGENTA,
    BACKGROUND_COLOR_CYAN,
    BACKGROUND_COLOR_WHITE,
] = [x + 40 for x in range(8)]
BACKGROUND_COLORS = {
    BACKGROUND_COLOR_BLACK,
    BACKGROUND_COLOR_RED,
    BACKGROUND_COLOR_GREEN,
    BACKGROUND_COLOR_YELLOW,
    BACKGROUND_COLOR_BLUE,
    BACKGROUND_COLOR_MAGENTA,
    BACKGROUND_COLOR_CYAN,
    BACKGROUND_COLOR_WHITE,
}
[
    TEXT_PROP_DEFAULT,
    TEXT_PROP_BOLD,
    TEXT_PROP_NOT_BOLD,
    TEXT_PROP_UNDERSCORE,
    TEXT_PROP_NOT_UNDERSCORE,
    TEXT_PROP_BLINK,
    TEXT_PROP_NOT_BLINK,
    TEXT_PROP_INVERS,
    TEXT_PROP_NOT_INVERS,
] = [0, 1, 22, 4, 24, 5, 25, 7, 27]
TEXT_PROPS = {
    TEXT_PROP_DEFAULT,
    TEXT_PROP_BOLD,
    TEXT_PROP_NOT_BOLD,
    TEXT_PROP_UNDERSCORE,
    TEXT_PROP_NOT_UNDERSCORE,
    TEXT_PROP_BLINK,
    TEXT_PROP_NOT_BLINK,
    TEXT_PROP_INVERS,
    TEXT_PROP_NOT_INVERS,
}
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = [
    x + 30 for x in range(8)]
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

LOGLEVEL_COLORS = {
    'DEBUG':    (FOREGROUND_COLOR_BLUE, None, TEXT_PROP_DEFAULT),
    'INFO':     (FOREGROUND_COLOR_GREEN, None, TEXT_PROP_BOLD),
    'WARNING':  (FOREGROUND_COLOR_YELLOW, None, TEXT_PROP_BOLD),
    'ERROR':    (FOREGROUND_COLOR_RED, None, TEXT_PROP_BOLD),
    'CRITICAL': (FOREGROUND_COLOR_RED,
                 BACKGROUND_COLOR_YELLOW,
                 [TEXT_PROP_BOLD, TEXT_PROP_BLINK]),
}


def colorize(string, fore_color=None, back_color=None, props=None):
    """colorize the string
    """
    ctrls = []

    if isinstance(props, int):
        if props not in TEXT_PROPS:
            # invalid property
            ctrls.append(TEXT_PROP_DEFAULT)
        else:
            ctrls.append(props)
    elif isinstance(props, (tuple, list)):
        for prop in props:
            if prop in TEXT_PROPS:
                ctrls.append(prop)

    if fore_color in FOREGROUND_COLORS:
        ctrls.append(fore_color)

    if back_color in BACKGROUND_COLORS:
        ctrls.append(back_color)

    return f'''\033[{';'.join(map(str, ctrls))}m{string}\033[0m'''


class ColoredFormatter(logging.Formatter):
    """colored formatter for logger"""

    def __init__(self, fmt, datefmt):
        logging.Formatter.__init__(self, fmt, datefmt)

    def format(self, record):
        """format the log"""
        levelname = record.levelname
        if levelname in LOGLEVEL_COLORS:
            record.name = colorize(record.name,
                                   FOREGROUND_COLOR_BLUE,
                                   None,
                                   [TEXT_PROP_BOLD])
            record.levelname = colorize(levelname, *LOGLEVEL_COLORS[levelname])
            record.msg = colorize(record.msg, *LOGLEVEL_COLORS[levelname])
        return logging.Formatter.format(self, record)


def init_logger(name):
    """init logger"""
    logger = logging.getLogger(name)
    color_formatter = ColoredFormatter(
        "[%(name)s] %(asctime)s %(levelname)-8s %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setFormatter(color_formatter)
    logger.addHandler(console)
    logger.setLevel(logging.INFO)


def get_logger(name):
    """get logger"""
    return logging.getLogger(name)
