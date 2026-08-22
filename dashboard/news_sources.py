"""
dashboard/news_sources.py — kuratierte RSS-Quellen fuer die Weltkarte.

Feste Zuordnungstabelle pro Outlet statt Live-Bewertung durch die KI:
schneller, kostenlos (keine Zusatz-API), und konsistent bei jedem Abruf.
Einstufung orientiert sich an gaengigen Medienbias-Uebersichten
(AllSides / Ad Fontes Media) - eine Vereinfachung, keine exakte Wissenschaft.

Jede Quelle: (Anzeigename, RSS-URL, Bias-Label, Sprache des Feeds)
"""


BIAS_COLORS = {
    "links":       "#4da6ff",
    "mitte-links": "#7ad1ff",
    "mitte":       "#9dffb0",
    "mitte-rechts":"#ffd27a",
    "rechts":      "#ff8a4d",
    "staatlich":   "#ff5566",
}


SOURCES: dict[str, list[tuple[str, str, str, str]]] = {
    "de": [
        ("Tagesschau (ARD)",      "https://www.tagesschau.de/index~rss2.xml",              "mitte",        "de"),
        ("taz",                   "https://taz.de/!p4608;rss/",                             "links",        "de"),
        ("Sueddeutsche Zeitung",  "https://rss.sueddeutsche.de/rss/Topthemen",              "mitte-links",  "de"),
        ("Die Welt",              "https://www.welt.de/feeds/latest.rss",                   "mitte-rechts", "de"),
        ("Bild",                  "https://www.bild.de/feed/alles.xml",                     "rechts",       "de"),
    ],
    "us": [
        ("PBS NewsHour",          "https://www.pbs.org/newshour/feeds/rss/headlines",       "mitte",        "en"),
        ("New York Times",        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "mitte-links",  "en"),
        ("CNN",                   "http://rss.cnn.com/rss/cnn_topstories.rss",              "mitte-links",  "en"),
        ("Wall Street Journal",   "https://feeds.a.dj.com/rss/RSSWorldNews.xml",             "mitte-rechts", "en"),
        ("Fox News",              "https://moxie.foxnews.com/google-publisher/latest.xml",  "rechts",       "en"),
    ],
    "ru": [
        ("TASS",                  "https://tass.com/rss/v2.xml",                            "staatlich",    "en"),
        ("Kommersant",            "https://www.kommersant.ru/RSS/news.xml",                 "mitte",        "ru"),
        ("Meduza (Exil-Medium)",  "https://meduza.io/rss/en/all",                            "links",        "en"),
    ],
    "cn": [
        ("CGTN (Staatsmedium)",   "https://www.cgtn.com/subscribe/rss/section/world.xml",    "staatlich",    "en"),
        ("South China Morning Post", "https://www.scmp.com/rss/91/feed",                     "mitte",        "en"),
    ],
}


FEED_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
