"""
Share System for Popularoo — Phase 1
- Dynamic image generation (Rally Cry visuals)
- Short link system (popularoo.com/r/[7-char])
- Server-rendered public pages with OG meta tags
- Pre-written share messages per platform
"""

import os
import random
import string
from io import BytesIO
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from PIL import Image, ImageDraw, ImageFont
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from bson import ObjectId

# ---- Constants ----
BRAND_GREEN = "#009B4D"
BRAND_DARK = "#0F2F22"
BRAND_GOLD = "#FFD700"
BRAND_LIGHT = "#EAEAEA"
BRAND_CARD = "#1C3A2C"
BRAND_BORDER = "#2E6148"

SITE_URL = "https://popularoo.com"
APP_STORE_URL = "https://apps.apple.com/app/popularoo/id6743206968"
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.popularoo.app"

share_router = APIRouter(prefix="/api/share", tags=["Share System"])


# ---- Models ----
class ShareData(BaseModel):
    short_url: str
    share_image_square: str
    share_image_vertical: str
    messages: Dict[str, str]


# ---- Short Link System ----
def generate_short_id(length=7):
    """Generate a 7-char alphanumeric short ID"""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=length))


async def create_short_link(db, target_type: str, target_id: str) -> str:
    """Create or retrieve a short link for a target (rally_cry or user)"""
    # Check if one already exists
    existing = await db.short_links.find_one({
        "target_type": target_type,
        "target_id": target_id,
    })
    if existing:
        return existing["short_id"]

    # Generate new unique short_id
    for _ in range(10):
        short_id = generate_short_id()
        conflict = await db.short_links.find_one({"short_id": short_id})
        if not conflict:
            break
    else:
        short_id = generate_short_id(9)  # Fallback to longer ID

    await db.short_links.insert_one({
        "short_id": short_id,
        "target_type": target_type,  # "rally_cry" or "user"
        "target_id": target_id,
        "created_at": datetime.now(timezone.utc),
        "clicks": 0,
    })
    return short_id


async def resolve_short_link(db, short_id: str) -> Optional[Dict]:
    """Resolve a short link to its target"""
    doc = await db.short_links.find_one({"short_id": short_id})
    if doc:
        await db.short_links.update_one(
            {"_id": doc["_id"]},
            {"$inc": {"clicks": 1}}
        )
    return doc


# ---- Image Generation ----
FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
BRAND_RED = "#E04F5F"


def get_font(size: int, bold: bool = True):
    """Get Oswald font (condensed, impact-like), fallback to system fonts"""
    if bold:
        candidates = [
            os.path.join(FONTS_DIR, "Oswald-Bold.ttf"),
            "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
    else:
        candidates = [
            os.path.join(FONTS_DIR, "Oswald-Regular.ttf"),
            "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _truncate_name(draw, name: str, font, max_width: int) -> str:
    """Truncate name with ellipsis if it exceeds max_width"""
    text = name.upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    if (bbox[2] - bbox[0]) <= max_width:
        return text
    while len(text) > 3:
        text = text[:-1]
        bbox = draw.textbbox((0, 0), text + "…", font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return text + "…"
    return text


def _format_score(score: int) -> str:
    """Format score with thousands separators"""
    if score >= 1000000:
        return f"{score / 1000000:.1f}M"
    elif score >= 10000:
        return f"{score / 1000:.1f}K"
    return f"{score:,}".replace(",", " ")


def generate_rally_cry_image(
    user_name: str,
    celebrity_name: str,
    user_score: int,
    celebrity_score: int,
    gap: int,
    rank: str = "Challenger",
    format_type: str = "square",  # "square" (1080x1080) or "vertical" (1080x1920)
    time_remaining: str = "4d 18h",
    short_url: str = "popularoo.com/r/abc1234",
) -> BytesIO:
    """
    Generate a Rally Cry share image — UFC Fight Poster / NBA Scoreboard style.
    100% typographic. No avatars, no circles, no fake buttons.
    Layout:
      - Top band (~12%): Green #009B4D with "RALLY CRY" + "LIVE • timer"
      - User section (~38%): name (80-100px) + score in GOLD (200-250px)
      - VS band (~7%): Red #E04F5F full width with massive "VS"
      - Celebrity section (~38%): name (80-100px) + score in RED (200-250px)
      - Footer (~5%): "POPULAROO — The Stock Market of Fame" + short link
    """

    if format_type == "vertical":
        width, height = 1080, 1920
    else:
        width, height = 1080, 1080

    img = Image.new("RGB", (width, height), BRAND_DARK)
    draw = ImageDraw.Draw(img)
    cx = width // 2

    # ---- Proportional zones ----
    header_h = int(height * 0.12)
    section_h = int(height * 0.38)
    vs_h = int(height * 0.07)
    footer_h = int(height * 0.05)

    # ---- Font sizes (proportional) ----
    if format_type == "vertical":
        sz_header_title = 56
        sz_live = 32
        sz_label = 34
        sz_name = 90
        sz_score = 220
        sz_vs = 90
        sz_footer = 26
        sz_link = 22
    else:
        sz_header_title = 48
        sz_live = 28
        sz_label = 30
        sz_name = 80
        sz_score = 200
        sz_vs = 80
        sz_footer = 22
        sz_link = 20

    f_header_title = get_font(sz_header_title, bold=True)
    f_live = get_font(sz_live, bold=False)
    f_label = get_font(sz_label, bold=False)
    f_name = get_font(sz_name, bold=True)
    f_score = get_font(sz_score, bold=True)
    f_vs = get_font(sz_vs, bold=True)
    f_footer = get_font(sz_footer, bold=False)
    f_link = get_font(sz_link, bold=False)

    # ============ TOP HEADER BAND (green) ============
    y0 = 0
    draw.rectangle([(0, y0), (width, y0 + header_h)], fill=BRAND_GREEN)

    # "RALLY CRY" left-of-center
    header_cy = y0 + header_h // 2
    draw.text((60, header_cy), "RALLY CRY", font=f_header_title, fill="#FFFFFF", anchor="lm")

    # "LIVE • 4d 18h" right-of-center
    live_text = f"LIVE  •  {time_remaining}"
    draw.text((width - 60, header_cy), live_text, font=f_live, fill="#FFFFFF", anchor="rm")

    # Thin bright line at bottom of header
    draw.rectangle([(0, y0 + header_h - 3), (width, y0 + header_h)], fill=BRAND_GOLD)

    # ============ USER SECTION (top half) ============
    user_y0 = header_h
    user_cy = user_y0 + section_h // 2

    # "OUTSIDER" label
    label_y = user_y0 + int(section_h * 0.15)
    draw.text((cx, label_y), "OUTSIDER", font=f_label, fill=BRAND_GOLD, anchor="mm")

    # User name (truncated if needed)
    name_y = user_y0 + int(section_h * 0.38)
    user_display = _truncate_name(draw, user_name, f_name, width - 120)
    draw.text((cx, name_y), user_display, font=f_name, fill="#FFFFFF", anchor="mm")

    # User score — MASSIVE in GOLD
    score_y = user_y0 + int(section_h * 0.72)
    user_score_text = _format_score(user_score)
    draw.text((cx, score_y), user_score_text, font=f_score, fill=BRAND_GOLD, anchor="mm")

    # ============ VS BAND (red bar) ============
    vs_y0 = header_h + section_h
    draw.rectangle([(0, vs_y0), (width, vs_y0 + vs_h)], fill=BRAND_RED)

    # "VS" centered — massive white
    vs_cy = vs_y0 + vs_h // 2
    draw.text((cx, vs_cy), "VS", font=f_vs, fill="#FFFFFF", anchor="mm")

    # ============ CELEBRITY SECTION (bottom half) ============
    celeb_y0 = header_h + section_h + vs_h

    # "CELEBRITY" label
    clabel_y = celeb_y0 + int(section_h * 0.15)
    draw.text((cx, clabel_y), "CELEBRITY", font=f_label, fill=BRAND_RED, anchor="mm")

    # Celebrity name (truncated if needed)
    cname_y = celeb_y0 + int(section_h * 0.38)
    celeb_display = _truncate_name(draw, celebrity_name, f_name, width - 120)
    draw.text((cx, cname_y), celeb_display, font=f_name, fill="#FFFFFF", anchor="mm")

    # Celebrity score — MASSIVE in RED
    cscore_y = celeb_y0 + int(section_h * 0.72)
    celeb_score_text = _format_score(celebrity_score)
    draw.text((cx, cscore_y), celeb_score_text, font=f_score, fill=BRAND_RED, anchor="mm")

    # ============ FOOTER ============
    footer_y0 = height - footer_h
    # Thin separator
    draw.rectangle([(0, footer_y0), (width, footer_y0 + 2)], fill=BRAND_GOLD + "55")

    # "POPULAROO — The Stock Market of Fame"
    brand_y = footer_y0 + int(footer_h * 0.35)
    draw.text((cx, brand_y), "POPULAROO — The Stock Market of Fame", font=f_footer, fill=BRAND_GOLD, anchor="mm")

    # Short link
    link_y = footer_y0 + int(footer_h * 0.75)
    draw.text((cx, link_y), short_url, font=f_link, fill="#FFFFFF80", anchor="mm")

    # ============ EXPORT ============
    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer


# ---- Pre-written Share Messages ----
def get_share_messages(user_name: str, celebrity_name: str, gap: int, short_url: str) -> Dict[str, str]:
    """Generate platform-adapted share messages"""
    
    base_message = f"I'm competing against {celebrity_name} on Popularoo! Only {abs(gap)} points away. Help me win!"
    
    return {
        "whatsapp": f"🚀 {user_name} vs {celebrity_name} on Popularoo!\n\n"
                    f"{'Only ' + str(abs(gap)) + ' points to go!' if gap > 0 else 'Currently ahead!'}\n\n"
                    f"Vote here 👉 {short_url}",
        
        "sms": f"{user_name} needs your vote on Popularoo! Competing against {celebrity_name}. "
               f"Vote here: {short_url}",
        
        "twitter": f"I'm taking on {celebrity_name} on @Popularoo 🏆\n"
                   f"{'Only ' + str(abs(gap)) + ' momentum behind!' if gap > 0 else '💪 Currently ahead!'}\n\n"
                   f"Help me rise to Legend 👉 {short_url}\n\n"
                   f"#Popularoo #BullRun",
        
        "instagram": f"🏆 RALLY CRY 🏆\n\n"
                     f"{user_name} vs {celebrity_name}\n"
                     f"Gap: {abs(gap)} momentum\n\n"
                     f"Vote on Popularoo!\n"
                     f"Link in bio or: {short_url}",
        
        "tiktok": f"Can I beat {celebrity_name} on Popularoo? 🤔\n"
                  f"I need YOUR vote! 🚀\n"
                  f"{short_url}",
        
        "generic": base_message + f"\n\n{short_url}",
    }


# ---- Public Page HTML Generation ----
def generate_rally_page_html(
    user_name: str,
    celebrity_name: str,
    user_score: int,
    celebrity_score: int,
    gap: int,
    rank: str,
    short_id: str,
    rally_id: str,
) -> str:
    """Generate a server-rendered public page for a Rally Cry"""
    
    og_title = f"{user_name} vs {celebrity_name} — Rally Cry on Popularoo"
    og_description = f"{user_name} is competing against {celebrity_name}! {abs(gap)} momentum {'behind' if gap > 0 else 'ahead'}. Vote now!"
    og_image = f"{SITE_URL}/api/share/rally-image/{rally_id}/square"
    page_url = f"{SITE_URL}/r/{short_id}"
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{og_title}</title>
    
    <!-- Open Graph -->
    <meta property="og:title" content="{og_title}">
    <meta property="og:description" content="{og_description}">
    <meta property="og:image" content="{og_image}">
    <meta property="og:url" content="{page_url}">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Popularoo">
    
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{og_title}">
    <meta name="twitter:description" content="{og_description}">
    <meta name="twitter:image" content="{og_image}">
    
    <!-- Apple Universal Link meta -->
    <meta name="apple-itunes-app" content="app-id=6743206968, app-argument={page_url}">
    
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: {BRAND_DARK}; color: {BRAND_LIGHT}; 
            min-height: 100vh; display: flex; flex-direction: column; align-items: center;
            padding: 40px 20px;
        }}
        .container {{ max-width: 480px; width: 100%; }}
        .header {{ text-align: center; margin-bottom: 32px; }}
        .header h1 {{ color: {BRAND_GOLD}; font-size: 28px; letter-spacing: 2px; }}
        .header p {{ color: {BRAND_LIGHT}99; font-size: 14px; margin-top: 8px; }}
        .scoreboard {{ 
            background: {BRAND_CARD}; border: 2px solid {BRAND_BORDER}; 
            border-radius: 16px; padding: 24px; margin-bottom: 24px; 
        }}
        .player {{ display: flex; align-items: center; gap: 16px; padding: 16px 0; }}
        .player-initial {{ 
            width: 56px; height: 56px; border-radius: 50%; 
            display: flex; align-items: center; justify-content: center;
            font-size: 24px; font-weight: 800; 
        }}
        .player-info {{ flex: 1; }}
        .player-name {{ font-size: 20px; font-weight: 700; }}
        .player-rank {{ font-size: 12px; color: {BRAND_GOLD}; margin-top: 4px; }}
        .player-score {{ font-size: 32px; font-weight: 800; }}
        .gap {{ 
            text-align: center; padding: 12px; border-radius: 20px; 
            font-size: 14px; font-weight: 700; margin: 8px 0;
            background: {'#E04F5F22' if gap > 0 else BRAND_GREEN + '22'};
            color: {'#E04F5F' if gap > 0 else BRAND_GREEN};
        }}
        .cta {{ 
            display: block; width: 100%; padding: 18px; text-align: center;
            background: {BRAND_GOLD}; color: {BRAND_DARK}; border-radius: 30px;
            font-size: 18px; font-weight: 800; text-decoration: none;
            margin-bottom: 12px;
        }}
        .cta:hover {{ opacity: 0.9; }}
        .store-links {{ display: flex; gap: 12px; justify-content: center; margin-top: 16px; }}
        .store-links a {{ 
            padding: 10px 20px; border: 1px solid {BRAND_BORDER}; border-radius: 8px;
            color: {BRAND_LIGHT}; text-decoration: none; font-size: 13px;
        }}
        .footer {{ text-align: center; margin-top: 32px; color: {BRAND_LIGHT}55; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>RALLY CRY</h1>
            <p>The Stock Market of Fame</p>
        </div>
        
        <div class="scoreboard">
            <div class="player">
                <div class="player-initial" style="background: {BRAND_GOLD}; color: {BRAND_DARK};">
                    {user_name[0].upper() if user_name else '?'}
                </div>
                <div class="player-info">
                    <div class="player-name">{user_name}</div>
                    <div class="player-rank">{rank}</div>
                </div>
                <div class="player-score" style="color: {BRAND_GOLD};">{user_score}</div>
            </div>
            
            <div class="gap">
                {'▼' if gap > 0 else '▲'} {abs(gap)} momentum {'behind' if gap > 0 else 'ahead'}
            </div>
            
            <div class="player">
                <div class="player-initial" style="background: #E04F5F; color: #FFF;">
                    {celebrity_name[0].upper() if celebrity_name else '?'}
                </div>
                <div class="player-info">
                    <div class="player-name">{celebrity_name}</div>
                    <div class="player-rank" style="color: #E04F5F99;">Celebrity</div>
                </div>
                <div class="player-score" style="color: #E04F5F;">{celebrity_score}</div>
            </div>
        </div>
        
        <a href="popularoo://rally/{rally_id}" class="cta">
            Vote for {user_name.split(' ')[0]}!
        </a>
        
        <div class="store-links">
            <a href="{APP_STORE_URL}">📱 App Store</a>
            <a href="{PLAY_STORE_URL}">🤖 Google Play</a>
        </div>
        
        <div class="footer">
            <p>Popularoo — Compete with real celebrities</p>
        </div>
    </div>
</body>
</html>"""


def generate_user_page_html(
    user_name: str,
    rank: str,
    total_votes: int,
    wins: list,
    short_id: str,
    person_id: str,
) -> str:
    """Generate a server-rendered public profile page"""
    
    og_title = f"{user_name} on Popularoo — {rank}"
    og_description = f"{user_name} has {total_votes} votes and has out-rallied {len(wins)} celebrities. Vote now!"
    page_url = f"{SITE_URL}/u/{short_id}"
    
    wins_html = ""
    for w in wins[:5]:
        wins_html += f'<li>Out-rallied <strong>{w}</strong></li>'
    if not wins:
        wins_html = '<li style="color: #999;">No victories yet — be the first to vote!</li>'
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{og_title}</title>
    
    <!-- Open Graph -->
    <meta property="og:title" content="{og_title}">
    <meta property="og:description" content="{og_description}">
    <meta property="og:url" content="{page_url}">
    <meta property="og:type" content="profile">
    <meta property="og:site_name" content="Popularoo">
    
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{og_title}">
    <meta name="twitter:description" content="{og_description}">
    
    <!-- Apple Universal Link meta -->
    <meta name="apple-itunes-app" content="app-id=6743206968, app-argument={page_url}">
    
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: {BRAND_DARK}; color: {BRAND_LIGHT};
            min-height: 100vh; display: flex; flex-direction: column; align-items: center;
            padding: 40px 20px;
        }}
        .container {{ max-width: 480px; width: 100%; }}
        .profile {{ text-align: center; margin-bottom: 32px; }}
        .initial {{ 
            width: 80px; height: 80px; border-radius: 50%; margin: 0 auto 16px;
            display: flex; align-items: center; justify-content: center;
            background: {BRAND_GOLD}; color: {BRAND_DARK};
            font-size: 36px; font-weight: 800;
        }}
        .profile h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .rank {{ color: {BRAND_GOLD}; font-size: 16px; font-weight: 600; }}
        .stats {{ 
            display: flex; gap: 16px; justify-content: center; margin: 20px 0;
        }}
        .stat {{ 
            background: {BRAND_CARD}; border: 1px solid {BRAND_BORDER};
            border-radius: 12px; padding: 16px 24px; text-align: center;
        }}
        .stat-num {{ font-size: 24px; font-weight: 800; color: {BRAND_GOLD}; }}
        .stat-label {{ font-size: 11px; color: {BRAND_LIGHT}88; margin-top: 4px; }}
        .wins {{ 
            background: {BRAND_CARD}; border: 1px solid {BRAND_BORDER};
            border-radius: 12px; padding: 20px; margin: 20px 0;
        }}
        .wins h3 {{ color: {BRAND_GOLD}; font-size: 14px; margin-bottom: 12px; }}
        .wins ul {{ list-style: none; }}
        .wins li {{ 
            padding: 8px 0; border-bottom: 1px solid {BRAND_BORDER};
            font-size: 14px;
        }}
        .wins li:last-child {{ border-bottom: none; }}
        .cta {{ 
            display: block; width: 100%; padding: 18px; text-align: center;
            background: {BRAND_GOLD}; color: {BRAND_DARK}; border-radius: 30px;
            font-size: 18px; font-weight: 800; text-decoration: none;
            margin: 24px 0 12px;
        }}
        .store-links {{ display: flex; gap: 12px; justify-content: center; }}
        .store-links a {{ 
            padding: 10px 20px; border: 1px solid {BRAND_BORDER}; border-radius: 8px;
            color: {BRAND_LIGHT}; text-decoration: none; font-size: 13px;
        }}
        .footer {{ text-align: center; margin-top: 32px; color: {BRAND_LIGHT}55; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="profile">
            <div class="initial">{user_name[0].upper() if user_name else '?'}</div>
            <h1>{user_name}</h1>
            <div class="rank">{rank}</div>
        </div>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-num">{total_votes}</div>
                <div class="stat-label">VOTES</div>
            </div>
            <div class="stat">
                <div class="stat-num">{len(wins)}</div>
                <div class="stat-label">WINS</div>
            </div>
        </div>
        
        <div class="wins">
            <h3>🏆 Recent victories</h3>
            <ul>{wins_html}</ul>
        </div>
        
        <a href="popularoo://person/{person_id}" class="cta">
            Vote for {user_name.split(' ')[0]}!
        </a>
        
        <div class="store-links">
            <a href="{APP_STORE_URL}">📱 App Store</a>
            <a href="{PLAY_STORE_URL}">🤖 Google Play</a>
        </div>
        
        <div class="footer">
            <p>Popularoo — The Stock Market of Fame</p>
        </div>
    </div>
</body>
</html>"""


# ---- Deep Link Configuration Files ----
APPLE_APP_SITE_ASSOCIATION = {
    "applinks": {
        "apps": [],
        "details": [
            {
                "appID": "WWSNPS7M6R.com.popularoo.app",
                "paths": ["/r/*", "/u/*"]
            }
        ]
    }
}

ANDROID_ASSET_LINKS = [
    {
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.popularoo.app",
            "sha256_cert_fingerprints": ["37:80:02:5F:A5:AD:9E:ED:CB:DB:FF:22:ED:64:CF:29:0D:37:90:FA:8E:2B:18:E1:69:E7:40:29:76:5C:8E:62"]
        }
    }
]
