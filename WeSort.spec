# -*- mode: python ; coding: utf-8 -*-


def _prune_qt_collect_items(toc):
    keep_translations = {
        "PyQt6/Qt6/translations/qt_zh_CN.qm",
        "PyQt6/Qt6/translations/qtbase_zh_CN.qm",
        "PyQt6/Qt6/translations/qt_en.qm",
        "PyQt6/Qt6/translations/qtbase_en.qm",
    }
    pruned = []
    for entry in toc:
        dest_name = entry[0].replace("\\", "/")
        if dest_name.startswith("PyQt6/Qt6/translations/") and dest_name not in keep_translations:
            continue
        pruned.append(entry)
    return pruned


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config/rules.json', 'config'),
        ('config/api_config.json', 'config'),
        ('config/api_config.json.template', 'config'),
        ('gui/styles/modern_theme.qss', 'gui/styles'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter'],
    noarchive=False,
    optimize=0,
)
a.datas = _prune_qt_collect_items(a.datas)
a.binaries = _prune_qt_collect_items(a.binaries)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WeSort',
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WeSort',
)
