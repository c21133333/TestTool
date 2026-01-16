# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('requesttool')


a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[('assets', 'assets'), ('D:\\works\\project\\ezTest\\TestTool\\src\\规范手册.docx', 'src'), ('src/dbcase.xlsx', 'src'), ('src/chatgptcase.xlsx', 'src'), ('src/requesttool/app/assets/templates/report.html', 'src/requesttool/app/assets/templates')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EazyTest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\lightning.ico'],
)
