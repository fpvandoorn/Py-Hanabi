import json
from typing import Optional, Dict

import requests_cache
import platformdirs

from hanabi import logger
from hanabi import constants

# Cache all requests to site to reduce traffic and latency
session = requests_cache.CachedSession(platformdirs.user_cache_dir(constants.APP_NAME) + '/hanab.live')


def get(url, refresh=False) -> Optional[Dict | str]:
    #    print("sending request for " + url)
    query = "https://hanab.live/" + url
    logger.debug("GET {} (force_refresh={})".format(query, refresh))
    response = session.get(query, force_refresh=refresh)
    if not response:
        logger.error("Failed to get request {} from hanab.live".format(query))
        return None
    if not response.status_code == 200:
        logger.error("Request {} from hanab.live produced status code {}".format(query, response.status_code))
        return None
    if "application/json" in response.headers['content-type']:
        return json.loads(response.text)
    return response.text


def api(url, refresh=False):
    link = "api/v1/" + url
    if "?" in url:
        link += "&"
    else:
        link += "?"
    link += "size=100"
    return get(link, refresh)


def replay(seed):
    r = api("seed/" + str(seed))
    try:
        game_id = r['rows'][0]['id']
    except TypeError:
        return None
    return get("export/" + str(game_id))
