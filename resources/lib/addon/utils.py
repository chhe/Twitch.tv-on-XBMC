# -*- coding: utf-8 -*-
"""
     
    Copyright (C) 2016 Twitch-on-Kodi
    
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import re
import time
from datetime import datetime
from base64 import b64decode
from common import kodi
from strings import STRINGS
from tccleaner import TextureCacheCleaner
from constants import CLIENT_ID, REDIRECT_URI, LIVE_PREVIEW_TEMPLATE, Images, STORAGE, ADDON_DATA_DIR, REQUEST_LIMIT
from twitch.api.parameters import Boolean, Period, ClipPeriod, Direction, Language, SortBy, VideoSort
import xbmcvfs

translations = kodi.Translations(STRINGS)
i18n = translations.i18n


def get_redirect_uri():
    settings_id = kodi.get_setting('oauth_redirecturi')
    stripped_id = settings_id.strip()
    if settings_id != stripped_id:
        settings_id = stripped_id
        kodi.set_setting('oauth_redirecturi', settings_id)
    if settings_id:
        return settings_id.decode('utf-8')
    else:
        return REDIRECT_URI.decode('utf-8')


def get_client_id():
    settings_id = kodi.get_setting('oauth_clientid')
    stripped_id = settings_id.strip()
    if settings_id != stripped_id:
        settings_id = stripped_id
        kodi.set_setting('oauth_clientid', settings_id)
    if settings_id:
        return settings_id.decode('utf-8')
    else:
        return b64decode(CLIENT_ID).decode('utf-8')


def get_oauth_token(token_only=True, required=False):
    oauth_token = kodi.get_setting('oauth_token')
    if not oauth_token or not oauth_token.strip():
        if not required: return ''
        kodi.notify(kodi.get_name(), i18n('token_required'), sound=False)
        kodi.show_settings()
        oauth_token = kodi.get_setting('oauth_token')
    stripped_token = oauth_token.strip()
    if oauth_token != stripped_token:
        oauth_token = stripped_token
        kodi.set_setting('oauth_token', oauth_token)
    if oauth_token:
        if token_only:
            idx = oauth_token.find(':')
            if idx >= 0:
                oauth_token = oauth_token[idx + 1:]
        else:
            if not oauth_token.lower().startswith('oauth:'):
                idx = oauth_token.find(':')
                if idx >= 0:
                    oauth_token = oauth_token[idx + 1:]
                oauth_token = 'oauth:{0}'.format(oauth_token)
    return oauth_token.decode('utf-8')


def get_items_per_page():
    return int(kodi.get_setting('items_per_page'))


def calculate_pagination_values(index):
    index = int(index)
    limit = get_items_per_page()
    offset = index * limit
    return index, offset, limit


def get_offset(offset, item, items, key=None):
    if item is None:
        return int(offset) + REQUEST_LIMIT
    try:
        if key is None:
            return int(offset) + next(index for (index, _item) in enumerate(items) if item == _item)
        else:
            return int(offset) + next(index for (index, _item) in enumerate(items) if item == _item[key])
    except:
        return None


def the_art(art=None):
    if not art:
        art = {}
    return {'icon': art.get('icon', Images.ICON),
            'thumb': art.get('thumb', Images.THUMB),
            'poster': art.get('poster', Images.POSTER),
            'banner': art.get('banner', Images.BANNER),
            'fanart': art.get('fanart', Images.FANART),
            'clearart': art.get('clearart', Images.CLEARART),
            'clearlogo': art.get('clearlogo', Images.CLEARLOGO),
            'landscape': art.get('landscape', Images.LANDSCAPE)}


def link_to_next_page(queries):
    if 'index' in queries:
        queries['index'] += 1
    return {'label': i18n('next_page'),
            'art': the_art(),
            'path': kodi.get_plugin_url(queries)}


def irc_enabled():
    return kodi.get_setting('irc_enable') != 'true'


def exec_irc_script(username, channel):
    if not irc_enabled():
        return
    password = get_oauth_token(token_only=False, required=True)
    if username and password:
        host = 'irc.chat.twitch.tv'
        builtin = 'RunScript(script.ircchat, run_irc=True&nickname=%s&username=%s&password=%s&host=%s&channel=#%s)' % \
                  (username, username, password, host, channel)
        kodi.execute_builtin(builtin)


def notify_refresh():
    if kodi.get_setting('notify_refresh') == 'false':
        return False
    return True


def refresh_previews():
    if kodi.get_setting('live_previews_enable') != 'true':
        return
    if kodi.get_setting('refresh_previews') == 'true':
        refresh_interval = int(kodi.get_setting('refresh_interval')) * 60
        if get_refresh_diff() >= refresh_interval:
            set_refresh_stamp()
            TextureCacheCleaner().remove_like(LIVE_PREVIEW_TEMPLATE, notify_refresh())


def set_refresh_stamp():
    window = kodi.Window(10000)
    window.setProperty(key='%s-lpr_stamp' % kodi.get_id(), value=datetime.now())


def get_refresh_stamp():
    window = kodi.Window(10000)
    return window.getProperty(key='%s-lpr_stamp' % kodi.get_id())


def get_stamp_diff(current_stamp):
    stamp_format = '%Y-%m-%d %H:%M:%S.%f'
    current_datetime = datetime.now()
    if not current_stamp: return 86400  # 24 hrs
    stamp_datetime = datetime(*(time.strptime(current_stamp, stamp_format)[0:6]))  # datetime.strptime has issues
    time_delta = current_datetime - stamp_datetime
    total_seconds = 0
    if time_delta:
        total_seconds = ((time_delta.seconds + time_delta.days * 24 * 3600) * 10 ** 6) / 10 ** 6
    return total_seconds


def get_refresh_diff():
    return get_stamp_diff(get_refresh_stamp())


def extract_video(url):
    video_id = None
    seek_time = 0
    id_string = url  # http://twitch.tv/a/v/12345678?t=9m1s
    idx = id_string.find('?')
    if idx >= 0:
        id_string = id_string[:idx]  # https://twitch.tv/a/v/12345678
    idx = id_string.rfind('/')
    if idx >= 0:
        id_string = id_string[:idx] + id_string[idx + 1:]  # https://twitch.tv/a/v12345678
    idx = id_string.rfind('/')
    if idx >= 0:
        id_string = id_string[idx + 1:]  # v12345678
    if id_string.startswith("videos"):  # videos12345678
        id_string = "v" + id_string[6:]  # v12345678
    start_time = url  # http://twitch.tv/a/v/12345678?t=9m1s
    idx = url.find('?')
    if idx >= 0:
        time_string = start_time[idx:]  # t=9m1s
        pattern = re.compile('t=(?:(?P<hours>[0-9]+)(?:h))?(?:(?P<minutes>[0-9]+)(?:m))?(?:(?P<seconds>[0-9]+)(?:s))?')
        match = re.search(pattern, time_string)
        if match:
            hours = match.group('hours')
            minutes = match.group('minutes')
            seconds = match.group('seconds')
            if hours:
                seek_time += int(hours) * 3600
            if minutes:
                seek_time += int(minutes) * 60
            if seconds:
                seek_time += int(seconds)
    if id_string.startswith('v') or id_string.startswith('c') or id_string.startswith('a'):
        video_id = id_string
    return video_id, seek_time


_sorting_defaults = \
    {
        'followed_channels':
            {
                'by': SortBy.LAST_BROADCAST,
                'direction': Direction.DESC,
                'period': None
            },
        'channel_videos':
            {
                'by': VideoSort.VIEWS,
                'direction': None,
                'period': None
            },
        'clips':
            {
                'by': Boolean.TRUE,
                'direction': None,
                'period': ClipPeriod.WEEK
            },
        'top_videos':
            {
                'by': None,
                'direction': None,
                'period': Period.WEEK
            }
    }


def get_stored_json():
    if not xbmcvfs.exists(ADDON_DATA_DIR):
        result = xbmcvfs.mkdir(ADDON_DATA_DIR)
    json_data = STORAGE.load()
    needs_save = False
    # set defaults
    if 'blacklist' not in json_data:
        json_data['blacklist'] = {'user': [], 'game': [], 'community': []}
        needs_save = True
    if 'qualities' not in json_data:
        json_data['qualities'] = {'stream': [], 'video': [], 'clip': []}
        needs_save = True
    if 'sorting' not in json_data:
        json_data['sorting'] = _sorting_defaults
        needs_save = True
    if 'languages' not in json_data:
        json_data['languages'] = [Language.ALL]
        needs_save = True
    if needs_save:
        STORAGE.save(json_data)
    return json_data


def is_blacklisted(target, list_type='user'):
    json_data = get_stored_json()
    blacklist = json_data['blacklist'].get(list_type)
    if not blacklist:
        return False
    if isinstance(target, int):
        target = str(target)
    if list_type == 'user':
        return any(target == blacklist_id for blacklist_id, blacklist_name in blacklist)
    else:
        return any((target == blacklist_id or
                    target == blacklist_name) for blacklist_id, blacklist_name in blacklist)


def add_blacklist(target_id, name, list_type='user'):
    json_data = get_stored_json()

    if not is_blacklisted(target_id, list_type):
        blacklist = json_data['blacklist'].get(list_type)
        if not blacklist:
            json_data['blacklist'][list_type] = []
        json_data['blacklist'][list_type].append([target_id, name])
        STORAGE.save(json_data)
        return True
    return False


def remove_blacklist(list_type='user'):
    json_data = get_stored_json()
    result = kodi.Dialog().select(i18n('remove_from_blacklist') % list_type,
                                  [blacklist_name for blacklist_id, blacklist_name in json_data['blacklist'][list_type]])
    if result == -1:
        return None
    else:
        result = json_data['blacklist'][list_type].pop(result)
        STORAGE.save(json_data)
        return result


def get_languages():
    json_data = get_stored_json()
    return json_data['languages']


def add_language(language):
    json_data = get_stored_json()
    language = Language.validate(language)
    if language == Language.ALL:
        json_data['languages'] = [language]
    json_data['languages'].append(language)
    new_languages = list(set(json_data['languages']))
    try:
        index_of_all = new_languages.index(Language.ALL)
    except ValueError:
        index_of_all = -1
    if (index_of_all > -1) and len(new_languages) > 1:
        new_languages.remove(Language.ALL)
    json_data['languages'] = new_languages
    STORAGE.save(json_data)


def remove_language(language):
    json_data = get_stored_json()
    language = Language.validate(language)
    new_languages = [lang for lang in json_data['languages'] if lang != language]
    if len(new_languages) == 0:
        new_languages.append(Language.ALL)
    json_data['languages'] = new_languages
    STORAGE.save(json_data)


def get_sort(for_type, key=None):
    json_data = get_stored_json()
    sorting = json_data['sorting'].get(for_type)
    if not sorting:
        return None
    if key and key in json_data['sorting'][for_type]:
        return json_data['sorting'][for_type][key]
    else:
        return json_data['sorting'][for_type]


def set_sort(for_type, sort_by, direction, period):
    json_data = get_stored_json()
    sorting = json_data['sorting'].get(for_type)
    if not sorting:
        if for_type in _sorting_defaults:
            json_data['sorting'][for_type] = _sorting_defaults[for_type]
        else:
            return False
    json_data['sorting'][for_type] = {'by': sort_by, 'direction': direction, 'period': period}
    STORAGE.save(json_data)
    return True


def get_default_quality(content_type, target_id):
    json_data = get_stored_json()
    if content_type not in json_data['qualities']:
        json_data['qualities'][content_type] = []
    if any(str(target_id) in item for item in json_data['qualities'][content_type]):
        return next(item for item in json_data['qualities'][content_type] if str(target_id) in item)
    else:
        return None


def add_default_quality(content_type, target_id, name, quality):
    json_data = get_stored_json()
    current_quality = get_default_quality(content_type, target_id)
    if current_quality:
        current_quality = current_quality[target_id]['quality']
        if current_quality.lower() == quality.lower():
            return False
        else:
            index = next(index for index, item in enumerate(json_data['qualities'][content_type]) if str(target_id) in item)
            del json_data['qualities'][content_type][index]
    json_data['qualities'][content_type].append({target_id: {'name': name, 'quality': quality}})
    STORAGE.save(json_data)
    return True


def remove_default_quality(content_type):
    json_data = get_stored_json()
    result = kodi.Dialog().select(i18n('remove_default_quality') % content_type,
                                  ['%s [%s]' % (user[user.keys()[0]]['name'], user[user.keys()[0]]['quality']) for user in json_data['qualities'][content_type]])
    if result == -1:
        return None
    else:
        result = json_data['qualities'][content_type].pop(result)
        STORAGE.save(json_data)
        return result


def clear_list(list_type, list_name):
    json_data = get_stored_json()
    if (list_name in json_data) and (list_type in json_data[list_name]):
        json_data[list_name][list_type] = []
        STORAGE.save(json_data)
        return True
    else:
        return False


class BlacklistFilter(object):
    def by_type(self, results, result_key, parent_keys=None,
                id_key=None, game_key=None, list_type='user'):
        if (id_key is None) and (game_key is None): return
        # list_type = user, game, community
        filtered_results = {result_key: list()}
        for result in results[result_key]:
            identification = None
            id_parent = result
            key = id_key if id_key else game_key
            if parent_keys is None:
                identification = id_parent[key]
            else:
                for parent_key in parent_keys:
                    id_parent = id_parent[parent_key]
                    identification = id_parent[key]
            if game_key and identification:
                identification = identification if identification else ''
            if identification:
                if not is_blacklisted(identification, list_type=list_type):
                    filtered_results[result_key].append(result)
        return filtered_results


class TitleBuilder(object):
    class Templates(object):
        TITLE = u"{title}"
        STREAMER = u"{streamer}"
        STREAMER_TITLE = u"{streamer} - {title}"
        VIEWERS_STREAMER_TITLE = u"{viewers} - {streamer} - {title}"
        STREAMER_GAME_TITLE = u"{streamer} - {game} - {title}"
        GAME_VIEWERS_STREAMER_TITLE = u"[{game}] {viewers} | {streamer} - {title}"
        BROADCASTER_LANGUAGE_STREAMER_TITLE = u"{broadcaster_language} | {streamer} - {title}"
        ELLIPSIS = u'...'

    def __init__(self, line_length):
        self.line_length = line_length

    def format_title(self, title_values):
        title_setting = int(kodi.get_setting('title_display'))
        template = self.get_title_template(title_setting)

        for key, value in title_values.iteritems():
            title_values[key] = self.clean_title_value(value)
        title = template.format(**title_values)

        return self.truncate_title(title)

    @staticmethod
    def get_title_template(title_setting):
        options = {0: TitleBuilder.Templates.STREAMER_TITLE,
                   1: TitleBuilder.Templates.VIEWERS_STREAMER_TITLE,
                   2: TitleBuilder.Templates.TITLE,
                   3: TitleBuilder.Templates.STREAMER,
                   4: TitleBuilder.Templates.STREAMER_GAME_TITLE,
                   5: TitleBuilder.Templates.GAME_VIEWERS_STREAMER_TITLE,
                   6: TitleBuilder.Templates.BROADCASTER_LANGUAGE_STREAMER_TITLE}
        return options.get(title_setting, TitleBuilder.Templates.STREAMER)

    @staticmethod
    def clean_title_value(value):
        if isinstance(value, basestring):
            return unicode(value).replace('\r\n', ' ').strip()
        else:
            return value

    def truncate_title(self, title):
        truncate_setting = kodi.get_setting('title_truncate') == 'true'

        if truncate_setting:
            short_title = title[:self.line_length]
            ending = (title[self.line_length:] and TitleBuilder.Templates.ELLIPSIS)
            return short_title + ending
        return title
