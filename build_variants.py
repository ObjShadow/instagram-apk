from utils import patch_apk


def build_apk(apk: str, out: str):
    patches = "bins/patches.mpp"
    cli = "bins/morphe-cli.jar"

    common_includes = [
        "Theme",
        "Export all activities"
    ]

    common_excludes = []

    patch_apk(
        cli,
        patches,
        apk,
        includes=common_includes,
        excludes=common_excludes,
        out=out,
    )
