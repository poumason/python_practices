import csv
import os
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from temporalio import activity

KKBOX_SEARCH_PAGE = "https://www.kkbox.com/tw/tc/search"
KKBOX_SEARCH_API = "https://www.kkbox.com/api/search/{kind}"


def _kkbox_search(session: requests.Session, kind: str, keyword: str) -> list[dict]:
    response = session.get(
        KKBOX_SEARCH_API.format(kind=kind),
        params={"q": keyword, "terr": "tw", "lang": "tc"},
        headers={
            "Referer": f"{KKBOX_SEARCH_PAGE}?q={quote(keyword)}",
            "Accept": "application/json",
        },
        timeout=20,
    )
    response.raise_for_status()
    if response.status_code != 200 or not response.text:
        # KKBOX occasionally answers with a 202 bot-check instead of data.
        # Raise so Temporal's activity retry policy backs off and tries again.
        raise RuntimeError(f"KKBOX {kind} search not ready yet (status={response.status_code})")
    return response.json().get("data", {}).get("result", [])


@activity.defn
async def fetch_cnblue_news(query: str = "CNBLUE") -> str:
    """Search KKBOX for the artist's songs and albums and write the latest
    results to a CSV file. Returns the path of the CSV file written.

    KKBOX's search API only replies once the session cookie from its search
    page has been set, so we visit that page first to pick up the cookie,
    then call the song/album JSON APIs it uses internally.
    """
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; TemporalWorkerExample/1.0)"
    session.get(KKBOX_SEARCH_PAGE, params={"q": query}, timeout=20)

    songs = _kkbox_search(session, "song", query)
    albums = _kkbox_search(session, "album", query)

    album_release_date = {album["url"]: album.get("release_date", "") for album in albums}

    rows = []
    for song in songs:
        album = song.get("album", {})
        rows.append(
            {
                "type": "song",
                "title": song.get("name", ""),
                "artist": ", ".join(a.get("name", "") for a in song.get("artist_roles", [])),
                "album": album.get("name", ""),
                "release_date": album_release_date.get(album.get("url", ""), ""),
                "url": song.get("url", ""),
            }
        )
    for album in albums:
        rows.append(
            {
                "type": "album",
                "title": album.get("name", ""),
                "artist": album.get("artist", {}).get("name", ""),
                "album": album.get("name", ""),
                "release_date": album.get("release_date", ""),
                "url": album.get("url", ""),
            }
        )

    rows.sort(key=lambda r: r["release_date"], reverse=True)

    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = os.path.join(out_dir, f"cnblue_kkbox_{timestamp}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["type", "title", "artist", "album", "release_date", "url"])
        writer.writeheader()
        writer.writerows(rows)

    activity.logger.info(f"Wrote {len(rows)} KKBOX song/album rows to {csv_path}")
    return csv_path
