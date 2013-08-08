import pkgconfig
from setuptools import setup

VERSION='0.0.1'

REQUIRED_UFO='>=0.5'

if not pkgconfig.installed('ufo', REQUIRED_UFO):
    print("You need at least ufo-core {0}. The installed scripts "
          "might not work as expected.\n".format(REQUIRED_UFO))

setup(
    name='ufo-scripts',
    version=VERSION,
    author='Matthias Vogelgesang',
    author_email='matthias.vogelgesang@kit.edu',
    url='http://ufo.kit.edu',
    scripts=['bin/ufo-reconstruct',
             'bin/ufo-ffc-sinos',
             'bin/ufo-estimate-center',
             ],
    long_description=open('README.md').read(),
)