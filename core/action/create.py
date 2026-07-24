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
create verb implement
TODO: Manage third-party packages through the system, instead of adapting these third-party packages to bazel by buildtool
@jinping @liming @yongshun
"""
import os
import core

from pathlib import Path
from core import ErrCode
from core.logging import get_logger
from core.common import generate_template
from core.common import format_namespace_for_template

logger = get_logger('buildtool')
TEMPLATE_COMPONENT = 'component'
TEMPLATE_PLUGIN = 'plugin'


def kebab_to_snake_case(text):
    """convert kebab case to snake case"""
    return text.replace('-', '_')


def kebab_to_pascal_case(text):
    """convert kebab case to pascal case"""
    return ''.join(x.capitalize() for x in text.split('-'))


def kebab_to_camel_case(text):
    """convert kebab case to camel case"""
    camel_text = kebab_to_pascal_case(text)
    return camel_text[0].lower() + camel_text[1:]


def snake_to_kebab_case(text):
    """convert snake case to kebab case"""
    return text.replace('_', '-')


def snake_to_pascal_case(text):
    """convert snake case to pascal case"""
    return ''.join(x.capitalize() for x in text.split('_'))


def snake_to_camel_case(text):
    """convert snake case to camel case"""
    camel_text = snake_to_pascal_case(text)
    return camel_text[0].lower() + camel_text[1:]


def pascal_to_camel_case(text):
    """convert pascal case to camel case"""
    return text[0].lower() + text[1:]


def pascal_to_snake_case(text):
    """convert pascal case to snake case"""
    return ''.join(
        map(lambda x: '_' + x.lower() if x.isupper() else x, text),
    ).lstrip('_')


def pascal_to_kebab_case(text):
    """convert pascal case to kebab case"""
    return ''.join(
        map(lambda x: '-' + x.lower() if x.isupper() else x, text),
    ).lstrip('-')


def camel_to_pascal_case(text):
    """convert camel case to pascal case"""
    return text[0].upper() + text[1:]


def camel_to_snake_case(text):
    """convert camel case to snake case"""
    return ''.join(
        map(lambda x: '_' + x.lower() if x.isupper() else x, text),
    ).lstrip('_')


def camel_to_kebab_case(text):
    """convert camel case to kebab case"""
    return ''.join(
        map(lambda x: '-' + x.lower() if x.isupper() else x, text),
    ).lstrip('-')


def get_action_name():
    """get action name"""
    return 'create'


def get_action_description():
    """get action description"""
    return 'create specific package'


class Action(core.action.Action):
    """create action class"""

    def __init__(self):
        # set default setting
        super().__init__()

    def _check_workspace(self):
        cwd = os.getcwd()
        dirs = cwd.split('/')
        current_dir = '/'
        find_workspace = False
        for d in dirs:
            if d == '':
                continue
            current_dir = current_dir + d + '/'
            workspace_wrapper = Path(current_dir) / 'WORKSPACE'
            if workspace_wrapper.exists():
                if find_workspace:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        ['WORKSPACE nesting detected']
                    )
                find_workspace = True
                self.workspace = current_dir

        if not find_workspace:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ['Can not find WORKSPACE']
            )
        return find_workspace

    def generate_template_vars(self, args):
        """generate template vars"""
        template = args.template
        package_path = f'modules/demo_{template}'
        if args.package_path is not None:
            # override package_path
            package_path = args.package_path

        cwd = os.getcwd()
        if not package_path.startswith('/'):
            package_path = os.path.abspath(
                os.path.join(cwd, package_path))
        if not package_path.startswith(self.workspace):
            ErrCode.send_error(
                ErrCode.ParamErr,
                ['package path must be inside the WORKSPACE']
            )
        package_path = package_path[len(self.workspace):]

        package_name = f'demo-{template}'
        if args.name is not None:
            # override package_name
            package_name = snake_to_kebab_case(pascal_to_kebab_case(args.name))
        else:
            if args.package_path is not None:
                package_name = snake_to_kebab_case(
                    args.package_path.split('/')[-1])

        target_name = kebab_to_snake_case(package_name)

        class_name = kebab_to_pascal_case(package_name)
        if args.class_name is not None:
            # override class_name
            class_name = args.class_name

        base_class_name = f'{class_name}Base'
        if args.base_class_name is not None:
            # override base_class_name
            base_class_name = args.base_class_name

        config_message_name = f'{class_name}Config'
        if args.config_message_name is not None:
            # override config_message_name
            config_message_name = args.config_message_name

        package_type = args.type
        email = args.email
        author = args.author
        description = args.description
        namespaces = args.namespaces

        includes = args.includes
        if includes is None:
            includes = []

        channel_name = f'/apollo/{target_name}'
        if namespaces:
            channel_name = f'/apollo/{"/".join(namespaces)}/{target_name}'

        if args.channel_name is not None:
            # override channel_name
            channel_name = args.channel_name

        channel_message_type = ('apollo'
                                f'{format_namespace_for_template(namespaces)}'
                                f'::{class_name}Msg')
        if args.channel_message_type is not None:
            # override channel_message_type
            channel_message_type = args.channel_message_type

        dependencies = []
        if args.dependencies is not None:
            for dep in args.dependencies:
                dep_attrs = dep.split(':')
                dep_info = {}
                dep_info['package_name'] = dep_attrs[0]
                if len(dep_attrs) > 1:
                    dep_info['import_type'] = dep_attrs[1]
                else:
                    dep_info['import_type'] = 'binary'

                if len(dep_attrs) > 2:
                    dep_info['repo_name'] = dep_attrs[2]
                else:
                    dep_info['repo_name'] = dep_attrs[0]

                if len(dep_attrs) > 3:
                    dep_info['lib_names'] = dep_attrs[3]

                dependencies.append(dep_info)

        build_dependencies = args.build_dependencies
        if build_dependencies is None:
            build_dependencies = []

        template_vars = {
            'package_path': package_path,
            'package_name': package_name,
            'target_name': target_name,
            'class_name': class_name,
            'base_class_name': base_class_name,
            'config_message_name': config_message_name,
            'namespaces': namespaces,
            'includes': includes,
            'dependencies': dependencies,
            'build_dependencies': build_dependencies,
            'channel_name': channel_name,
            'channel_message_type': channel_message_type,
            'package_type': package_type,
            'email': email,
            'author': author,
            'description': description,
        }
        return template_vars

    def execute(self, args, **kwargs):
        """main logic of action"""
        self._check_workspace()

        template = args.template
        template_vars = self.generate_template_vars(args)

        print('template_vars: ', template_vars)

        if template == TEMPLATE_COMPONENT:
            # 1.create proto file
            self.render_component_proto_file(template_vars)
            # 2.create .h file
            self.render_component_header_file(template_vars)
            # 3.create .cc file
            self.render_component_source_file(template_vars)
            # 4.create build file
            self.render_component_build_file(template_vars)
            # 5. create dag file
            self.render_component_dag_file(template_vars)
            # 6. create launch file
            self.render_component_launch_file(template_vars)
            # 7. create cyberfile file
            self.render_component_cyberfile_file(template_vars)
            # 8. create conf file
            self.render_component_conf_file(template_vars)
            logger.info('create component'
                        f' package {template_vars["package_name"]}'
                        f' on {template_vars["package_path"]} success')
        elif template == TEMPLATE_PLUGIN:
            # 1.create .h file
            self.render_plugin_header_file(template_vars)
            # 2. crete .cc file
            self.render_plugin_source_file(template_vars)
            # 3. create build file
            self.render_plugin_build_file(template_vars)
            # 4. create plugins file
            self.render_plugin_plugins_file(template_vars)
            # 5. create cyberfile file
            self.render_plugin_cyberfile_file(template_vars)
            # 6. create conf file
            self.render_plugin_conf_file(template_vars)
            # 7. create proto file
            self.render_plugin_proto_file(template_vars)
            logger.info('create plugin'
                        f' package {template_vars["package_name"]}'
                        f' on {template_vars["package_path"]} success')
        else:
            logger.error('Not currently supported')

    def render_component_cyberfile_file(self, template_vars):
        """
        render_component_cyberfile_file
        """
        package_path = template_vars['package_path']
        component_cyberfile_path = Path(package_path) / 'cyberfile.xml'
        template_path = 'template_component/cyberfile.xml.in'
        self.render_cyberfile(component_cyberfile_path,
                              template_path, **template_vars)

    def render_component_conf_file(self, template_vars):
        """render_component_conf_file"""
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        component_conf_path = Path(package_path) / 'conf/default_conf.pb.txt'
        component_flag_path = Path(package_path) / f'conf/{target_name}.conf'
        conf_template_path = 'template_component/conf/default_conf.pb.txt'
        flag_template_path = 'template_component/conf/flags.conf'

        for template_path, target_path in zip(
                [conf_template_path, flag_template_path],
                [component_conf_path, component_flag_path]):
            if target_path.exists():
                logger.info(f'{target_path} already exist, skip...')
                continue
            try:
                generate_template(template_path,
                                  target_path, **template_vars)
                logger.info(f'{target_path} create success')
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ['write {} failed, detail: {}'.format(
                        str(target_path), str(ex))]
                )

    def render_component_header_file(self, template_vars):
        """render_component_header_file
        * 继承Component类
        * 定义ExampleComponent的Init和Pro函数，Proc函数需要声明输入的类型
        * 通过宏CYBER_REGISTER_COMPONENT注册ExampleComponent类
        """
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        component_h_path = Path(package_path) / f'{target_name}.h'
        if component_h_path.exists():
            logger.info(f'{component_h_path} already exist, skip...')
            return
        template_path = 'template_component/template.h.in'
        try:
            generate_template(template_path,
                              component_h_path, **template_vars)
            logger.info(f'{component_h_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(component_h_path), str(ex))]
            )

    def render_component_source_file(self, template_vars):
        """render_component_source_file
        需要实现头文件中定义的Init和Proc方法
        """
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        component_cc_path = Path(package_path) / f'{target_name}.cc'
        if component_cc_path.exists():
            logger.info(f'{component_cc_path} already exist, skip...')
            return
        template_path = 'template_component/template.cc.in'
        try:
            generate_template(template_path,
                              component_cc_path, **template_vars)
            logger.info(f'{component_cc_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(component_cc_path), str(ex))]
            )

    def render_component_proto_file(self, template_vars):
        """render_component_proto_file
        """
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        component_proto_path = Path(
            package_path) / f'proto/{target_name}.proto'
        if component_proto_path.exists():
            logger.info(f'{component_proto_path} already exist, skip...')
            return
        template_path = 'template_component/proto/template.proto.in'
        try:
            generate_template(template_path,
                              component_proto_path, **template_vars)
            logger.info(f'{component_proto_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(component_proto_path), str(ex))]
            )

    def render_component_build_file(self, template_vars):
        """render_component_build_file"""
        # 1. create proto build
        package_path = template_vars['package_path']
        proto_build_path = Path(package_path) / 'proto/BUILD'
        if proto_build_path.exists():
            logger.info(f'{proto_build_path} already exist, skip...')
        else:
            template_proto_build_path = 'template_component/proto/BUILD.in'
            try:
                generate_template(template_proto_build_path,
                                  proto_build_path, **template_vars)
                logger.info(f'{proto_build_path} create success')
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ['write {} failed, detail: {}'.format(
                        str(proto_build_path), str(ex))]
                )
        # 2. create main build
        main_build_path = Path(package_path) / 'BUILD'
        if main_build_path.exists():
            logger.info(f'{main_build_path} already exist, skip...')
        else:
            template_main_build_path = 'template_component/BUILD.in'
            try:
                generate_template(template_main_build_path,
                                  main_build_path,
                                  **template_vars)
                logger.info(f'{main_build_path} create success')
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ['write {} failed, detail: {}'.format(
                        str(main_build_path), str(ex))]
                )
        return

    def render_component_dag_file(self, template_vars):
        """render_component_dag_file
        * channel名称：指定该component监听的channel
        * library路径：该component编译后产出的动态链接库的保存路径
        * 在Apollo 9.x_dev中，编译后的模块产出的动态链接库可以在/opt/apollo/neo/lib下找到
        * class名称：component对应的类名"""
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        dag_path = Path(package_path) / f'dag/{target_name}.dag'
        if dag_path.exists():
            logger.info(f'{dag_path} already exist, skip...')
            return
        else:
            template_path = 'template_component/dag/template.dag.in'
            try:
                generate_template(template_path,
                                  dag_path,
                                  **template_vars)
                logger.info(f'{dag_path} create success')
                return
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ['write {} failed, detail: {}'.format(
                        str(dag_path), str(ex))]
                )

    def render_component_launch_file(self, template_vars):
        """render_component_launch_file
        * component的名称
        * 该component对应的dag文件的路径
        * 该component运行的进程名"""
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        launch_path = Path(package_path) / f'launch/{target_name}.launch'
        if launch_path.exists():
            logger.info(f'{launch_path} already exist, skip...')
            return
        else:
            template_path = 'template_component/launch/template.launch.in'
            try:
                generate_template(template_path, launch_path, **template_vars)
                logger.info(f'{launch_path} create success')
                return
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ['write {} failed, detail: {}'.format(
                        str(launch_path), str(ex))]
                )

    def render_cyberfile(self, output_path, template_path, **template_vars):
        """
        render_cyberfile
        """
        if output_path.exists():
            logger.info(f'{output_path} already exist, skip...')
            return
        try:
            generate_template(template_path, output_path, **template_vars)
            logger.info(f'{output_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(output_path), str(ex))]
            )

    def render_plugin_header_file(self, template_vars):
        """
        render_plugin_header_file
        """
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        plugin_h_path = Path(package_path) / f'{target_name}.h'
        if plugin_h_path.exists():
            logger.info(f'{plugin_h_path} already exist, skip...')
            return
        template_path = 'template_plugin/template.h.in'
        try:
            generate_template(template_path, plugin_h_path, **template_vars)
            logger.info(f'{plugin_h_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(plugin_h_path), str(ex))]
            )

    def render_plugin_source_file(self, template_vars):
        """render_plugin_source_file
        """
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        plugin_cc_path = Path(package_path) / f'{target_name}.cc'
        if plugin_cc_path.exists():
            logger.info(f'{plugin_cc_path} already exist, skip...')
            return
        template_path = 'template_plugin/template.cc.in'
        try:
            generate_template(template_path, plugin_cc_path, **template_vars)
            logger.info(f'{plugin_cc_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(plugin_cc_path), str(ex))]
            )

    def render_plugin_build_file(self, template_vars):
        """render_plugin_build_file"""
        package_path = template_vars['package_path']

        proto_build_path = Path(package_path) / 'proto/BUILD'
        if proto_build_path.exists():
            logger.info(f'{proto_build_path} already exist, skip...')
        else:
            template_proto_build_path = 'template_plugin/proto/BUILD.in'
            try:
                generate_template(template_proto_build_path,
                                  proto_build_path, **template_vars)
                logger.info(f'{proto_build_path} create success')
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ['write {} failed, detail: {}'.format(
                        str(proto_build_path), str(ex))]
                )

        plugin_main_build_path = Path(package_path) / 'BUILD'
        if plugin_main_build_path.exists():
            logger.info(f'{plugin_main_build_path} already exist, skip...')
            return
        else:
            template_main_build_path = 'template_plugin/BUILD.in'
            try:
                generate_template(template_main_build_path,
                                  plugin_main_build_path,
                                  **template_vars)
                logger.info(f'{plugin_main_build_path} create success')
                return
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ['write {} failed, detail: {}'.format(
                        str(plugin_main_build_path), str(ex))]
                )

    def render_plugin_plugins_file(self, template_vars):
        """render_plugin_plugins_file"""
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        plugin_plugins_path = Path(
            package_path) / f'plugin_{target_name}_description.xml'
        if plugin_plugins_path.exists():
            logger.info(f'{plugin_plugins_path} already exist, skip...')
            return
        template_path = 'template_plugin/plugins.xml.in'
        try:
            generate_template(template_path,
                              plugin_plugins_path, **template_vars)
            logger.info(f'{plugin_plugins_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(plugin_plugins_path), str(ex))]
            )

    def render_plugin_cyberfile_file(self, template_vars):
        """render_plugin_cyberfile_file"""
        package_path = template_vars['package_path']

        plugin_cyberfile_path = Path(package_path) / 'cyberfile.xml'
        template_path = 'template_plugin/cyberfile.xml.in'
        self.render_cyberfile(plugin_cyberfile_path,
                              template_path, **template_vars)

    def render_plugin_conf_file(self, template_vars):
        """render_plugin_conf_file"""
        package_path = template_vars['package_path']
        plugin_conf_path = Path(package_path) / 'conf' / 'default_conf.pb.txt'
        if plugin_conf_path.exists():
            logger.info(f'{plugin_conf_path} already exist, skip...')
            return
        template_path = 'template_plugin/conf/default_conf.pb.txt'
        try:
            generate_template(template_path, plugin_conf_path, **template_vars)
            logger.info(f'{plugin_conf_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(plugin_conf_path), str(ex))]
            )

    def render_plugin_proto_file(self, template_vars):
        """render_plugin_proto_file
        """
        package_path = template_vars['package_path']
        target_name = template_vars['target_name']
        plugin_proto_path = Path(package_path) / f'proto/{target_name}.proto'
        if plugin_proto_path.exists():
            logger.info(f'{plugin_proto_path} already exist, skip...')
            return
        template_path = 'template_plugin/proto/template.proto.in'
        try:
            generate_template(template_path,
                              plugin_proto_path, **template_vars)
            logger.info(f'{plugin_proto_path} create success')
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ['write {} failed, detail: {}'.format(
                    str(plugin_proto_path), str(ex))]
            )

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            'package_path',
            type=str.lstrip,
            help=('specify the path of this package needed to create,'
                  ' default to `modules/demo_<template>`'),
        )

        parser.add_argument(
            '--template',
            type=str.lstrip,
            choices=['component', 'plugin'],
            default='component',
            help='specify the template of this package',
            required=True,
        )

        parser.add_argument(
            '--name',
            type=str.lstrip,
            help='specify the name of this package, default to `demo-<template>`',
            required=False,
        )

        parser.add_argument(
            '--class_name',
            type=str.lstrip,
            help='override default class name',
            required=False,
        )

        parser.add_argument(
            '--type',
            type=str.lstrip,
            choices=['src', 'module', 'binary', 'wrapper'],
            default='module',
            help='specify the type of this package',
            required=False,
        )

        parser.add_argument(
            '--author',
            type=str.lstrip,
            help='specify the author of this package',
            required=False,
            default='Apollo Developer',
        )

        parser.add_argument(
            '--email',
            type=str.lstrip,
            help='specify the contacted email',
            required=False,
            default='sample@sample.com'
        )

        parser.add_argument(
            '--description',
            type=str.lstrip,
            help='specify the description of this package',
            required=False,
            default='This is a demo package',
        )

        parser.add_argument(
            '--config_message_name',
            type=str.lstrip,
            help='specify the proto message name',
            required=False,
        )

        parser.add_argument(
            '--channel_message_type',
            type=str.lstrip,
            help='specify the channel message type',
            required=False,
        )

        parser.add_argument(
            '--channel_name',
            type=str.lstrip,
            help='specify the channel name',
            required=False,
        )

        parser.add_argument(
            '--namespaces',
            nargs='*',
            help='specify the namespace list',
            required=False,
        )

        parser.add_argument(
            '--includes',
            nargs='*',
            help='specify the extra include file list',
            required=False,
        )

        parser.add_argument(
            '--dependencies',
            nargs='*',
            help='specify the extra dependency list',
            required=False,
        )

        parser.add_argument(
            '--build_dependencies',
            nargs='*',
            help='specify the extra build dependency list',
            required=False,
        )

        parser.add_argument(
            '--base_class_name',
            type=str.lstrip,
            help='specify the base class name of plugin',
            required=False,
        )
