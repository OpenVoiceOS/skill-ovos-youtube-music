#!/usr/bin/env python3
from os import walk, path
from os.path import dirname, join

from setuptools import setup

URL = "https://github.com/OpenVoiceOS/skill-ovos-youtube-music"
SKILL_CLAZZ = "YoutubeMusicSkill"  # needs to match __init__.py class name
PYPI_NAME = "ovos-skill-youtube-music"  # pip install PYPI_NAME

# below derived from github url to ensure standard skill_id
SKILL_AUTHOR, SKILL_NAME = URL.split(".com/")[-1].split("/")
SKILL_PKG = SKILL_NAME.lower().replace('-', '_')
PLUGIN_ENTRY_POINT = f'{SKILL_NAME.lower()}.{SKILL_AUTHOR.lower()}={SKILL_PKG}:{SKILL_CLAZZ}'


# skill_id=package_name:SkillClass

def find_resource_files():
    # add any folder with files your skill uses here! 
    resource_base_dirs = ("locale", "res", "vocab", "dialog", "regex", "skill")
    base_dir = path.dirname(__file__)
    package_data = ["*.json"]
    for res in resource_base_dirs:
        if path.isdir(path.join(base_dir, res)):
            for (directory, _, files) in walk(path.join(base_dir, res)):
                if files:
                    package_data.append(
                        path.join(directory.replace(base_dir, "").lstrip('/'),
                                  '*'))
    return package_data


def get_version():
    """ Find the version of this skill"""
    version_file = join(dirname(__file__), 'version.py')
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if int(alpha):
        version += f"a{alpha}"
    return version


setup(
    name=PYPI_NAME,
    version=get_version(),
    url=URL,
    package_dir={SKILL_PKG: ""},
    package_data={SKILL_PKG: find_resource_files()},
    packages=[SKILL_PKG],
    description='ovos common play youtube music skill plugin',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    include_package_data=True,
    install_requires=["ovos-plugin-manager>=0.0.1a3",
                      "tutubo",
                      "ovos_workshop~=0.0,>=0.0.5"],
    keywords='ovos skill plugin',
    entry_points={'ovos.plugin.skill': PLUGIN_ENTRY_POINT}
)
