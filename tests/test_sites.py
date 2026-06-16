from cookidoo_mcp.sites import parse_footer_modal, site_from_url


FOOTER_MODAL = """
<core-dropdown-select class="core-footer__country-select">
  <ul class="core-dropdown-list">
    <li class="core-dropdown-list__item"><label>Switzerland<input value="ch"></label></li>
    <li class="core-dropdown-list__item"><label>United States<input value="us"></label></li>
  </ul>
</core-dropdown-select>
<core-dropdown-select class="core-footer__language-select">
  <ul class="core-dropdown-list">
    <li class="core-dropdown-list__item" data-filter="ch" data-lang="de-CH" default-filter-option="true">
      <label>German<input value="https://cookidoo.ch/foundation/de-CH/explore"></label>
    </li>
    <li class="core-dropdown-list__item" data-filter="ch" data-lang="fr-CH">
      <label>French<input value="https://cookidoo.ch/foundation/fr-CH/explore"></label>
    </li>
    <li class="core-dropdown-list__item" data-filter="us" data-lang="en-US" default-filter-option="true">
      <label>English<input value="https://cookidoo.thermomix.com/foundation/en-US/explore"></label>
    </li>
  </ul>
</core-dropdown-select>
"""


def test_parse_footer_modal_groups_languages_by_country():
    sites = parse_footer_modal(FOOTER_MODAL)

    assert [site.label for site in sites] == ["Switzerland", "United States"]
    assert sites[0].country == "ch"
    assert [(item.label, item.locale, item.default) for item in sites[0].languages] == [
        ("German", "de-CH", True),
        ("French", "fr-CH", False),
    ]


def test_site_from_url_matches_known_cookidoo_site():
    sites = parse_footer_modal(FOOTER_MODAL)

    selected = site_from_url("https://cookidoo.ch/foundation/fr-CH/explore", sites)

    assert selected is not None
    assert selected.country == "ch"
    assert selected.locale == "fr-CH"
    assert selected.label == "Switzerland - French"
