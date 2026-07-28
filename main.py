import argparse
import os

import apkmirror
import github
from apkmirror import Variant, Version
from build_variants import build_apk
from constants import ARCHITECTURES, REPO
from download_bins import download_morphe_cli, download_release_asset
from utils import FlareSolverrSession, panic, publish_release, report_to_telegram


def get_latest_release(versions: list[Version]) -> Version | None:
    for i in versions:
        if i.version.find("release") >= 0:
            return i


def process(latest_version: Version, session: FlareSolverrSession):
    # Morphe handles .apkm bundles directly; no APKEditor merge is needed.
    download_morphe_cli(include_prereleases=True)

    print("Downloading patches")
    pikoRelease = download_release_asset(
        "crimera/piko", "^patches.*mpp$", "bins", "patches.mpp", include_prereleases=True
    )

    message: str = f"""
Changelogs:
[piko-{pikoRelease["tag_name"]}]({pikoRelease["html_url"]})
"""

    variants: list[Variant] = apkmirror.get_variants(latest_version, session=session)

    patched_apks = []

    for architecture in ARCHITECTURES:
        download_link = next(
            (
                variant
                for variant in variants
                if variant.is_bundle and variant.architecture == architecture
            ),
            None,
        )
        if download_link is None:
            raise Exception(f'{architecture} bundle not found')

        apk_filename = f'big_file_{architecture}.apkm'
        apkmirror.download_apk(download_link, apk_filename, session=session)
        if not os.path.exists(apk_filename):
            panic(f'Failed to download {apk_filename}')

        build_apk(apk_filename, f"instagram-piko-v{latest_version.version}-{architecture}.apk")
        patched_apks.append(f"instagram-piko-v{latest_version.version}-{architecture}.apk")

    publish_release(
        latest_version.version,
        patched_apks,
        message,
        latest_version.version
    )

    report_to_telegram(tag=latest_version.version)


def main():
    # get latest version
    url: str = "https://www.apkmirror.com/apk/instagram/instagram-instagram/"
    repo_url: str = REPO

    with FlareSolverrSession() as session:
        versions = apkmirror.get_versions(url, session=session)

        latest_version = get_latest_release(versions)
        if latest_version is None:
            raise Exception("Could not find the latest version")

        # only continue if it's a release
        if latest_version.version.find("release") < 0:
            panic("Latest version is not a release version")

        last_build_version: github.GithubRelease | None = github.get_last_build_version(
            repo_url
        )

        if last_build_version is None:
            panic("Failed to fetch the latest build version")
            return

        # Begin stuff
        if last_build_version.tag_name != latest_version.version:
            print(f"New version found: {latest_version.version}")
        else:
            print("No new version found")
            return

        process(latest_version, session=session)


def manual(version:str):
    link = f'https://www.apkmirror.com/apk/instagram/instagram-instagram/instagram-{version.replace(".","-")}-release/'
    latest_version = Version(link=link,version=version)

    with FlareSolverrSession() as session:
        process(latest_version, session=session)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Piko APK')
    # 0 = auto; 1 = manual;
    parser.add_argument('--m', action="store", dest='mode', default=0)
    parser.add_argument('--v', action="store", dest='version', default=0)

    args = parser.parse_args()
    mode = args.mode

    if not mode: # auto
        main()
    else: # manual
        version = args.version
        if not version:
            raise Exception("Version is required.")
        manual(version)
