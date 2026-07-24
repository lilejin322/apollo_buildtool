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
"""request metadata"""
import shutil
import subprocess
import requests
import hashlib
import os

from pathlib import Path
from core import ErrCode
from core.version_decide.semver import Version
from core.common import get_config, get_logger
from core.action import apollo_prefix
from core.package_identification.identifier import singleton
from core.task.bazel.handler import Procedure

logger = get_logger("apollo")

@singleton
class MetaDataCli(object):
    def __init__(self):
        self.metadata_request_url = get_config("url", "metadata")
        self.raw_metadata_pool = dict()
        self.raw_version_pool = dict()
        self.raw_cyberfile_path_pool = dict()
        self.raw_cyberfile_pool = dict()
        self.cyberfile_source = dict()
        self.procedure = Procedure()
        self.online = self.procedure.get_network_status()
        self.need_cached = False
        self._init_metadata()
    
    def _init_metadata(self):
        raw_metadatas_file = get_config("url", "offline_metadata")
        raw_metadatas = None

        if self.online:
            raw_metadatas_resp = requests.get(self.metadata_request_url)
            if raw_metadatas_resp.status_code != 200:
                ErrCode.send_error(
                    ErrCode.NetworkIoError,
                    [
                        "Request packages metadata failed! Status code={}".format(
                            raw_metadatas_resp.status_code
                        )
                    ]
                )

            raw_metadatas = raw_metadatas_resp.text
        
            if not Path(raw_metadatas_file).exists():
                self.need_cached = True 
            else:    
                local_cached_md5 = None
                with open(raw_metadatas_file, "r") as f:
                    local_cached_md5 = hashlib.md5(f.read().encode('utf-8')).hexdigest()

                raw_metadatas_md5 = hashlib.md5(raw_metadatas.encode('utf-8')).hexdigest() 
                if raw_metadatas_md5 != local_cached_md5:
                    self.need_cached = True

        else:
            if not Path(raw_metadatas_file).exists():
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["can not find metadata file"]
                )

            with open(raw_metadatas_file, "r") as f:
                raw_metadatas = f.read()

        raw_metadata_list = raw_metadatas.split("\n\n")

        # parse metadata
        for i in raw_metadata_list:
            if i == "":
                continue
            terms = i.split("\n")
            terms_dict = dict()
            for term in terms:
                k, v = term.split(":")[0], term.split(":")[1]
                terms_dict[k] = v
            
            if terms_dict["Package"].strip() in self.raw_metadata_pool:
                self.raw_metadata_pool[terms_dict["Package"].strip()].append(terms_dict)
            else:
                self.raw_metadata_pool[terms_dict["Package"].strip()] = [terms_dict]
        if self.online:
            for _, name in enumerate(self.raw_metadata_pool):
                # parse cyberfile path
                self.raw_cyberfile_path_pool[name] = [
                    "{}/{}".format(
                        get_config("url", "head"), (".".join(
                            (i["Filename"].split("."))[: len(i["Filename"].split("."))-1] \
                                + ["cyberfile"]).strip()
                        )
                    ) for i in self.raw_metadata_pool[name]
                ]

                # parse version
                self.raw_version_pool[name] = [
                    Version.parse(i["Version"].strip()) for i in self.raw_metadata_pool[name]
                ]
        else:
            for _, name in enumerate(self.raw_metadata_pool):
                # parse cyberfile path
                self.raw_cyberfile_path_pool[name] = [
                    "{}".format(
                        ((".".join(
                            (i["Filename"].split("."))[: len(i["Filename"].split("."))-1] \
                                + ["cyberfile"]).strip()
                        ).split("/"))[-1]
                    ) for i in self.raw_metadata_pool[name]
                ] 

                # parse version
                self.raw_version_pool[name] = [
                    Version.parse(i["Version"].strip()) for i in self.raw_metadata_pool[name]
                ]

        for k in self.raw_version_pool:
            self.raw_version_pool[k].sort()

        if self.need_cached:
            cyberfiles_dir_wrapper = Path(get_config("url", "offline_cyberfile_repo"))
            cached_dir_splited = get_config("url", "offline_metadata").split("/")
            cached_dir_wrapper = Path("/".join(cached_dir_splited[: len(cached_dir_splited)-1]))

            if cached_dir_wrapper.exists() and cached_dir_wrapper.is_dir():
                subprocess.run("sudo chmod -R 777 {}".format(str(cached_dir_wrapper)), shell=True)   
                shutil.rmtree(str(cached_dir_wrapper))
            if cached_dir_wrapper.exists():
                ErrCode.send_error(
                    ErrCode.OccupiedErr,
                    ["cache dir {} have been occupied"]
                )
            os.makedirs(str(cached_dir_wrapper))
            subprocess.run("sudo chmod -R 777 {}".format(str(cached_dir_wrapper)), shell=True)
            
            if cyberfiles_dir_wrapper.exists() and cyberfiles_dir_wrapper.is_dir():
                shutil.rmtree(str(cyberfiles_dir_wrapper))
            if cyberfiles_dir_wrapper.exists():
                ErrCode.send_error(
                    ErrCode.OccupiedErr,
                    ["cache dir {} have been occupied"]
                )
            os.makedirs(str(cyberfiles_dir_wrapper))   

            self._cached_all_cyberfile(cyberfiles_dir_wrapper)

            with open(raw_metadatas_file, "w+") as f:
                f.write(raw_metadatas)

    def _cached_all_cyberfile(self, cyberfiles_dir_wrapper):
        logger.info("update the local cache, this process will take a while...")
        for name in self.raw_cyberfile_path_pool:
            request_urls = self.raw_cyberfile_path_pool[name]
            for request_url in request_urls:
                cyberfile_name = request_url.split("/")[-1]
                cyberfile_save_path = os.path.join(str(cyberfiles_dir_wrapper), cyberfile_name)
                ret = subprocess.run(
                    "wget -O {} {} >/dev/null 2>&1".format(
                        cyberfile_save_path, request_url
                    ), shell=True
                )
                if ret.returncode != 0:
                    ErrCode.send_error(
                        ErrCode.NetworkIoError,
                        ["download {} failed".format(cyberfile_name)],
                        exit=False
                    )
        logger.info("update local cache complete")

    
    def init_all_cyberfile(self):
        for name in self.raw_cyberfile_path_pool:
            self.acquire_cyberfile(name)

    def acquire_cyberfile(self, name: str):
        # format name to repo package name
        name = self.change_package_name(name)
        if name not in self.raw_cyberfile_path_pool:
            # system package or not found
            return None 
        else:
            if self.online:
                if name not in self.cyberfile_source:
                    # request cyberfile and format
                    self.raw_cyberfile_pool[name] = list()
                    for cyberfile_url in self.raw_cyberfile_path_pool[name]:
                        cyberfile_resp = requests.get(cyberfile_url)
                        if cyberfile_resp.status_code != 200:
                            ErrCode.send_error(
                                ErrCode.NetworkIoError,
                                [
                                    "Request {} failed!".format(cyberfile_url),
                                    "Get metadata of {} failed!".format(name)
                                ]
                            )

                        self.raw_cyberfile_pool[name].append(cyberfile_resp.text)
                    if len(self.raw_cyberfile_pool[name]) == 0:
                        ErrCode.send_error(
                            ErrCode.NetworkIoError,
                            ["Can not get any metadata of {}".format(name)]
                        )

                
                    # construct cyberfile
                    self.cyberfile_source[name] = "<root>\n" + "\n".join(self.raw_cyberfile_pool[name]) + "\n</root>"
            else:
                if name not in self.cyberfile_source:
                    self.raw_cyberfile_pool[name] = list()
                    for cyberfile_name in self.raw_cyberfile_path_pool[name]:
                        cyberfile_path = os.path.join(
                            get_config("url", "offline_cyberfile_repo"),
                            cyberfile_name
                        )
                        if not Path(cyberfile_path).exists():
                            ErrCode.send_error(
                                ErrCode.FileIoErr,
                                ["can not get {}".format(cyberfile_path)]
                            )

                        with open(cyberfile_path, "r") as f:
                            cyberfile_content = f.read()
                        self.raw_cyberfile_pool[name].append(cyberfile_content) 
                    if len(self.raw_cyberfile_pool[name]) == 0:
                        ErrCode.send_error(
                            ErrCode.NetworkIoError,
                            ["Can not get any metadata of {}".format(name)]
                        )

                    self.cyberfile_source[name] = "<root>\n" + "\n".join(self.raw_cyberfile_pool[name]) + "\n</root>" 
            
            return self.cyberfile_source[name]
        
    def get_available_version_format(self, name: str):
        prefix_name = self.change_package_name(name)
        cyber_content = self.acquire_cyberfile(name)
        if cyber_content is None:
            return None

        version_range = self.raw_version_pool[prefix_name]
        if len(version_range) > 1:
            return ">={} <={}".format(version_range[0], version_range[-1])
        else:
            return "={}".format(version_range[-1])
    
    def get_recached_flags(self):
        return self.need_cached

    def get_latest_version(self, name: str):
        prefix_name = self.change_package_name(name)
        cyber_content = self.acquire_cyberfile(name)
        if cyber_content is None:
            return None

        version_range = self.raw_version_pool[prefix_name]
        return version_range[-1] 

    def change_package_name(self, name):
        if apollo_prefix not in name:
            return "{}{}".format(apollo_prefix, name)
        return name 
  