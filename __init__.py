from os.path import join, dirname

from json_database import JsonStorageXDG
from ovos_bus_client.message import Message
from ovos_utils import classproperty, timed_lru_cache
from ovos_utils.log import LOG
from ovos_utils.ocp import MediaType, PlaybackType
from ovos_utils.parse import fuzzy_match
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import ocp_search, ocp_featured_media
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill
from tutubo.ytmus import *


class YoutubeMusicSkill(OVOSCommonPlaybackSkill):
    def __init__(self, *args, **kwargs):
        self.supported_media = [MediaType.MUSIC]
        self.skill_icon = join(dirname(__file__), "res", "ytmus.png")
        self.archive = JsonStorageXDG("Youtube", subfolder="OCP")
        self.playlists = JsonStorageXDG("YoutubePlaylists", subfolder="OCP")
        super().__init__(*args, **kwargs)

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(internet_before_load=True,
                                   network_before_load=True,
                                   gui_before_load=False,
                                   requires_internet=True,
                                   requires_network=True,
                                   requires_gui=False,
                                   no_internet_fallback=False,
                                   no_network_fallback=False,
                                   no_gui_fallback=True)

    def initialize(self):
        self.precache()
        self.add_event(f"{self.skill_id}.precache", self.precache)
        self.bus.emit(Message(f"{self.skill_id}.precache"))

    def precache(self, message: Message = None):
        """cache searches and register some helper OCP keywords
        populates featured_media
        """

        def norm(t):
            return t.split("(")[0].split("[")[0].split("//")[0].replace(",", "-").replace(":", "-").strip()

        artist_names = [v["artist"] for v in self.archive.values()]
        song_names = [norm(v["title"]) for v in self.archive.values()]
        playlist_names = [k for k in self.playlists.keys()]

        if message is not None:
            for query in self.settings.get("featured", ["johnny cash"]):
                for r in self.search_youtube_music(query, MediaType.MUSIC):
                    if "playlist" in r:
                        playlist_names.append(norm(r["title"]))
                        for r in r["playlist"]:
                            song_names.append(norm(r["title"].split("-")[-1]))
                            if r["artist"] and \
                                    "-" not in r["artist"] and \
                                    len(r["artist"].split()) < 5 and \
                                    not any(a.isdigit() for a in r["artist"].split()):
                                artist_names.append(norm(r["artist"]).split("-")[0])
                        continue
                    song_names.append(norm(r["title"].split("-")[-1]))
                    if r["artist"] and \
                            "-" not in r["artist"] and \
                            len(r["artist"].split()) < 5 and \
                            not any(a.isdigit() for a in r["artist"].split()):
                        artist_names.append(norm(r["artist"]).split("-")[0])

        artist_names = list(set([a for a in artist_names if a is not None and a.strip()]))
        song_names = list(set([a for a in song_names if a is not None and a.strip()]))
        playlist_names = list(set([a for a in playlist_names if a is not None and a.strip()]))
        if len(artist_names):
            self.register_ocp_keyword(MediaType.MUSIC, "artist_name", artist_names)
        if len(song_names):
            self.register_ocp_keyword(MediaType.MUSIC, "song_name", song_names)
        if len(playlist_names):
            self.register_ocp_keyword(MediaType.MUSIC, "playlist_name", playlist_names)
        self.register_ocp_keyword(MediaType.MUSIC, "music_streaming_provider", ["youtube music", "youtube"])
        self.register_ocp_keyword(MediaType.MUSIC, "music_genre",
                                  ["indie", "rock", "metal", "pop", "jazz", "ai covers"])
        #self.export_ocp_keywords_csv("youtube.csv")

    @timed_lru_cache(seconds=3600 * 3)
    def search_yt(self, phrase):
        return search_yt_music(phrase, as_dict=False)

    # score
    def calc_score(self, phrase, match, idx=0, base_score=0,
                   media_type=MediaType.GENERIC):
        # idx represents the order from youtube
        score = base_score - idx * 5  # - 5% as we go down the results list

        if isinstance(match, MusicVideo):
            score -= 10  # penalty for video results

        if match.artist:
            score += 80 * fuzzy_match(phrase.lower(), match.artist.lower())
        if match.title:
            score += 80 * fuzzy_match(phrase.lower(), match.title.lower())

        if media_type == MediaType.GENERIC:
            score -= 10
        return min(100, score)

    # common play
    @ocp_search()
    def search_youtube_music(self, phrase, media_type):
        # match the request media_type
        base_score = 0
        if media_type == MediaType.MUSIC:
            base_score += 10

        if self.voc_match(phrase, "youtube"):
            # explicitly requested youtube
            base_score += 50
            phrase = self.remove_voc(phrase, "youtube")

        idx = 0
        for v in self.search_yt(phrase):
            if isinstance(v, MusicPlaylist):
                # albums / artists / playlists
                score = self.calc_score(phrase, v, idx,
                                        base_score=base_score,
                                        media_type=media_type)
                pl = [
                    {
                        "match_confidence": score,
                        "media_type": MediaType.MUSIC,
                        "length": entry.length * 1000 if entry.length else 0,
                        "uri": "youtube//" + entry.watch_url,
                        "playback": PlaybackType.AUDIO,
                        "image": v.thumbnail_url,
                        "bg_image": v.thumbnail_url,
                        "skill_icon": self.skill_icon,
                        "title": entry.title,
                        "album": v.title,
                        "artist": entry.artist,
                        "skill_id": self.skill_id
                    } for entry in v.tracks
                ]
                if pl:
                    if isinstance(v, MusicArtist):
                        title = v.artist + " (Featured Tracks)"
                    elif isinstance(v, MusicAlbum):
                        title = v.title + " (Full Album)"
                    elif isinstance(v, MusicPlaylist):
                        title = v.title + " (Playlist)"
                    else:
                        title = v.title

                    entry = {
                        "match_confidence": score,
                        "media_type": MediaType.MUSIC,
                        "playlist": pl,
                        "playback": PlaybackType.AUDIO,
                        "skill_icon": self.skill_icon,
                        "image": v.thumbnail_url,
                        "bg_image": v.thumbnail_url,
                        "artist": v.artist,
                        "title": title
                    }
                    yield entry
                    self.playlists[entry["title"]] = entry
                    for entry in pl:
                        self.archive[entry["uri"]] = entry

            else:
                # videos / songs
                score = self.calc_score(phrase, v, idx,
                                        base_score=base_score,
                                        media_type=media_type)
                # return as a video result (single track dict)
                entry = {
                    "match_confidence": score,
                    "media_type": MediaType.VIDEO if isinstance(v, MusicVideo) else MediaType.MUSIC,
                    "length": v.length * 1000 if v.length else 0,
                    "uri": "youtube//" + v.watch_url,
                    "playback": PlaybackType.AUDIO,
                    "image": v.thumbnail_url,
                    "bg_image": v.thumbnail_url,
                    "skill_icon": self.skill_icon,
                    "title": v.title,
                    "artist": v.artist,
                    "skill_id": self.skill_id
                }
                yield entry
                idx += 1
                self.archive[entry["uri"]] = entry
        self.archive.store()

    @ocp_featured_media()
    def featured_media(self):
        return [{
            "title": video["title"],
            "image": video["thumbnail"],
            "match_confidence": 80,
            "media_type": MediaType.MUSIC,
            "uri": uri,
            "playback": PlaybackType.AUDIO,
            "skill_icon": self.skill_icon,
            "bg_image": video["thumbnail"],
            "skill_id": self.skill_id
        } for uri, video in self.archive.items()]

    def get_playlist(self, score=50, num_entries=50):
        pl = self.featured_media()[:num_entries]
        return {
            "match_confidence": score,
            "media_type": MediaType.MUSIC,
            "playlist": pl,
            "playback": PlaybackType.AUDIO,
            "skill_icon": self.skill_icon,
            "image": self.skill_icon,
            "title": "YoutubeMusic Featured Media (Playlist)",
            "author": "YoutubeMusic"
        }

    @ocp_search()
    def search_db(self, phrase, media_type=MediaType.GENERIC):
        base_score = 20 if media_type == MediaType.MUSIC else 0
        entities = self.ocp_voc_match(phrase)

        base_score += 30 * len(entities)

        artist = entities.get("artist_name")
        song = entities.get("song_name")
        playlist = entities.get("playlist_name")
        skill = "music_streaming_provider" in entities  # skill matched

        results = []
        if skill:
            base_score += 30

        urls = []
        if song:
            LOG.debug("searching YoutubeMusic songs cache")
            for video in self.archive.values():
                if song.lower() in video["title"].lower():
                    s = base_score + 0.8 * fuzzy_match(song.lower(), video["title"].lower())
                    if artist and (artist.lower() in video["title"].lower() or
                                   artist.lower() in video.get("artist", "").lower()):
                        s += 0.5 * fuzzy_match(artist.lower(), video["title"].lower())
                    video["match_confidence"] = min(100, s)
                    if video["media_type"] != media_type and media_type != MediaType.GENERIC:
                        video["match_confidence"] -= 20
                    results.append(video)
                    urls.append(video["uri"])
        if artist:
            LOG.debug("searching YoutubeMusic artist cache")
            for video in self.archive.values():
                if video["uri"] in urls:
                    continue
                if artist.lower() in video["title"].lower():
                    s = base_score + 0.8 * fuzzy_match(artist.lower(), video["title"].lower())
                    video["match_confidence"] = min(100, s)
                    if video["media_type"] != media_type and media_type != MediaType.GENERIC:
                        video["match_confidence"] -= 20
                    results.append(video)
                    urls.append(video["uri"])

        if playlist:
            LOG.debug("searching YoutubeMusic playlist cache")
            for k, pl in self.playlists.items():
                if playlist.lower() in k.lower():
                    s = base_score + 0.8 * fuzzy_match(k.lower(), playlist.lower())
                    pl["match_confidence"] = min(100, s)
                    results.append(pl)

        if skill:
            results.append(self.get_playlist())

        return sorted(results, key=lambda k: k["match_confidence"], reverse=True)


if __name__ == "__main__":
    from ovos_utils.messagebus import FakeBus

    s = YoutubeMusicSkill(bus=FakeBus(), skill_id="t.fake")

    for r in s.search_db("zz top", MediaType.MUSIC):
        print(r)
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 443000, 'uri': 'youtube//https://music.youtube.com/watch?v=X4jyfV_-WAw', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ Top - 08 Sure Got Cold After The Rain Fell - Rio Grande Mud 1972 mix', 'album': 'Z Z Top (The Blues)', 'artist': 'creepingthrash', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 420000, 'uri': 'youtube//https://music.youtube.com/watch?v=b76kjd5nvMg', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ TOP - Blue Jean Blues', 'album': 'Z Z Top (The Blues)', 'artist': 'Tomi_C', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 211000, 'uri': 'youtube//https://music.youtube.com/watch?v=vMjqgIZ1_YM', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ Top - Jesus Just Left Chicago', 'album': 'Z Z Top (The Blues)', 'artist': 'thenoname365', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 257000, 'uri': 'youtube//https://music.youtube.com/watch?v=Uv4B0xK8rNs', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': "ZZ Top 'A Fool For Your Stockings'", 'album': 'Z Z Top (The Blues)', 'artist': 'wolftrack57', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 206000, 'uri': 'youtube//https://music.youtube.com/watch?v=MCBYpv8MmtY', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ Top - Asleep In The Desert [Instrumental]', 'album': 'Z Z Top (The Blues)', 'artist': 'joeybbbbbz', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 362000, 'uri': 'youtube//https://music.youtube.com/watch?v=0s5Hv4EoBAQ', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ Top - Vincent Price Blues (1996)', 'album': 'Z Z Top (The Blues)', 'artist': 'Rudy Doo', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 335000, 'uri': 'youtube//https://music.youtube.com/watch?v=nPdcuhb-kJY', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Goin So Good - ZZ Top with lyrics', 'album': 'Z Z Top (The Blues)', 'artist': 'yollom600', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 271000, 'uri': 'youtube//https://music.youtube.com/watch?v=MOxMMNyIxCE', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ Top - Over You', 'album': 'Z Z Top (The Blues)', 'artist': 'XxXPLAYERONEXxX', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 315000, 'uri': 'youtube//https://music.youtube.com/watch?v=5OhaJfpu9ic', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ top - Made into a movie', 'album': 'Z Z Top (The Blues)', 'artist': 'MrSP0T', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 379000, 'uri': 'youtube//https://music.youtube.com/watch?v=pGr4NHj92rY', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ Top - I Need You Tonight', 'album': 'Z Z Top (The Blues)', 'artist': 'Metal8909', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 254000, 'uri': 'youtube//https://music.youtube.com/watch?v=j9CAjoBg7Qw', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': "ZZ Top - Just Got Back From Baby's", 'album': 'Z Z Top (The Blues)', 'artist': 'Kilo2199', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 214000, 'uri': 'youtube//https://music.youtube.com/watch?v=oi23gO8u_Uw', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ Top - Old Man', 'album': 'Z Z Top (The Blues)', 'artist': 'Kilo2199', 'skill_id': 't.fake'}
        # {'match_confidence': 90, 'media_type': <MediaType.MUSIC: 2>, 'length': 404000, 'uri': 'youtube//https://music.youtube.com/watch?v=kSHhAkVreiw', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'bg_image': 'https://yt3.ggpht.com/WJUxM-ld-EV397QjrzHHvd4zL3aQc0c702ZdyYJI6EDHDKoZ9cMe0X-yrgbHRkRbLaxQuebzDNo=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'ZZ Top - Breakaway', 'album': 'Z Z Top (The Blues)', 'artist': 'MasaccioGlamour', 'skill_id': 't.fake'}

    for r in s.search_db("frank sinatra ai covers", MediaType.MUSIC):
        print(r)
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 288000, 'uri': 'youtube//https://music.youtube.com/watch?v=SCXZ8_znoE4', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://yt3.ggpht.com/kMnjAFHNa_GkRdMSB0WPOZ_L7bZ3sjTRutYVlmV7BxP6ZuuwJFYRsNSGL0p25alCrG4KX1r20_E=s1200', 'bg_image': 'https://yt3.ggpht.com/kMnjAFHNa_GkRdMSB0WPOZ_L7bZ3sjTRutYVlmV7BxP6ZuuwJFYRsNSGL0p25alCrG4KX1r20_E=s1200', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Pavlo Ilnytskyy – My Way [Live, Frank Sinatra Cover]', 'album': 'Frank Sinatra covers', 'artist': 'Pavlo Ilnytskyy', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 215000, 'uri': 'youtube//https://music.youtube.com/watch?v=_LvrA0fJcI0', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'as the world caves in  - (Frank Sinatra A.I Cover)', 'album': 'Frank Sinatra AI', 'artist': 'the ai man', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 239000, 'uri': 'youtube//https://music.youtube.com/watch?v=9CC_mvhjXE0', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Frank Sinatra Sings Just The Two Of Us ( AI Voice Cover)', 'album': 'Frank Sinatra AI', 'artist': 'PGCFusion', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 189000, 'uri': 'youtube//https://music.youtube.com/watch?v=gauYC0Td7Jk', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Sway by Frank Sinatra (AI Cover)', 'album': 'Frank Sinatra AI', 'artist': 'aidar', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 144000, 'uri': 'youtube//https://music.youtube.com/watch?v=Ikr9mVDMnXM', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': "AI Frank Sinatra - Ain't That A Kick In The Head (Dean Martin Cover)", 'album': 'Frank Sinatra AI', 'artist': 'AI COVERS', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 243000, 'uri': 'youtube//https://music.youtube.com/watch?v=FmIqdyNvYsw', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Feeling Good - Frank Sinatra (Original by Michael Bublé) (AI COVER)', 'album': 'Frank Sinatra AI', 'artist': 'WhoAmI AiCover', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 255000, 'uri': 'youtube//https://music.youtube.com/watch?v=dZGGBT1KEOc', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'AI Frank Sinatra - What A Wonderful World (Louis Armstrong Cover)', 'album': 'Frank Sinatra AI', 'artist': 'AI COVERS', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 265000, 'uri': 'youtube//https://music.youtube.com/watch?v=mbr28MMU9cw', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'a-ha - Take On Me - Frank Sinatra (AI Jazz Cover)', 'album': 'Frank Sinatra AI', 'artist': 'AI Sings', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 238000, 'uri': 'youtube//https://music.youtube.com/watch?v=aU3AWfjCNFc', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Frank Sinatra - Thriller (AI COVER) (IN THE STYLE OF FRANK SINATRA)', 'album': 'Frank Sinatra AI', 'artist': 'JechucamTF2', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 111000, 'uri': 'youtube//https://music.youtube.com/watch?v=pvTvU0Vr9co', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'AI Frank Sinatra - L-O-V-E (Nat King Cole Cover)', 'album': 'Frank Sinatra AI', 'artist': 'AI COVERS', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 222000, 'uri': 'youtube//https://music.youtube.com/watch?v=q6hUd_TVW54', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Frank Sinatra (A.I Cover) - ‘Five Nights at Freddy’s’ (Color Coded Lyrics)', 'album': 'Frank Sinatra AI', 'artist': 'SuperCraft 85', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 236000, 'uri': 'youtube//https://music.youtube.com/watch?v=kvG7xF03tG0', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Feeling Good - Frank Sinatra (AI Cover)', 'album': 'Frank Sinatra AI', 'artist': 'ZaCool27', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 281000, 'uri': 'youtube//https://music.youtube.com/watch?v=62MvAtdIUrw', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Frank Sinatra - Mr. Blue Sky (AI COVER)', 'album': 'Frank Sinatra AI', 'artist': 'Foamy', 'skill_id': 't.fake'}
        # {'match_confidence': 100, 'media_type': <MediaType.MUSIC: 2>, 'length': 362000, 'uri': 'youtube//https://music.youtube.com/watch?v=VNWudHD3Kt8', 'playback': <PlaybackType.AUDIO: 2>, 'image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'bg_image': 'https://i.ytimg.com/vi/_LvrA0fJcI0/hqdefault.jpg?sqp=-oaymwEWCMACELQBIAQqCghQEJADGFogjgJIWg&rs=AMzJL3k-VuOFKLYIlJNi_JDaC2TbjHOaPg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Bohemian Rhapsody - Frank Sinatra (AI COVER) Queen / Marc Martel', 'album': 'Frank Sinatra AI', 'artist': 'breezy', 'skill_id': 't.fake'}
