from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TextIO
from urllib.parse import urlparse
from urllib.request import urlopen
import ssl

import certifi


FOOTER_MODAL_URL = (
    "https://cookidoo.thermomix.com/foundation/en-US/partials/footer-modal"
    "?page=%2Ffoundation%2F%7Blang%7D%2Fexplore"
)


@dataclass(frozen=True)
class LanguageOption:
    label: str
    locale: str
    url: str
    default: bool = False


@dataclass(frozen=True)
class SiteOption:
    country: str
    label: str
    languages: tuple[LanguageOption, ...]


@dataclass(frozen=True)
class SelectedSite:
    country: str
    locale: str
    label: str
    url: str | None = None


class _FooterModalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.mode: str | None = None
        self.in_item = False
        self.in_label = False
        self.attrs: dict[str, str | None] = {}
        self.text: list[str] = []
        self.countries: list[tuple[str, str]] = []
        self.languages: list[tuple[str, LanguageOption]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        class_name = attributes.get("class") or ""
        if tag == "core-dropdown-select" and "core-footer__country-select" in class_name:
            self.mode = "country"
            return
        if tag == "core-dropdown-select" and "core-footer__language-select" in class_name:
            self.mode = "language"
            return
        if tag == "li" and self.mode and "core-dropdown-list__item" in class_name:
            self.in_item = True
            self.attrs = attributes
            self.text = []
            return
        if tag == "label" and self.in_item:
            self.in_label = True
            return
        if tag == "input" and self.in_item:
            self.attrs["value"] = attributes.get("value")

    def handle_data(self, data: str) -> None:
        if self.in_item and self.in_label:
            text = " ".join(data.split())
            if text:
                self.text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self.in_item:
            self.in_label = False
            return
        if tag == "li" and self.in_item:
            label = " ".join(self.text).strip()
            if self.mode == "country":
                country = str(self.attrs.get("value") or "").strip().lower()
                if country and label:
                    self.countries.append((country, label))
            elif self.mode == "language":
                country = str(self.attrs.get("data-filter") or "").strip().lower()
                locale = str(self.attrs.get("data-lang") or "").strip()
                url = str(self.attrs.get("value") or "").strip()
                if country and locale and label and url:
                    self.languages.append(
                        (
                            country,
                            LanguageOption(
                                label=label,
                                locale=locale,
                                url=url,
                                default="default-filter-option" in self.attrs,
                            ),
                        )
                    )
            self.in_item = False
            self.attrs = {}
            self.text = []
            return
        if tag == "core-dropdown-select" and self.mode:
            self.mode = None


def parse_footer_modal(html: str) -> list[SiteOption]:
    parser = _FooterModalParser()
    parser.feed(html)
    languages_by_country: dict[str, list[LanguageOption]] = {}
    for country, language in parser.languages:
        languages_by_country.setdefault(country, []).append(language)
    return [
        SiteOption(country=country, label=label, languages=tuple(languages_by_country.get(country, ())))
        for country, label in parser.countries
    ]


def fetch_site_options(url: str = FOOTER_MODAL_URL) -> list[SiteOption]:
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(url, timeout=20, context=context) as response:
        html = response.read().decode("utf-8", "replace")
    return parse_footer_modal(html)


def site_from_url(raw_url: str, sites: list[SiteOption]) -> SelectedSite | None:
    parsed = urlparse(raw_url.strip())
    if not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    locale = _locale_from_path(parsed.path)
    if not locale:
        return None
    for site in sites:
        for language in site.languages:
            language_url = urlparse(language.url)
            if language_url.netloc.lower() == host and language.locale.lower() == locale.lower():
                return SelectedSite(
                    country=site.country,
                    locale=language.locale,
                    label=f"{site.label} - {language.label}",
                    url=language.url,
                )
    country = _country_from_host(host)
    if not country:
        return None
    return SelectedSite(country=country, locale=locale, label=f"{country} - {locale}", url=raw_url)


def choose_site_interactively(
    sites: list[SiteOption],
    input_stream: TextIO,
    output_stream: TextIO,
) -> SelectedSite:
    if not sites:
        raise ValueError("Cookidoo site list is empty")
    print("Which Cookidoo site do you use?", file=output_stream)
    for index, site in enumerate(sites, start=1):
        print(f"{index}. {site.label}", file=output_stream)
    site = _choose_site(sites, input_stream, output_stream)
    if len(site.languages) == 1:
        language = site.languages[0]
    else:
        print(f"Which language do you use for {site.label}?", file=output_stream)
        for index, language_option in enumerate(site.languages, start=1):
            suffix = " [default]" if language_option.default else ""
            print(f"{index}. {language_option.label}{suffix}", file=output_stream)
        language = _choose_language(site, input_stream, output_stream)
    return SelectedSite(
        country=site.country,
        locale=language.locale,
        label=f"{site.label} - {language.label}",
        url=language.url,
    )


def _choose_site(sites: list[SiteOption], input_stream: TextIO, output_stream: TextIO) -> SiteOption:
    while True:
        print("> ", end="", file=output_stream, flush=True)
        value = input_stream.readline().strip()
        if value.isdigit() and 1 <= int(value) <= len(sites):
            return sites[int(value) - 1]
        matches = [site for site in sites if value.lower() in site.label.lower()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            print("Matching sites:", file=output_stream)
            for site in matches:
                print(f"{sites.index(site) + 1}. {site.label}", file=output_stream)
            continue
        print("Choose a number from the list or type part of the country name.", file=output_stream)


def _choose_language(site: SiteOption, input_stream: TextIO, output_stream: TextIO) -> LanguageOption:
    while True:
        print("> ", end="", file=output_stream, flush=True)
        value = input_stream.readline().strip()
        if not value:
            default = next((language for language in site.languages if language.default), None)
            if default:
                return default
        if value.isdigit() and 1 <= int(value) <= len(site.languages):
            return site.languages[int(value) - 1]
        matches = [language for language in site.languages if value.lower() in language.label.lower()]
        if len(matches) == 1:
            return matches[0]
        print("Choose a number from the list or type part of the language name.", file=output_stream)


def _locale_from_path(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    try:
        index = parts.index("foundation")
    except ValueError:
        return None
    if index + 1 >= len(parts):
        return None
    return parts[index + 1]


def _country_from_host(host: str) -> str | None:
    special_hosts = {
        "cookidoo.thermomix.com": "us",
        "cookidoo.co.uk": "gb",
        "cookidoo.com.tr": "tr",
        "cookidoo.thermomix.vn": "vn",
    }
    if host in special_hosts:
        return special_hosts[host]
    prefix = "cookidoo."
    if host.startswith(prefix) and host.count(".") == 1:
        return host.removeprefix(prefix)
    return None
