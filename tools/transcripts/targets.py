"""Single source of truth for the Gavin Baker transcript corpus.

Every hardcoded target (video ID, URL, search query, output path) lives here so
there is exactly one place to change. The fetchers in this package import from
this module only -- they contain no embedded URLs or IDs of their own.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

# Repo root = three levels up from this file: tools/transcripts/targets.py
REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPTS_ROOT = REPO_ROOT / "transcripts"

DIR_YOUTUBE = TRANSCRIPTS_ROOT / "youtube"
DIR_COLOSSUS = TRANSCRIPTS_ROOT / "colossus"
DIR_WEB = TRANSCRIPTS_ROOT / "web"
DIR_TEXT = TRANSCRIPTS_ROOT / "text"
DIR_WHISPER = TRANSCRIPTS_ROOT / "whisper"

ALL_DIRS = [DIR_YOUTUBE, DIR_COLOSSUS, DIR_WEB, DIR_TEXT, DIR_WHISPER]

MASTER_MANIFEST = TRANSCRIPTS_ROOT / "_master_manifest.json"

# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30  # seconds


# --------------------------------------------------------------------------
# Typed target records
# --------------------------------------------------------------------------


class YoutubeTarget(TypedDict):
    label: str
    date: str  # YYYY-MM-DD (approximate is fine; used only for filename + manifest)
    source: str
    host: str
    topic: str


class ScrapeTarget(TypedDict):
    url: str
    label: str
    date: str
    source: str
    host: str
    topic: str


class SearchTarget(TypedDict):
    # A text/article target resolved to a concrete URL (via web search).
    label: str
    date: str
    source: str
    host: str
    topic: str
    url: str
    kind: str  # "html" | "pdf"


class RssTarget(TypedDict):
    itunes_id: str
    episode_match: str  # substring to find the right episode in the RSS feed
    label: str
    date: str
    source: str
    host: str
    topic: str


# --------------------------------------------------------------------------
# Step 1 -- YouTube (yt-dlp auto-subs). Keyed by video ID.
# --------------------------------------------------------------------------

YOUTUBE_VIDEOS: dict[str, YoutubeTarget] = {
    # Sohn & Conferences
    "2Ryr95iiYNk": {
        "label": "sohn_ny_2026_tech_investor", "date": "2026-05-12",
        "source": "Sohn NY 2026", "host": "Sohn Conference",
        "topic": "Tech investing fireside",
    },
    "dqYbDqz500c": {
        "label": "sohn_australia_2020_omnichannel", "date": "2020-11-15",
        "source": "Sohn Australia 2020", "host": "Sohn Conference",
        "topic": "Omnichannel / tech",
    },
    "s4QVoht3YsI": {
        "label": "iconn_globalalts_2024_gracias_gurley", "date": "2024-01-15",
        "source": "iConnections Global Alts 2024", "host": "Gracias, Gurley",
        "topic": "Markets panel",
    },
    # All-In Podcast
    "K2xfW3hgxb4": {
        "label": "allin_sec_bitcoin_xai_2024dec", "date": "2024-12-07",
        "source": "All-In Podcast", "host": "Chamath, Jason, Sacks, Friedberg",
        "topic": "SEC, bitcoin, xAI",
    },
    "w8ah_tA0yfg": {
        "label": "allin_dram_bottleneck_2024mid", "date": "2024-06-15",
        "source": "All-In Podcast", "host": "Chamath, Jason, Sacks, Friedberg",
        "topic": "DRAM bottleneck",
    },
    "V0lFjTWx36I": {
        "label": "allin_secondary_markets_2024mid", "date": "2024-06-15",
        "source": "All-In Podcast", "host": "Chamath, Jason, Sacks, Friedberg",
        "topic": "Secondary markets",
    },
    # BG2 Pod
    "Tx9jT2c6e3U": {
        "label": "bg2_spacex_ipo_2026jun", "date": "2026-06-11",
        "source": "BG2 Pod", "host": "Brad Gerstner, Bill Gurley",
        "topic": "SpaceX IPO, AI capex, Cursor",
    },
    # Capital Allocators
    "CFtlGhmAeM0": {
        "label": "capital_allocators_2026_crossover", "date": "2026-03-02",
        "source": "Capital Allocators", "host": "Ted Seides",
        "topic": "Crossover investing",
    },
    # TBPN / Technology Brothers
    "PW5n3ZnEJN0": {
        "label": "tbpn_token_factories_sovereign_ai_2025", "date": "2025-11-15",
        "source": "TBPN", "host": "Technology Brothers",
        "topic": "Token factories, sovereign AI",
    },
    # Heller House / Mission Control
    "_Tua32QoR6w": {
        "label": "heller_house_spacex_cfo_2026", "date": "2026-02-15",
        "source": "Heller House / Mission Control", "host": "Heller House",
        "topic": "SpaceX CFO",
    },
    # Invested by Aleph
    "ugihLT9cFTE": {
        "label": "aleph_semis_globalwarming_2024feb", "date": "2024-02-14",
        "source": "Invested by Aleph", "host": "Michael Eisenberg",
        "topic": "Semiconductors, global warming",
    },
    # ---- Discovered via discover_youtube + operator-confirmed (Gate 2) ----
    # ILTB YouTube mirrors of the two Colossus episodes below (free fallback).
    "Mmj_G9RlW-I": {
        "label": "iltb_watts_wafers_2026may_yt", "date": "2026-05-20",
        "source": "Invest Like the Best (YouTube)", "host": "Patrick O'Shaughnessy",
        "topic": "Watts and wafers",
    },
    "cmUo4841KQw": {
        "label": "iltb_gpus_tpus_ai_economics_2025dec_yt", "date": "2025-12-09",
        "source": "Invest Like the Best (YouTube)", "host": "Patrick O'Shaughnessy",
        "topic": "GPUs, TPUs, economics of AI (Nvidia vs Google)",
    },
    "5ze3ZNvOdRY": {
        "label": "a16z_ai_bubble_david_george_2025oct", "date": "2025-10-30",
        "source": "a16z Podcast", "host": "David George",
        "topic": "Is there an AI bubble?",
    },
    "HxNUAwBWX4I": {
        "label": "allin_2025_predictions_2025jan", "date": "2025-01-04",
        "source": "All-In Podcast", "host": "Chamath, Jason, Sacks, Friedberg",
        "topic": "2025 predictions (bestie guest Gavin Baker)",
    },
    "NlZhF_pULfo": {
        "label": "koyfin_investing_wizards_ep6_2020jul", "date": "2020-07-27",
        "source": "Koyfin Investing Wizards", "host": "Rob Koyfman",
        "topic": "AI tailwind for semiconductors",
    },
    "H_q0w2qSyGY": {
        "label": "twist_ai_platform_shift_2023jun", "date": "2023-06-19",
        "source": "This Week in Startups", "host": "Jason Calacanis",
        "topic": "AI platform shift, Nvidia outlook, extinction risk",
    },
    "kFY30zE9td0": {
        "label": "columbia_sima_investing_2020may", "date": "2020-05-07",
        "source": "Columbia SIMA", "host": "Columbia Student Investment Mgmt Assoc.",
        "topic": "Investing discussion",
    },
    # On The Tape + Thematic Investors -- YouTube mirrors of the audio-only
    # episodes originally slated for Whisper (Step 5); now covered here.
    "mgM-UWPlc3E": {
        "label": "onthetape_fear_market_killer_2022mar", "date": "2022-03-25",
        "source": "On The Tape / RiskReversal", "host": "RiskReversal",
        "topic": "Fear is the market killer",
    },
    "tIxEBEu2Kew": {
        "label": "thematic_investors_scifi_history_2024jul", "date": "2024-07-01",
        "source": "Thematic Investors", "host": "Thematic Investors",
        "topic": "Blending sci-fi, history and literature",
    },
    "RKNTt-HZG2E": {
        "label": "vspartners_global_tech_2021nov", "date": "2021-11-30",
        "source": "VS Partners", "host": "Vanessa Xu (panel)",
        "topic": "Global technology investment: hype, hope, reality",
    },
}

# --------------------------------------------------------------------------
# Discovery searches -- candidate IDs are surfaced for operator review (Gate 2)
# before being added to YOUTUBE_VIDEOS above.
# --------------------------------------------------------------------------

SEARCHES: list[str] = [
    "Gavin Baker Invest Like the Best watts wafers",
    "Gavin Baker Invest Like the Best nvidia google scaling",
    "Gavin Baker Invest Like the Best AI semiconductors robotic",
    "Gavin Baker Invest Like the Best cyclone under surface",
    "Gavin Baker Invest Like the Best bear market 2020",
    "Gavin Baker Invest Like the Best tech consumer growth",
    "Gavin Baker All-In 2025 predictions",
    "Gavin Baker Koyfin Investing Wizards",
    "Gavin Baker Columbia student investment management",
    "Gavin Baker CNBC Sharpe Angle SPACs",
    "Gavin Baker On The Tape RiskReversal",
    "Gavin Baker Thematic Investors podcast",
]

# --------------------------------------------------------------------------
# Step 2 -- Colossus / Invest Like the Best (scrape; YouTube is the fallback)
# --------------------------------------------------------------------------

COLOSSUS_EPISODES: list[ScrapeTarget] = [
    {"url": "https://colossus.com/episode/watts-and-wafers/",
     "label": "iltb_watts_wafers_2026may", "date": "2026-05-20",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "Watts and wafers"},
    {"url": "https://colossus.com/episode/gavin-baker-nvidia-v-google-scaling-laws-and-the-economics-of-ai/",
     "label": "iltb_nvidia_google_scaling_2025dec", "date": "2025-12-09",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "Nvidia vs Google, scaling laws, AI economics"},
    {"url": "https://colossus.com/episode/gavin-baker-ai-semiconductors-and-the-robotic-frontier/",
     "label": "iltb_ai_semis_robotic_2024aug", "date": "2024-08-27",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "AI, semiconductors, robotic frontier"},
    {"url": "https://colossus.com/episode/gavin-baker-the-cyclone-under-the-surface/",
     "label": "iltb_cyclone_surface_2022jan", "date": "2022-01-25",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "The cyclone under the surface"},
    {"url": "https://colossus.com/episode/gavin-baker-investing-through-a-bear-market/",
     "label": "iltb_bear_market_2020apr", "date": "2020-04-02",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "Investing through a bear market"},
    {"url": "https://colossus.com/episode/gavin-baker-tech-and-consumer-growth-investing/",
     "label": "iltb_tech_consumer_2019nov", "date": "2019-11-26",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "Tech and consumer growth investing"},
]

# --------------------------------------------------------------------------
# Step 3 -- Free web writeups (hedgefundalpha). happyscribe dropped (403).
# --------------------------------------------------------------------------

WEB_TARGETS: list[ScrapeTarget] = [
    {"url": "https://hedgefundalpha.com/conferences/2025-sohn-montreal-atreides-gavin-baker/",
     "label": "sohn_montreal_2025_skhynix_writeup", "date": "2025-05-28",
     "source": "HedgeFundAlpha (writeup)", "host": "Sohn Montreal 2025",
     "topic": "SK Hynix / HBM pitch"},
    {"url": "https://hedgefundalpha.com/conferences/inside-mind-a-tech-sohn-2026/",
     "label": "sohn_ny_2026_khaira_writeup", "date": "2026-05-12",
     "source": "HedgeFundAlpha (writeup)", "host": "Sohn NY 2026",
     "topic": "Khaira fireside writeup"},
]

# --------------------------------------------------------------------------
# Step 4 -- Written interviews resolved via web search, then fetched.
# --------------------------------------------------------------------------

# URLs resolved via web search. themarket.ch is partly paywalled -- we save the
# public portion. Graham & Doddsville is a public PDF (Baker interview on p.4+).
TEXT_TARGETS: list[SearchTarget] = [
    {"label": "themarket_there_is_no_playbook", "date": "2022-04-08",
     "source": "The Market (themarket.ch)", "host": "Christoph Gisiger",
     "topic": "There is no playbook; inflation, tech earnings power",
     "url": "https://themarket.ch/interview/there-is-no-playbook-ld.6422",
     "kind": "html"},
    {"label": "themarket_semiconductors_magic", "date": "2020-09-25",
     "source": "The Market (themarket.ch)", "host": "Christoph Gisiger",
     "topic": "Semiconductors are the closest thing to magic",
     "url": "https://themarket.ch/interview/semiconductors-are-the-closest-thing-to-magic-in-the-modern-world-ld.2719",
     "kind": "html"},
    {"label": "themarket_inflation_matters", "date": "2021-09-13",
     "source": "The Market (themarket.ch)", "host": "Christoph Gisiger",
     "topic": "The one thing that matters is inflation",
     "url": "https://themarket.ch/interview/the-one-thing-that-matters-is-inflation-ld.4998",
     "kind": "html"},
    {"label": "graham_doddsville_issue43_2021", "date": "2021-11-01",
     "source": "Graham & Doddsville (Columbia)", "host": "Columbia Business School",
     "topic": "Investor interview (Issue 43, Fall 2021)",
     "url": "https://business.columbia.edu/sites/default/files-efs/imce-uploads/Graham%20&%20Doddsville_Issue%2043_vF.pdf",
     "kind": "pdf"},
]

# --------------------------------------------------------------------------
# Step 6 -- CNBC video (try yt-dlp captions; else article-text fallback)
# --------------------------------------------------------------------------

CNBC_TARGET: ScrapeTarget = {
    "url": "https://www.cnbc.com/video/2021/08/09/the-sharpe-angle-atreides-management-cio-says-one-essential-investment-is-driving-the-spac-market.html",
    "label": "cnbc_sharpe_angle_spacs_2021aug", "date": "2021-08-09",
    "source": "CNBC Sharpe Angle", "host": "CNBC",
    "topic": "Retail investor / SPACs",
}

# --------------------------------------------------------------------------
# Step 5 -- audio-only podcasts (Whisper). NOW REDUNDANT: both episodes were
# found as YouTube mirrors during Gate-2 discovery (onthetape_fear_market_killer
# = mgM-UWPlc3E, thematic_investors_scifi_history = tIxEBEu2Kew) and are covered
# by Step 1. fetch_audio_whisper.py remains as general-purpose tooling for any
# future audio-only appearance that lacks a YouTube mirror.
# --------------------------------------------------------------------------

RSS_TARGETS: list[RssTarget] = [
    {"itunes_id": "1545205930", "episode_match": "Fear is the Market Killer",
     "label": "onthetape_fear_market_killer", "date": "2022-03-25",
     "source": "On The Tape / RiskReversal", "host": "RiskReversal",
     "topic": "Fear is the market killer"},
    {"itunes_id": "1706531701", "episode_match": "Gavin Baker",
     "label": "thematic_investors_scifi_history", "date": "2024-06-15",
     "source": "Thematic Investors", "host": "Thematic Investors",
     "topic": "Blending sci-fi, history and literature"},
]
