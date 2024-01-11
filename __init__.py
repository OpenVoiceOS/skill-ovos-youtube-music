from os.path import join, dirname

from ovos_utils.ocp import MediaType, PlaybackType
from ovos_utils.parse import fuzzy_match
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill
from ovos_workshop.decorators import ocp_search
from ovos_utils.process_utils import RuntimeRequirements
from ovos_utils import classproperty
from tutubo.ytmus import *


class YoutubeMusicSkill(OVOSCommonPlaybackSkill):
    def __init__(self, *args, **kwargs):
        self.supported_media = [MediaType.MUSIC]
        self.skill_icon = join(dirname(__file__), "ui", "ytmus.png")
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
        if media_type == MediaType.VIDEO:
            base_score += 25

        if self.voc_match(phrase, "youtube"):
            # explicitly requested youtube
            base_score += 50
            phrase = self.remove_voc(phrase, "youtube")

        idx = 0
        for v in search_yt_music(phrase, as_dict=False):
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

                    yield {
                        "match_confidence": score,
                        "media_type": MediaType.MUSIC,
                        "playlist": pl,
                        "playback": PlaybackType.AUDIO,
                        "skill_icon": self.skill_icon,
                        "image": v.thumbnail_url,
                        "bg_image": v.thumbnail_url,
                        "title": title
                    }

            else:
                # videos / songs
                score = self.calc_score(phrase, v, idx,
                                        base_score=base_score,
                                        media_type=media_type)
                # return as a video result (single track dict)
                yield {
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
                idx += 1


def create_skill():
    return YoutubeMusicSkill()
