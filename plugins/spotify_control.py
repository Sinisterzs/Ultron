"""
Spotify playback control plugin for Mark LVI.

Controls the Spotify desktop application on this computer through the Spotify
Web API.  When the user asks the assistant to play a song, artist, album or
playlist **on Spotify**, Gemini routes the request here instead of opening a
browser tab or just launching the app.

REQUIREMENTS
    pip install spotipy

    The user must also:
      1. Create an app at https://developer.spotify.com/dashboard
      2. Copy the Client ID (Client Secret is optional for legacy OAuth) into Settings -> PLUGIN SETTINGS -> Spotify
      3. Set the Redirect URI to http://127.0.0.1:8888/callback (already the default)
      4. Have a Spotify **Premium** account (playback endpoints require it)
      5. Have the Spotify desktop app open on this PC (it must be an active device)

    The very first 'play' command opens a browser tab for the OAuth consent page.
    After that the token is cached and everything is automatic.
"""

import sys
from pathlib import Path

from memory.config_manager import get_plugin_setting, save_plugin_config

# ── Lazy import — spotipy may not be installed ────────────────────────────────
_SPOTIPY_AVAILABLE = True
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth, SpotifyPKCE
    from spotipy.cache_handler import CacheHandler
except ImportError:
    _SPOTIPY_AVAILABLE = False
    CacheHandler = object

# ── Token cache location ──────────────────────────────────────────────────────
class _ProtectedCache(CacheHandler):
    """OAuth tokens use the same protected user configuration as API keys."""
    def get_cached_token(self):
        return get_plugin_setting("spotify", "oauth_cache", None)

    def save_token_to_cache(self, token_info):
        save_plugin_config("spotify", {"oauth_cache": token_info})


# ── Spotify client singleton ─────────────────────────────────────────────────
_sp_client = None


def _get_client():
    """Return an authenticated Spotify client, creating one if necessary."""
    global _sp_client

    if not _SPOTIPY_AVAILABLE:
        raise RuntimeError(
            "The 'spotipy' library is not installed. "
            "Run: pip install spotipy"
        )

    client_id     = get_plugin_setting("spotify", "client_id", "").strip()
    client_secret = get_plugin_setting("spotify", "client_secret", "").strip()
    redirect_uri  = (get_plugin_setting("spotify", "redirect_uri", "").strip()
                     or "http://127.0.0.1:8888/callback")

    if not client_id:
        raise RuntimeError(
            "Spotify credentials are not configured. "
            "Go to Settings, Plugin Settings, Spotify and enter your "
            "Client ID."
        )

    scope = (
        "user-read-playback-state "
        "user-modify-playback-state "
        "user-read-currently-playing"
    )

    options = dict(client_id=client_id, redirect_uri=redirect_uri,
                   scope=scope, cache_handler=_ProtectedCache(), open_browser=True)
    # Existing private configurations remain compatible; distributed installs use PKCE.
    if client_secret:
        auth_manager = SpotifyOAuth(client_secret=client_secret, **options)
    else:
        auth_manager = SpotifyPKCE(**options)

    _sp_client = spotipy.Spotify(auth_manager=auth_manager)
    return _sp_client


# ── Device helper ─────────────────────────────────────────────────────────────

def _find_this_pc(sp):
    """Return the first active Spotify device on this computer, or None."""
    devices = sp.devices().get("devices", [])
    if not devices:
        return None
    for d in devices:
        if d.get("is_active"):
            return d
    for d in devices:
        if d.get("type", "").lower() == "computer":
            return d
    return devices[0]


# ── Search helper ─────────────────────────────────────────────────────────────

def _search_and_play(sp, query: str, device_id: str) -> str:
    """Search Spotify for *query* and start playback of the best match."""
    q_lower = query.lower().strip()

    search_type = "track"
    search_query = query
    for prefix in ("playlist", "album", "artist"):
        if q_lower.startswith(prefix + " "):
            search_type = prefix
            search_query = query[len(prefix):].strip()
            break

    results = sp.search(q=search_query, type=search_type, limit=1)

    items_key = search_type + "s"
    items = results.get(items_key, {}).get("items", [])
    if not items:
        return f"I couldn't find any {search_type} matching '{search_query}' on Spotify."

    item = items[0]
    name = item.get("name", search_query)

    if search_type == "track":
        uri = item["uri"]
        artist = ", ".join(a["name"] for a in item.get("artists", []))
        sp.start_playback(device_id=device_id, uris=[uri])
        return f"Playing {name} by {artist} on Spotify."

    elif search_type == "artist":
        uri = item["uri"]
        sp.start_playback(device_id=device_id, context_uri=uri)
        return f"Playing {name} on Spotify."

    else:  # album or playlist
        uri = item["uri"]
        owner = ""
        if search_type == "playlist":
            owner = item.get("owner", {}).get("display_name", "")
        sp.start_playback(device_id=device_id, context_uri=uri)
        label = f"{search_type} {name}"
        if owner:
            label += f" by {owner}"
        return f"Playing {label} on Spotify."



# ── Action dispatcher ─────────────────────────────────────────────────────────

_NO_DEVICE_MSG = (
    "Spotify doesn't seem to be open on this computer. "
    "Please open the Spotify app and try again."
)


def _dispatch(sp, action: str, params: dict) -> str:
    """Route an action string to the correct Spotify API call."""
    device = _find_this_pc(sp)
    device_id = device["id"] if device else None

    if action == "play":
        query = params.get("query", "").strip()
        if not device:
            return _NO_DEVICE_MSG
        if not query:
            sp.start_playback(device_id=device_id)
            return "Resumed playback on Spotify."
        return _search_and_play(sp, query, device_id)

    elif action == "pause":
        sp.pause_playback(device_id=device_id)
        return "Paused Spotify."

    elif action == "resume":
        if not device:
            return _NO_DEVICE_MSG
        sp.start_playback(device_id=device_id)
        return "Resumed playback on Spotify."

    elif action == "next":
        sp.next_track(device_id=device_id)
        return "Skipped to the next track on Spotify."

    elif action == "previous":
        sp.previous_track(device_id=device_id)
        return "Went back to the previous track on Spotify."

    elif action == "volume":
        vol = params.get("volume_percent")
        if vol is None:
            return "Please specify a volume level between 0 and 100."
        vol = max(0, min(100, int(vol)))
        sp.volume(vol, device_id=device_id)
        return f"Spotify volume set to {vol}%."

    elif action == "current":
        current = sp.current_playback()
        if not current or not current.get("item"):
            return "Nothing is playing on Spotify right now."
        track = current["item"]
        name = track.get("name", "Unknown")
        artist = ", ".join(a["name"] for a in track.get("artists", []))
        is_playing = current.get("is_playing", False)
        status = "Playing" if is_playing else "Paused"
        return f"{status}: {name} by {artist}."

    elif action == "shuffle":
        current = sp.current_playback()
        shuffle_on = not (current or {}).get("shuffle_state", False)
        sp.shuffle(shuffle_on, device_id=device_id)
        state = "on" if shuffle_on else "off"
        return f"Shuffle turned {state}."

    elif action == "repeat":
        current = sp.current_playback()
        repeat_state = (current or {}).get("repeat_state", "off")
        cycle = {"off": "context", "context": "track", "track": "off"}
        new_state = cycle.get(repeat_state, "off")
        sp.repeat(new_state, device_id=device_id)
        labels = {"off": "off", "context": "all", "track": "this track"}
        return f"Repeat set to {labels.get(new_state, new_state)}."

    else:
        return (
            f"Unknown Spotify action: '{action}'. "
            "Try play, pause, resume, next, previous, volume, current, "
            "shuffle, or repeat."
        )



# ═══════════════════════════════════════════════════════════════════════════════
#  Plugin contract
# ═══════════════════════════════════════════════════════════════════════════════

PLUGIN = {
    "name": "spotify_control",
    "description": (
        "Controls Spotify playback on the user's computer — play a song/artist/"
        "album/playlist by name, pause, resume, skip, go back, change volume, "
        "toggle shuffle/repeat, or ask what is currently playing. "
        "Use this whenever the user asks to play music on Spotify instead of "
        "opening a browser tab or using 'open_app'. "
        "Do NOT use 'browser_control' or 'open_app' for Spotify music requests; "
        "use this tool."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "What to do: 'play' (play/search a song, or resume if no "
                    "query), 'pause', 'resume', 'next' (skip), 'previous' "
                    "(go back), 'volume' (set volume), 'current' (what is "
                    "playing now), 'shuffle' (toggle), 'repeat' (cycle mode)."
                ),
            },
            "query": {
                "type": "STRING",
                "description": (
                    "Search query for the 'play' action. Can be a song name, "
                    "artist name, or prefixed with 'playlist', 'album', or "
                    "'artist' for specific searches. Examples: "
                    "'Bohemian Rhapsody', 'artist The Weeknd', "
                    "'playlist chill vibes', 'album Abbey Road'. "
                    "Not needed for other actions."
                ),
            },
            "volume_percent": {
                "type": "INTEGER",
                "description": (
                    "Volume level from 0 to 100. Only used with "
                    "action='volume'."
                ),
            },
        },
        "required": ["action"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "spotify",
    "title": "Spotify",
    "fields": [
        {
            "key": "client_id",
            "label": "Client ID",
            "type": "text",
            "hint": "From https://developer.spotify.com/dashboard",
        },
        {
            "key": "client_secret",
            "label": "Client Secret (legacy, optional)",
            "type": "password",
            "hint": "Leave blank for the desktop PKCE login flow",
        },
        {
            "key": "redirect_uri",
            "label": "Redirect URI",
            "type": "text",
            "default": "http://127.0.0.1:8888/callback",
            "hint": "Must match the one in your Spotify app settings",
        },
    ],
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Entry point called by the plugin loader.

    Never raises — every error is caught and returned as a spoken string.
    """
    action = (parameters.get("action") or "").strip().lower()
    if not action:
        return "No Spotify action was specified."

    try:
        sp = _get_client()
    except Exception as e:
        return f"Sir, I couldn't connect to Spotify: {e}"

    try:
        result = _dispatch(sp, action, parameters)
    except Exception as e:
        err = str(e)
        if "NO_ACTIVE_DEVICE" in err or "Not found" in err:
            result = _NO_DEVICE_MSG
        elif "PREMIUM_REQUIRED" in err or "premium" in err.lower():
            result = (
                "This feature requires a Spotify Premium account. "
                "Playback control through the API is not available "
                "on the free plan."
            )
        elif "token" in err.lower() or "access" in err.lower():
            result = (
                "The Spotify authorization has expired or is invalid. "
                "Please re-authorize in Settings, Plugin Settings, Spotify."
            )
        else:
            result = f"Sir, Spotify returned an error: {e}"

    if player:
        try:
            player.write_log(f"JARVIS: {result}")
        except Exception:
            pass

    return result

