import asyncio
import aiohttp
import random
from dataclasses import dataclass
from typing import Optional


CSRF_URL = "https://auth.roblox.com/v2/logout"
AUTH_URL = "https://users.roblox.com/v1/users/authenticated"
REPORT_URL = "https://abuse.roblox.com/v2/moderation/report-game"
UNIVERSE_URL = "https://apis.roblox.com/universes/v1/places/{place_id}/universe"
GAME_DETAIL_URL = "https://games.roblox.com/v1/games?universeIds={universe_id}"

REPORT_COMMENT = (
    "This game contains inappropriate sexual content targeting minors (condo game). "
    "Immediate removal and investigation requested."
)


@dataclass
class RobloxSession:
    cookie: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    csrf_token: Optional[str] = None


async def fetch_csrf(session: aiohttp.ClientSession, cookie: str, proxy: Optional[str]) -> str:
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    async with session.post(CSRF_URL, headers=headers, proxy=proxy, ssl=False) as resp:
        token = resp.headers.get("x-csrf-token")
        if not token:
            raise RuntimeError("CSRF fetch failed — cookie invalid or expired")
        return token


async def authenticate(
    session: aiohttp.ClientSession,
    rob: RobloxSession,
    proxy: Optional[str]
) -> None:
    headers = {
        "Cookie": f".ROBLOSECURITY={rob.cookie}",
        "x-csrf-token": rob.csrf_token
    }
    async with session.get(AUTH_URL, headers=headers, proxy=proxy, ssl=False) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Auth failed — HTTP {resp.status}")
        data = await resp.json()
        rob.user_id = data["id"]
        rob.username = data["name"]


async def resolve_universe(
    session: aiohttp.ClientSession,
    place_id: int,
    cookie: str,
    proxy: Optional[str]
) -> int:
    url = UNIVERSE_URL.format(place_id=place_id)
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    async with session.get(url, headers=headers, proxy=proxy, ssl=False) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Universe resolve failed — HTTP {resp.status}")
        data = await resp.json()
        return data["universeId"]


async def fetch_game(
    session: aiohttp.ClientSession,
    universe_id: int,
    cookie: str,
    proxy: Optional[str]
) -> dict:
    url = GAME_DETAIL_URL.format(universe_id=universe_id)
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    async with session.get(url, headers=headers, proxy=proxy, ssl=False) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Game detail fetch failed — HTTP {resp.status}")
        data = await resp.json()
        games = data.get("data", [])
        if not games:
            raise RuntimeError("No game data returned")
        return games[0]


async def submit_report(
    session: aiohttp.ClientSession,
    rob: RobloxSession,
    place_id: int,
    universe_id: int,
    proxy: Optional[str]
) -> bool:
    headers = {
        "Cookie": f".ROBLOSECURITY={rob.cookie}",
        "x-csrf-token": rob.csrf_token,
        "Content-Type": "application/json",
        "Referer": f"https://www.roblox.com/games/{place_id}"
    }
    payload = {
        "universeId": universe_id,
        "placeId": place_id,
        "reasonId": 1,
        "comment": REPORT_COMMENT,
        "reporterUserId": rob.user_id
    }
    async with session.post(
        REPORT_URL, headers=headers, json=payload, proxy=proxy, ssl=False
    ) as resp:
        return resp.status in (200, 201, 204)


async def report_condo_games_with_proxy(
    cookie: str,
    place_ids: list[int],
    proxies: list[str]
) -> list[dict]:
    proxy_pool = proxies if proxies else [None]
    results = []

    connector = aiohttp.TCPConnector(ssl=False, limit=8, force_close=True)
    async with aiohttp.ClientSession(connector=connector) as http:
        proxy = random.choice(proxy_pool)

        rob = RobloxSession(cookie=cookie)
        rob.csrf_token = await fetch_csrf(http, cookie, proxy)
        await authenticate(http, rob, proxy)

        for place_id in place_ids:
            proxy = random.choice(proxy_pool)
            result = {
                "place_id": place_id,
                "status": "unknown",
                "game_name": "—",
                "creator": "—",
                "proxy_used": proxy or "direct",
                "error": None
            }
            try:
                universe_id = await resolve_universe(http, place_id, cookie, proxy)
                game = await fetch_game(http, universe_id, cookie, proxy)
                result["game_name"] = game.get("name", "Unknown")
                result["creator"] = game.get("creator", {}).get("name", "Unknown")

                success = await submit_report(http, rob, place_id, universe_id, proxy)
                result["status"] = "reported" if success else "failed"
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)

            results.append(result)
            await asyncio.sleep(2.0)

    return results
