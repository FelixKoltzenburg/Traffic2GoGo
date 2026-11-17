from datetime import date

from pendel.ui import seasons


def test_season_borders():
    assert seasons.season_for(date(2026, 3, 19)) == "winter"
    assert seasons.season_for(date(2026, 3, 20)) == "fruehling"
    assert seasons.season_for(date(2026, 6, 21)) == "sommer"
    assert seasons.season_for(date(2026, 9, 23)) == "herbst"
    assert seasons.season_for(date(2026, 11, 17)) == "herbst"
    assert seasons.season_for(date(2026, 12, 21)) == "winter"
    assert seasons.season_for(date(2027, 1, 5)) == "winter"


def test_fixed_choice_and_css():
    s = seasons.current("winter")
    assert s.key == "winter"
    css = seasons.css_vars(s)
    assert css.startswith(":root{") and "--a1:#9fd8ff;" in css


def test_particles_only_in_layer():
    for key, s in seasons.SEASONS.items():
        html = seasons.particles_html(s, count=6)
        assert html.startswith('<div class="season-layer"')
        assert html.count('class="pt ') == 6
