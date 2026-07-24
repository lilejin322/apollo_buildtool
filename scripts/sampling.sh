#! /usr/bin/env bash

###############################################################################
# Copyright 2020 The Apollo Authors. All Rights Reserved.
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

set -e

TOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

INPUT_FILES=$@

[[ -z $INPUT_FILES ]] && (echo >&2 -e "[\033[0;31mERROR\033[0m] sampling files not specified. Exiting ...") && exit 1

CBT_FILE="profile.cbt"
SVG_FILE="profile.svg"

[[ ! `which pprof` ]] && sudo wget "https://apollo-system.cdn.bcebos.com/archive/9.0/pprof" -O /usr/bin/pprof

[[ ! `which flamegraph.pl` ]] && \
    git clone --progress https://github.com/brendangregg/FlameGraph.git ~/FlameGraph && \
    sudo ln -snf ~/FlameGraph/flamegraph.pl /usr/bin/flamegraph.pl


pprof --collapsed $(which cyber_benchmark_writer) $INPUT_FILES > ${CBT_FILE}

flamegraph.pl ${CBT_FILE} > ${SVG_FILE}

rm -f ${CBT_FILE}

