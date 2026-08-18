import setuptools

import castero

install_requires = [
    'requests',
    'grequests',
    'cjkwrap',
    'pytz',
    'beautifulsoup4',
    'lxml',
    'platformdirs~=4.4.0',
    'python-vlc',
    'python-mpv',
    'windows-curses; platform_system == "Windows"'
]

tests_require = [
    'pytest',
    'coverage',
]

extras_require = {
    'test': tests_require
}


def long_description():
    with open("README.md") as readme:
        return readme.read()


setuptools.setup(
    name=castero.__title__,
    version=castero.__version__,
    description=castero.__description__,
    long_description=long_description(),
    long_description_content_type='text/markdown',
    keywords=castero.__keywords__,
    url=castero.__url__,
    author=castero.__author__,
    author_email=castero.__author_email__,
    license=castero.__license__,
    packages=[
        'castero', 'castero.perspectives', 'castero.players', 'castero.menus'
    ],
    package_data={
        'castero': ['templates/*', 'templates/migrations/*'],
    },
    python_requires='>=3.9',
    install_requires=install_requires,
    tests_require=tests_require,
    extras_require=extras_require,
    entry_points={'console_scripts': ['castero=castero.__main__:main']},
    classifiers=[
        'Intended Audience :: End Users/Desktop',
        'Environment :: Console :: Curses',
        'Operating System :: MacOS',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'License :: OSI Approved :: MIT License',
        'Topic :: Terminals'
    ],
)
