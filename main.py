import argparse
import os
import re
from subprocess import CalledProcessError

import requests

import apkmirror
import github
from apkmirror import Variant, Version
from build_variants import build_apk
from constants import ARCHITECTURES, PIKO_REPO, REPO
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
            print(f'{architecture} bundle not found')
            continue

        apk_filename = f'big_file_{architecture}.apkm'
        apkmirror.download_apk(download_link, apk_filename, session=session)
        if not os.path.exists(apk_filename):
            panic(f'Failed to download {apk_filename}')
        try:
            build_apk(apk_filename, f"output/instagram-piko-v{latest_version.version}-{architecture}.apk")
            patched_apks.append(f"output/instagram-piko-v{latest_version.version}-{architecture}.apk")
        except CalledProcessError as e:
            print(f"Failed to build output/instagram-piko-v{latest_version.version}-{architecture}.apk:\n{e}")
            continue

    publish_release(
        latest_version.version,
        patched_apks,
        message,
        latest_version.version
    )

    report_to_telegram(tag=latest_version.version)


def main():
    repo_url: str = REPO
    piko_repo: str = PIKO_REPO
    latest_support_version = None

    url = f"https://api.github.com/repos/{piko_repo}/releases"

    response = requests.get(url)
    if response.status_code != 200:
        panic("Failed to fetch github")

    releases = response.json()

    if not releases:
        panic(f"No releases found for {piko_repo}")

    for release in releases:
        match = re.search(r"\*\*Instagram:\*\* Add support for `([0-9.]+)`", release["body"])
        if match:
            version = match.group(1)
            link = f'https://www.apkmirror.com/apk/instagram/instagram-instagram/instagram-{version.replace(".","-")}-release/'
            latest_support_version = Version(
                link=link,
                version=version
            )
            break

    if latest_support_version is None:
        panic(f"No releases with support App version found for {piko_repo}")
        return

    last_build_version: github.GithubRelease | None = github.get_last_build_version(
        repo_url
    )

    if last_build_version is None:
        panic("Failed to fetch the latest build version")
        return

    # Begin stuff
    if last_build_version.tag_name != latest_support_version.version:
        print(f"New version found: {latest_support_version.version}")
    else:
        print("No new version found")
        return

    with FlareSolverrSession() as session:
        process(latest_support_version, session=session)


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
            panic("Version is required.")
        manual(version)
