# PyInstaller spec for redfish-test.exe (build on Windows)
# Usage: pyinstaller redfish_test_tool.spec

a = Analysis(
    ['redfish_test_tool/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('redfish_test_tool/reporting/templates',
         'redfish_test_tool/reporting/templates'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='redfish-test',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
