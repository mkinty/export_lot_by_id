import subprocess
import platform

if platform.system() == "Windows":
    subprocess.run([
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--windowed",
        "--name",
        "LOT Export",
        "--add-data",
        "lot_export/resources;resources",
        "run.py",
    ])

elif platform.system() == "Darwin":
    subprocess.run([
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--windowed",
        "--name",
        "LOT Export",
        "--add-data",
        "lot_export/resources:resources",
        "run.py",
    ])
