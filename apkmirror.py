from dataclasses import dataclass
from typing import cast
from bs4 import BeautifulSoup, Tag
from utils import download, flaresolverr_request, FlareSolverrSession


@dataclass
class Version:
    version: str
    link: str


@dataclass
class Variant:
    is_bundle: bool
    link: str
    architecture: str


@dataclass
class App:
    name: str
    link: str


class FailedToFindElement(Exception):
    def __init__(self, message=None) -> None:
        self.message = (
            f"Failed to find element{' ' + message if message is not None else ''}"  # noqa: E501
        )
        super().__init__(self.message)


class FailedToFetch(Exception):
    def __init__(self, url=None) -> None:
        self.message = f"Failed to fetch{' ' + url if url is not None else ''}"  # noqa: E501
        super().__init__(self.message)


def get_versions(url: str, session: FlareSolverrSession) -> list[Version]:
    """Get the latest version of the app from the given apkmirror url"""
    response = flaresolverr_request(url, session=session)
    if response.status_code != 200:
        raise FailedToFetch(f"{url}: {response.status_code}")

    bs4 = BeautifulSoup(response.text, "html.parser")
    versions = bs4.find("div", attrs={"class": "listWidget"})

    out: list[Version] = []
    if versions is not None:
        for versionRow in cast(Tag, versions).findChildren("div", recursive=False)[1:]:
            if versionRow is None:
                print(f"{versionRow} is None")
                continue

            version = versionRow.find("span", {"class": "infoSlide-value"})
            if version is None:
                continue

            version = version.string.strip()
            link = f"https://www.apkmirror.com/{versionRow.find('a')['href']}"
            out.append(Version(version=version, link=link))

    return out


def download_apk(variant: Variant, path: str = "big_file.apkm", session: FlareSolverrSession = None):
    """Download apk from the variant link"""
    url = variant.link

    response = flaresolverr_request(url, session=session)

    if response.status_code != 200:
        raise FailedToFetch(url)

    response_body = BeautifulSoup(response.content, "html.parser")

    downloadButton = response_body.find("a", {"class": "downloadButton"})
    if downloadButton is None:
        raise FailedToFindElement("Download button")

    download_page_link = (
        f"https://www.apkmirror.com/{cast(Tag, downloadButton).attrs['href']}"
    )

    download_page = flaresolverr_request(download_page_link, session=session)
    if download_page.status_code != 200:
        raise FailedToFetch(download_page_link)

    download_page_body = BeautifulSoup(download_page.content, "html.parser")

    direct_link = download_page_body.find("a", {"rel": "nofollow"})
    if direct_link is None:
        raise FailedToFindElement("download link")

    direct_link_href = cast(Tag, direct_link).attrs["href"]
    # Remove leading slash to avoid double slashes when combining with base URL
    if direct_link_href.startswith("/"):
        direct_link_href = direct_link_href[1:]
    direct_link_url = f"https://www.apkmirror.com/{direct_link_href}"
    print(f"Direct link: {direct_link_url}")

    # Download the APK file directly using FlareSolverr
    # Note: We use the session to maintain cookies across requests
    download(
        direct_link_url,
        path,
        use_scraper=True,
        headers={"Referer": download_page_link},
        session=session,
    )
    
    # Verify the downloaded file is valid
    if os.path.exists(path):
        file_size = os.path.getsize(path)
        if file_size < 1024:  # Less than 1KB is suspicious
            raise RuntimeError(f"Downloaded file {path} is too small ({file_size} bytes), likely not a valid APK")
        # Check for ZIP magic bytes (APK files are ZIP archives)
        with open(path, "rb") as f:
            magic = f.read(4)
            if magic != b'PK\x03\x04':
                raise RuntimeError(f"Downloaded file {path} does not have valid APK/ZIP magic bytes. Got: {magic.hex()}")
        print(f"Downloaded {path} successfully ({file_size} bytes)")
    else:
        raise RuntimeError(f"Failed to download {path}")


def get_variants(version: Version, session: FlareSolverrSession) -> list[Variant]:
    url = version.link
    variants_page = flaresolverr_request(url, session=session)
    if variants_page is None:
        raise FailedToFetch(url)

    variants_page_body = BeautifulSoup(variants_page.content, "html.parser")

    variants_table = variants_page_body.find("div", {"class": "table"})
    if variants_table is None:
        raise FailedToFindElement("variants table")

    variants_table_rows = cast(Tag, variants_table).findChildren(
        "div", recursive=False
    )[1:]

    variants: list[Variant] = []
    for variant_row in variants_table_rows:
        cells = variant_row.findChildren(
            "div", {"class": "table-cell"}, recursive=False
        )
        if len(cells) == 0:
            print("Could not find cells")

        is_bundle_tag = variant_row.find("span", {"class": "apkm-badge"})
        is_bundle = False
        if is_bundle_tag is None:
            print("Failed to find apk-badge")
        else:
            is_bundle = is_bundle_tag.string.strip() == "BUNDLE"

        architecture: str = cells[1].string
        link_element = variant_row.find("a", {"class": "accent_color"})
        if link_element is None:
            print("Failed to find the link element")

        link: str = f"https://www.apkmirror.com{link_element.attrs['href']}"
        variants.append(
            Variant(is_bundle=is_bundle, link=link, architecture=architecture)
        )

    print(variants)
    return variants
