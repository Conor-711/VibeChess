import asyncio
import json
import time

import aiohttp
from loguru import logger

limit_try_num = 3

proxy_auth = None

proxy_url = None


async def refresh_guest_token():
    url = 'https://api.twitter.com/1.1/guest/activate.json'

    headers = {
        'authority': 'api.twitter.com',
        'authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        'origin': 'https://twitter.com',
        'referer': 'https://twitter.com/',
    }

    connector = aiohttp.TCPConnector(ssl=False, limit=100, limit_per_host=100, force_close=True)
    r = None
    
    async with aiohttp.ClientSession(connector=connector) as session:
        try_num = 0
        while try_num < limit_try_num:
            try:
                async with session.post(url, headers=headers) as response:
                    r = await response.json()
                    logger.info(f"Guest token refreshed successfully")
                    return r['guest_token']
            except Exception as e:
                logger.error(f"Refresh guest token error: {e}")
                try_num += 1
                await asyncio.sleep(1)  # 添加延迟，避免请求过于频繁
    
    # 如果所有尝试都失败，记录错误并抛出异常
    if not r or 'guest_token' not in r:
        error_msg = "Failed to refresh guest token after multiple attempts"
        logger.error(error_msg)
        raise Exception(error_msg)
        
    return r['guest_token']


guest_token = asyncio.run(refresh_guest_token())


async def get_twitter_user_id(screen_name):
    global guest_token
    endpoint = "https://api.twitter.com/graphql/laYnJPCAcVo0o6pzcnlVxQ/UserByScreenName"
    params = {
        "variables": "{\"screen_name\":\"%s\"}" % (screen_name),
        "features": "{\"hidden_profile_subscriptions_enabled\":true,\"rweb_tipjar_consumption_enabled\":true,\"responsive_web_graphql_exclude_directive_enabled\":true,\"verified_phone_label_enabled\":false,\"subscriptions_verification_info_is_identity_verified_enabled\":true,\"subscriptions_verification_info_verified_since_enabled\":true,\"highlights_tweets_tab_ui_enabled\":true,\"responsive_web_twitter_article_notes_tab_enabled\":true,\"subscriptions_feature_can_gift_premium\":true,\"creator_subscriptions_tweet_preview_api_enabled\":true,\"responsive_web_graphql_skip_user_profile_image_extensions_enabled\":false,\"responsive_web_graphql_timeline_navigation_enabled\":true}",
        "fieldToggles": "{\"withAuxiliaryUserLabels\":false}"
    }

    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        'authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://twitter.com",
        "referer": "https://twitter.com/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "x-client-transaction-id": "pTJi/Qy0VYYahI4nE/udjuPrt/5hZYpqpFBjd7kH+10PJqZykh3jczzc8E/RwLFtVPl3Uac3Q3VDHq824Sh7msuwo168pg",
        "x-guest-token": guest_token,
    }

    connector = aiohttp.TCPConnector(ssl=False, limit=100, limit_per_host=100, force_close=True)

    async with aiohttp.ClientSession(connector=connector) as session:
        try_num = 0
        while try_num < limit_try_num:
            try_num += 1
            try:
                async with session.get(endpoint, headers=headers, params=params) as response:
                    resp = await response.text()
                    if int(response.headers.get("x-rate-limit-remaining", 0)) <= 1 or int(
                            response.headers.get("x-rate-limit-reset", int(time.time()) - 100)) <= int(time.time()):
                        guest_token = await refresh_guest_token()
                        return await get_twitter_user_id(screen_name)
                    r = json.loads(resp)
                    return r
            except Exception as e:
                logger.error(f"get twitter profile info error: {e}")
                try_num += 1

if __name__ == "__main__":
    username = "elonmusk"
    user_data = asyncio.run(get_twitter_user_id(username))
    print(json.dumps(user_data, indent=2, ensure_ascii=False))
