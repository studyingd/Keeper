# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('src/password_manager/assets', 'password_manager/assets'), ('src/password_manager/ui/fonts', 'password_manager/ui/fonts'), ('src/password_manager/qml', 'password_manager/qml')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Optional import chains only (openpyxl images/charts, setuptools' distutils
    # shim); the export path writes plain cells and needs none of them.
    excludes=['numpy', 'PIL', 'lxml', 'setuptools', 'lark', 'distutils'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Keeper',
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
    icon=['src/password_manager/assets/keeper.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Keeper',
)
