# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    [
        '/apollo/buildtool/bin/mainboard.py',
        '/apollo/buildtool/core/action/__init__.py',
        '/apollo/buildtool/core/action/bootstrap.py',
        '/apollo/buildtool/core/action/build.py',
        '/apollo/buildtool/core/action/clean.py',
        '/apollo/buildtool/core/action/install.py',
        '/apollo/buildtool/core/action/test.py',
        '/apollo/buildtool/core/action/uninstall.py',
        '/apollo/buildtool/core/package_identification/__init__.py',
        '/apollo/buildtool/core/package_identification/identifier.py',
        '/apollo/buildtool/core/task/cmake/__init__.py',
        '/apollo/buildtool/core/task/cmake/build.py',
        '/apollo/buildtool/core/task/bazel/__init__.py',
        '/apollo/buildtool/core/task/bazel/build.py', 
        '/apollo/buildtool/core/__init__.py',
        '/apollo/buildtool/core/boot.py',
        '/apollo/buildtool/core/entry_point.py',
        '/apollo/buildtool/core/logging.py',
        '/apollo/buildtool/core/package_descriptor.py',
        '/apollo/buildtool/core/topological_order.py',
        '/apollo/buildtool/core/common.py',
    ],
    pathex=[],
    binaries=[],
    datas=
    [
        ("data/action/*", "core/action"),
        ("data/templates/*", "data/templates"), 
        ("cmake/*", "cmake"),
        ("bazel/tools/*", "bazel/tools"),
        ("bazel/.bazelrc", "bazel/.bazelrc"),
        ("bazel/apollo.bazelrc", "bazel/apollo.bazelrc"),
        ("bazel/apollo.bzl", "bazel/apollo.bzl"),
        ("bazel/BUILD", "bazel/BUILD"),
        ("demo/*", "demo"),
        ("setup.sh", "./"),
        ("config/*", "config"),
    ],
    hiddenimports=['core.action', 'core.action.build', 'core.action.clean', 'core.action.install', 'core.action.test', 'core.action.uninstall', 'core.action.bootstrap'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='mainboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='mainboard',
)
