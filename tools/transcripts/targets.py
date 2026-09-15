"""Single source of truth for the Gavin Baker transcript corpus.

Every hardcoded target (video ID, URL, search query, output path) lives here so
there is exactly one place to change. The fetchers in this package import from
this module only -- they contain no embedded URLs or IDs of their own.
"""

from __future__ import annotations

from pathlib import Path
from typing import NotRequired, TypedDict

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
    subject_role: NotRequired[str]  # "guest" | "panelist" | "secondary" | "unknown"; set by fix_participants


class ScrapeTarget(TypedDict):
    url: str
    label: str
    date: str
    source: str
    host: str
    topic: str
    subject_role: NotRequired[str]  # "guest" | "panelist" | "secondary" | "unknown"; set by fix_participants


class SearchTarget(TypedDict):
    # A text/article target resolved to a concrete URL (via web search).
    label: str
    date: str
    source: str
    host: str
    topic: str
    url: str
    kind: str  # "html" | "pdf"
    subject_role: NotRequired[str]  # "guest" | "panelist" | "secondary" | "unknown"; set by fix_participants


class RssTarget(TypedDict):
    itunes_id: str
    episode_match: str  # substring to find the right episode in the RSS feed
    label: str
    date: str
    source: str
    host: str
    topic: str
    subject_role: NotRequired[str]  # "guest" | "panelist" | "secondary" | "unknown"; set by fix_participants


# --------------------------------------------------------------------------
# Step 1 -- YouTube (yt-dlp auto-subs). Keyed by video ID.
# --------------------------------------------------------------------------

# The person whose views this corpus tracks. Passed into the extraction prompt so
# the prompt itself is not investor-specific (it refers to "the subject").
SUBJECT_DESCRIPTION: str = (
    "Gavin Baker, CIO of Atreides Management (~$7B crossover fund focused on "
    "technology); previously ran Fidelity's $17B OTC fund for 8 years"
)

YOUTUBE_VIDEOS: dict[str, YoutubeTarget] = {
    # Sohn & Conferences
    "2Ryr95iiYNk": {
        "label": "sohn_ny_2026_tech_investor", "date": "2026-05-12",
        "source": "Sohn NY 2026", "host": "Jas (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Tech investing fireside",
    },
    "dqYbDqz500c": {
        "label": "sohn_australia_2020_omnichannel", "date": "2020-11-15",
        "source": "Sohn Australia 2020", "host": "unnamed (Gavin Baker unknown)", "subject_role": "unknown",
        "topic": "Omnichannel / tech",
    },
    "s4QVoht3YsI": {
        "label": "iconn_globalalts_2026_gracias_baker", "date": "2026-02-24",
        "source": "iConnections Global Alts 2026", "host": "Antonio Gracias, Ron (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "AI, Tesla, defense, energy — what comes next",
    },
    # All-In Podcast
    "K2xfW3hgxb4": {
        "label": "allin_sec_bitcoin_xai_2024dec", "date": "2024-12-07",
        "source": "All-In Podcast", "host": "Jason Calacanis, David Friedberg, Joe Lonsdale (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "SEC, bitcoin, xAI",
    },
    "w8ah_tA0yfg": {
        "label": "allin_ai_memory_micron_2026jun", "date": "2026-06-27",
        "source": "All-In Podcast", "host": "Travis Kalanick, Chamath, Jason, Sacks (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "E278: AI memory crunch, Micron blowout, NYC socialists, SpaceX float (w/ Kalanick)",
    },
    "V0lFjTWx36I": {
        "label": "allin_liquidity_secondaries_2026jun", "date": "2026-06-07",
        "source": "All-In Podcast", "host": "Kelly Rodriguez, Brad Gerstner (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "Liquidity Summit: secondary markets eating the IPO",
    },
    # Added 2026-07-22 (6-new-appearances task). Baker is a guest/bestie among
    # multiple All-In speakers — extraction must attribute only Baker's contributions.
    "WvTTDxMuAis": {
        "label": "allin_e125_spacex_starship_2023apr", "date": "2023-04-21",
        "source": "All-In Podcast", "host": "David Sacks, David Friedberg, Chamath Palihapitiya, Jason Calacanis, Antonio Gracias (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "E125: SpaceX Starship launch, Fox News settlement, AI/Reddit (with Antonio Gracias)",
    },
    "wu-p5xrJ8-E": {
        "label": "allin_tariffs_agi_prize_2025jul", "date": "2025-07-17",
        "source": "All-In Podcast", "host": "Jason, Dave, Chamath, Friedberg (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "Markets: pricing in tariffs, Trump vs Powell, the $10 trillion AGI prize",
    },
    # BG2 Pod
    "Tx9jT2c6e3U": {
        "label": "bg2_spacex_ipo_2026jun", "date": "2026-06-11",
        "source": "BG2 Pod", "host": "Andrew Fox, Clark Tang, Brad Gerstner (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "SpaceX IPO, AI capex, Cursor",
    },
    # Capital Allocators
    "CFtlGhmAeM0": {
        "label": "capital_allocators_2026_crossover", "date": "2026-03-02",
        "source": "Capital Allocators", "host": "Ted Seides (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Crossover investing",
    },
    # TBPN / Technology Brothers
    "PW5n3ZnEJN0": {
        "label": "tbpn_spacex_sovereign_ai_2026jun", "date": "2026-06-15",
        "source": "TBPN", "host": "Foxy (Gavin Baker guest)", "subject_role": "guest",
        "topic": "SpaceX IPO, token path, sovereign AI won't reach frontier",
    },
    # Heller House / Mission Control.
    # NOTE (2026-07-22): a prior file (2026-02-15_heller_house_spacex_cfo_2026) was
    # REMOVED 2026-07-08 as a red herring (reporter profiling SpaceX CFO Bret Johnsen;
    # see analysis/_removed_files_log.md). Re-added per operator instruction, reframed
    # as Baker-as-INTERVIEWER of the CFO — a legitimate source of Baker's own views via
    # his questions/commentary. Extraction MUST attribute only Baker (not Johnsen);
    # pending operator sign-off at the basket-curation gate. See
    # analysis/six_new_appearances_implementation_notes.md (SD-6NEW-1).
    # ---- REMOVED 2026-09-08: "jOgbqt04eUk" Heller House 2026-06-08.
    # BAKER IS THE INTERVIEWER, NOT THE SUBJECT. Title: "Gavin Baker interviews
    # SpaceX CFO Bret Johnsen at Mission Control". Full-transcript measurement:
    # 97 turns, 6 question-shaped (367 words) vs 91 answer-shaped (8,297 words)
    # -> 96% of words are Johnsen's; his questions span turn 2..83 of 96, so he
    # is interviewing THROUGHOUT, not just opening. Corporate "we/our/us" runs
    # 228 in answer turns vs 10 in question turns. The speaker-aware re-extract
    # independently assigned its lead thesis to "Bret Johnsen".
    # A transcript that is 96% someone else's views is a Baker byline, not a
    # Baker appearance. Removed rather than re-extracted, per operator.
    # COST: 4 of 11 theses were genuinely Baker's framing claims (TMUS/T/VZ,
    # NVDA) and go with it. Restore with `git checkout` if disputed. ----
    # Invested by Aleph
    "ugihLT9cFTE": {
        "label": "aleph_semis_globalwarming_2025oct", "date": "2025-10-22",
        "source": "Invested by Aleph", "host": "Michael Eisenberg (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Semiconductors, China/Taiwan fabs, global warming (China's Not Getting Taiwan's Fabs)",
    },
    # ---- Discovered via discover_youtube + operator-confirmed (Gate 2) ----
    # ILTB YouTube mirrors of the two Colossus episodes below (free fallback).
    "Mmj_G9RlW-I": {
        "label": "iltb_watts_wafers_2026may_yt", "date": "2026-05-20",
        "source": "Invest Like the Best (YouTube)", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Watts and wafers",
    },
    "cmUo4841KQw": {
        "label": "iltb_gpus_tpus_ai_economics_2025dec_yt", "date": "2025-12-09",
        "source": "Invest Like the Best (YouTube)", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
        "topic": "GPUs, TPUs, economics of AI (Nvidia vs Google)",
    },
    "5ze3ZNvOdRY": {
        "label": "a16z_ai_bubble_david_george_2025oct", "date": "2025-10-30",
        "source": "a16z Podcast", "host": "David George (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Is there an AI bubble?",
    },
    "HxNUAwBWX4I": {
        "label": "allin_2025_predictions_2025jan", "date": "2025-01-04",
        "source": "All-In Podcast", "host": "Jason Calacanis, Chamath, David Sacks, David Friedberg (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "2025 predictions (bestie guest Gavin Baker)",
    },
    "NlZhF_pULfo": {
        "label": "koyfin_investing_wizards_ep6_2020jul", "date": "2020-07-27",
        "source": "Koyfin Investing Wizards", "host": "Rob Koyfman (Gavin Baker guest)", "subject_role": "guest",
        "topic": "AI tailwind for semiconductors",
    },
    "H_q0w2qSyGY": {
        "label": "twist_ai_platform_shift_2023jun", "date": "2023-06-19",
        "source": "This Week in Startups", "host": "Jason Calacanis (Gavin Baker guest)", "subject_role": "guest",
        "topic": "AI platform shift, Nvidia outlook, extinction risk",
    },
    "kFY30zE9td0": {
        "label": "columbia_sima_investing_2020may", "date": "2020-05-07",
        "source": "Columbia SIMA", "host": "David, Danielle, Ben (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "Investing discussion",
    },
    # On The Tape + Thematic Investors -- YouTube mirrors of the audio-only
    # episodes originally slated for Whisper (Step 5); now covered here.
    "mgM-UWPlc3E": {
        "label": "onthetape_fear_market_killer_2022mar", "date": "2022-03-25",
        "source": "On The Tape / RiskReversal", "host": "Dan Nathan, Danny Moses, Guy (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "Fear is the market killer",
    },
    "tIxEBEu2Kew": {
        "label": "thematic_investors_scifi_history_2024jul", "date": "2024-07-01",
        "source": "Thematic Investors", "host": "Kieran Cavana (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Blending sci-fi, history and literature",
    },
    "RKNTt-HZG2E": {
        "label": "vspartners_global_tech_2021nov", "date": "2021-11-30",
        "source": "VS Partners", "host": "Vanessa Xu (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Global technology investment: hype, hope, reality",
    },
    # ---- Gap-fill 2026-07-09: missing appearances from corpus_audit.md ----
    # (upload dates verified via yt-dlp; conference dates are event dates.)
    # ---- REMOVED 2026-09-04: "yosv2UDCm9M" Limitless (Bankless) 2026-05-28.
    # BAKER IS NOT ON THIS EPISODE. Actual title "What The Best AI Investors Are
    # Buying Right Now"; it opens "Gavin Baker is one of the most prolific AI
    # investors that almost no one has heard of. He spent the last 20 years..."
    # — two Bankless hosts discussing him in the THIRD PERSON (it even garbles
    # Atreides as "a Trade Desk Management"). The attribution audit returned
    # 14/14 theses "other" with 19/19 named tickers attributed to the hosts.
    # Derivative commentary, not an appearance: removed rather than re-extracted.
    # Restore with `git checkout` if this is ever disputed. ----
    "UJ3pNPFwAeM": {
        "label": "iconn_globalalts_2025_future_of_ai", "date": "2025-01-28",
        "source": "iConnections Global Alts 2025", "host": "Antonio Gracias (Gavin Baker guest)", "subject_role": "guest",
        "topic": "The Future of AI",
    },
    "Iazo7g40VbQ": {
        "label": "allin_e221_coreweave_ipo_2025mar", "date": "2025-03-29",
        "source": "All-In Podcast", "host": "Jason, Friedberg (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "E221: AI cold war, Signalgate, CoreWeave IPO, tariffs",
    },
    "HGbA6ze0_3M": {
        "label": "allin_e274_spacex_2t_nvidia_2026may", "date": "2026-05-22",
        "source": "All-In Podcast", "host": "Chamath, Jason, Friedberg (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "E274: SpaceX $2T case, Nvidia shock selloff",
    },
    "4YXMZhsVClI": {
        "label": "twist_e1990_liquidity_gracias_2024aug", "date": "2024-08-07",
        "source": "This Week in Startups", "host": "Alex, Antonio Gracias, Jason Calacanis (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "E1990: Liquidity Summit fireside (with Antonio Gracias)",
    },
    "MWE5LsO62wA": {
        "label": "iconn_globalalts_2024_gracias_baker_gurley", "date": "2024-01-30",
        "source": "iConnections Global Alts 2024", "host": "Bill Gurley, Antonio Gracias (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "Industry titans panel: AI, growth/crossover investing",
    },
    "FmLGYLQ6DFY": {
        "label": "generating_alpha_ep56_2026jul", "date": "2026-07-08",
        "source": "Generating Alpha", "host": "Amir Fischer (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Ep.56: career arc, semis, NVDA/Tesla, AI infra cycles",
    },
    "esWMssGq-G0": {
        "label": "fii_gigafirm_trillion_dollar_2024feb", "date": "2024-02-23",
        "source": "FII Institute", "host": "Antonio (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Rise of the Gigafirm: next trillion-dollar tech company (panel)",
    },
    # ---- Added 2026-08-10 (2-new-appearances task; from fomo-fund-monitor
    # YouTube triage). Both are genuine solo Baker appearances (interviewee /
    # featured speaker) — full attribution to Baker, no co-guest split. ----
    "NGsi2PC4y68": {
        "label": "iltb_markets_pricing_ai_wrong_2026aug", "date": "2026-08-04",
        "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
        "topic": "Why the markets are pricing AI wrong: July 2026 AI/semis selloff ('2022 in a month'), private inference cloud, old-GPU repricing, ~$700B Blackwell/Rubin credit gap",
    },
    "MmNWwIYFBeI": {
        "label": "aria_networks_mfu_ai_factories_2026apr", "date": "2026-04-16",
        "source": "Aria Networks", "host": "Mansour (Gavin Baker guest)", "subject_role": "guest",
        "topic": "MFU (Model Flop Utilization) as the defining AI-factory metric; lowest-cost token producer wins → deploy highest-performance infra, not cheapest",
    },
    # ---- Added 2026-08-15 (full-sweep task). Baker is a GUEST/bestie among the
    # All-In hosts ("Gavin Baker joins the show" @0:00) — extraction must attribute
    # only Baker's contributions, not the hosts'. ----
    "kVzYGVJ8zUk": {
        "label": "allin_anthropic_ipo_nvidia_500b_2026aug", "date": "2026-08-14",
        "source": "All-In Podcast", "host": "David Sacks, Jason Calacanis (Gavin Baker panelist)", "subject_role": "panelist",
        "topic": "Anthropic $2T IPO, Zuck's AI manifesto, Nvidia's $500B AI financing, Grok 4.6 / SpaceX AI strategy",
    },
    # ---- Added 2026-09-04. Surfaced by the fomo-fund-monitor podcast_rss
    # monitor (a16z feed, 2026-08-31) and confirmed absent from the corpus.
    # YouTube mirror on the a16z channel (~1h14m), so no Whisper needed — unlike
    # the 2026-07-14 a16z episode, which had none and went via RSS_TARGETS.
    # SOLO Baker guest (David George interviews) -> FULL attribution, in contrast
    # to the All-In entry above where Baker is one voice among the hosts. ----
    "FGC4ofTcg2k": {
        "label": "a16z_demand_outrunning_compute_2026aug", "date": "2026-08-31",
        "source": "a16z Podcast", "host": "David George (Gavin Baker guest)", "subject_role": "guest",
        "topic": "AI demand outrunning compute supply; frontier-lab revenue is self-determined, reinvestment math, not necessarily winner-take-all",
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
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
     "topic": "Watts and wafers"},
    {"url": "https://colossus.com/episode/gavin-baker-nvidia-v-google-scaling-laws-and-the-economics-of-ai/",
     "label": "iltb_nvidia_google_scaling_2025dec", "date": "2025-12-09",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
     "topic": "Nvidia vs Google, scaling laws, AI economics"},
    {"url": "https://colossus.com/episode/gavin-baker-ai-semiconductors-and-the-robotic-frontier/",
     "label": "iltb_ai_semis_robotic_2024aug", "date": "2024-08-27",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
     "topic": "AI, semiconductors, robotic frontier"},
    {"url": "https://colossus.com/episode/gavin-baker-the-cyclone-under-the-surface/",
     "label": "iltb_cyclone_surface_2022jan", "date": "2022-01-25",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
     "topic": "The cyclone under the surface"},
    {"url": "https://colossus.com/episode/gavin-baker-investing-through-a-bear-market/",
     "label": "iltb_bear_market_2020apr", "date": "2020-04-02",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
     "topic": "Investing through a bear market"},
    {"url": "https://colossus.com/episode/gavin-baker-tech-and-consumer-growth-investing/",
     "label": "iltb_tech_consumer_2019nov", "date": "2019-11-26",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy (Gavin Baker guest)", "subject_role": "guest",
     "topic": "Tech and consumer growth investing"},
]

# --------------------------------------------------------------------------
# Step 3 -- Free web writeups (hedgefundalpha). happyscribe dropped (403).
# --------------------------------------------------------------------------

WEB_TARGETS: list[ScrapeTarget] = [
    {"url": "https://hedgefundalpha.com/conferences/2025-sohn-montreal-atreides-gavin-baker/",
     "label": "sohn_montreal_2025_skhynix_writeup", "subject_role": "secondary", "date": "2025-05-28",
     "source": "HedgeFundAlpha (writeup)", "host": "Sohn Montreal 2025",
     "topic": "SK Hynix / HBM pitch"},
    {"url": "https://hedgefundalpha.com/conferences/inside-mind-a-tech-sohn-2026/",
     "label": "sohn_ny_2026_khaira_writeup", "subject_role": "secondary", "date": "2026-05-12",
     "source": "HedgeFundAlpha (writeup)", "host": "Sohn NY 2026",
     "topic": "Khaira fireside writeup"},
]

# --------------------------------------------------------------------------
# Step 4 -- Written interviews resolved via web search, then fetched.
# --------------------------------------------------------------------------

# URLs resolved via web search. themarket.ch is partly paywalled -- we save the
# public portion. Graham & Doddsville is a public PDF (Baker interview on p.4+).
TEXT_TARGETS: list[SearchTarget] = [
    {"label": "themarket_there_is_no_playbook", "subject_role": "guest", "date": "2022-04-08",
     "source": "The Market (themarket.ch)", "host": "Christoph Gisiger",
     "topic": "There is no playbook; inflation, tech earnings power",
     "url": "https://themarket.ch/interview/there-is-no-playbook-ld.6422",
     "kind": "html"},
    {"label": "themarket_semiconductors_magic", "subject_role": "guest", "date": "2020-09-25",
     "source": "The Market (themarket.ch)", "host": "Christoph Gisiger",
     "topic": "Semiconductors are the closest thing to magic",
     "url": "https://themarket.ch/interview/semiconductors-are-the-closest-thing-to-magic-in-the-modern-world-ld.2719",
     "kind": "html"},
    {"label": "themarket_inflation_matters", "subject_role": "guest", "date": "2021-09-13",
     "source": "The Market (themarket.ch)", "host": "Christoph Gisiger",
     "topic": "The one thing that matters is inflation",
     "url": "https://themarket.ch/interview/the-one-thing-that-matters-is-inflation-ld.4998",
     "kind": "html"},
    {"label": "graham_doddsville_issue43_2021", "subject_role": "guest", "date": "2021-11-01",
     "source": "Graham & Doddsville (Columbia)", "host": "Columbia Business School",
     "topic": "Investor interview (Issue 43, Fall 2021)",
     "url": "https://business.columbia.edu/sites/default/files-efs/imce-uploads/Graham%20&%20Doddsville_Issue%2043_vF.pdf",
     "kind": "pdf"},
]

# --------------------------------------------------------------------------
# Step 6 -- CNBC video (try yt-dlp captions; else article-text fallback)
# --------------------------------------------------------------------------

# Appearances acquired OUTSIDE the five target lists above (two Whisper'd CNBC
# segments and a Sohn write-up). They live in the master manifest but had no
# targets.py record, so metadata lookups keyed on the target lists returned an
# empty participants field for them — the condition that produces bad
# attribution. Registered here so every appearance in the corpus has host + role
# in config rather than inferred at read time. Added 2026-09-08.
SUPPLEMENTARY_METADATA: dict[str, dict[str, str]] = {
    "sohn_australia_2021_coinbase": {
        "host": "Sohn Hearts & Minds Australia 2021",
        # Third-party coverage of the pick, not a transcript of Baker speaking.
        "subject_role": "secondary",
    },
    "cnbc_squawk_spacex_debut_2026jun": {
        "host": "CNBC (Quintanilla/Faber/Eisen)",
        "subject_role": "panelist",  # three anchors, all substantive
    },
    "cnbc_spacex_drawdown_2026jul": {
        "host": "CNBC",
        "subject_role": "guest",
    },
}

CNBC_TARGET: ScrapeTarget = {
    "url": "https://www.cnbc.com/video/2021/08/09/the-sharpe-angle-atreides-management-cio-says-one-essential-investment-is-driving-the-spac-market.html",
    "label": "cnbc_sharpe_angle_spacs_2021aug", "subject_role": "guest", "date": "2021-08-09",
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

# On The Tape + Thematic Investors were covered via YouTube mirrors (Step 1), so
# they are NOT listed here (listing them would trigger redundant re-transcription).
# The 4 Invest Like the Best episodes below are podcast-audio-only (no YouTube
# mirror on the ILTB channel for pre-2025 episodes) -> Whisper. iTunes id
# 1154105909 = "Invest Like the Best" (feed resolves to megaphone). Added
# 2026-07-09 during the corpus gap-fill (corpus_audit.md).
RSS_TARGETS: list[RssTarget] = [
    {"itunes_id": "1154105909", "episode_match": "Robotic Frontier",
     "label": "iltb_ai_semis_robotic_2024aug", "subject_role": "guest", "date": "2024-08-27",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "AI, semiconductors, and the robotic frontier (EP.385)"},
    {"itunes_id": "1154105909", "episode_match": "Cyclone Under the Surface",
     "label": "iltb_cyclone_surface_2022jan", "subject_role": "guest", "date": "2022-01-25",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "The cyclone under the surface (EP.260)"},
    {"itunes_id": "1154105909", "episode_match": "Investing Through a Bear Market",
     "label": "iltb_bear_market_2020apr", "subject_role": "guest", "date": "2020-04-02",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "Investing through a bear market (EP.167)"},
    {"itunes_id": "1154105909", "episode_match": "Tech and Consumer Growth",
     "label": "iltb_tech_consumer_2019nov", "subject_role": "guest", "date": "2019-11-26",
     "source": "Invest Like the Best", "host": "Patrick O'Shaughnessy",
     "topic": "Tech and consumer growth investing (EP.149)"},
    # ---- Added 2026-08-15 (full-sweep task). a16z is AUDIO-ONLY (no YouTube
    # mirror confirmed) -> Whisper. iTunes id 842818711 = "The a16z Show"
    # (feed simplecast JGE3yC0V). Solo Baker guest -> full attribution. ----
    {"itunes_id": "842818711", "episode_match": "Is AI a Bubble",
     "label": "a16z_ai_bubble_datacenters_2026jul", "date": "2026-07-14",
     "source": "a16z Podcast", "host": "David George (Gavin Baker guest)", "subject_role": "guest",
     "topic": "Is AI a bubble? Data centers, GPUs, and the AI economy (Gavin Baker)"},
]
