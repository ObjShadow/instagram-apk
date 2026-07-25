from utils import patch_apk


def build_apk(apk: str, out: str):
    patches = "bins/patches.mpp"
    cli = "bins/morphe-cli.jar"

    common_includes = [
        "Enable app downgrading",
        "Hide FAB",
        "Disable chirp font",
        "Add ability to copy media link",
        "Hide Banner",
        "Hide promote button",
        "Hide Community Notes",
        "Delete from database",
        "Customize Navigation Bar items",
        "Remove premium upsell",
        "Control video auto scroll",
        "Force enable translate",
    ]

    common_excludes = []

    patch_apk(
        cli,
        patches,
        apk,
        includes=["Dynamic color"] + common_includes,
        excludes=common_excludes,
        out=out,
    )
