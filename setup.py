#!/usr/bin/env python3
from setuptools import setup

# skill_id=package_name:SkillClass
PLUGIN_ENTRY_POINT = 'skill-youtube-music.jarbasai=skill_youtube_music:YoutubeMusicSkill'

setup(
    # this is the package name that goes on pip
    name='skill-youtube-music',
    version='0.0.1',
    description='ovos common play youtube music skill plugin',
    url='https://github.com/JarbasSkills/skill-youtube-music',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    package_dir={"skill_youtube_music": ""},
    package_data={'skill_youtube_music': ['locale/*', 'ui/*']},
    packages=['skill_youtube_music'],
    include_package_data=True,
    install_requires=["ovos-plugin-manager>=0.0.1a3",
                      "tutubo",
                      "ovos_workshop~=0.0,>=0.0.5"],
    keywords='ovos skill plugin',
    entry_points={'ovos.plugin.skill': PLUGIN_ENTRY_POINT}
)
