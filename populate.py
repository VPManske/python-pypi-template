#!/usr/bin/env python

import fnmatch
import os
import re
import sys
import textwrap
from datetime import date
from string import capwords
from subprocess import check_output
from os.path import abspath, dirname, join

try:
    from ConfigParser import SafeConfigParser as ConfigParser
except ImportError:
    try:
        from configparser import SafeConfigParser as ConfigParser
    except ImportError:
        from configparser import ConfigParser
        assert ConfigParser  # silence pyflakes


this_dir = dirname(abspath(__file__))


if sys.version_info < (3, 0):
    def items(x):
        return x.iteritems()
else:
    def items(x):
        return x.items()


def find_templated_files():
    for root, dirnames, filenames in os.walk(this_dir):
        for f in fnmatch.filter(filenames, '*.template'):
            yield join(root, f)


def find_templated_directories():
    for root, dirnames, filenames in os.walk(this_dir):
        for d in fnmatch.filter(dirnames, '{{ * }}'):
            yield join(root, d)


def git(*args):
    return check_output(('git',) + tuple(args)).strip()


def read_requirements(requirements_file_basename):
    with open(join(this_dir, requirements_file_basename)) as f:
        content = f.read()

    for line in content.splitlines():
        line = re.sub('#.*', '', line).strip()
        if line:
            yield line


def get_author_email():
    return git('config', 'user.email')


def get_author_name():
    return git('config', 'user.name')


def get_copyright_years():
    return str(date.today().year)


def get_github_info():
    result = re.search(
        'github.com[:/](?P<user>[^/]+)/(?P<repo>.+)[.]git',
        git('config', '--get', 'remote.origin.url'))

    if not result:
        raise RuntimeError(
            'Failed to find a GitHub user and/or repository name in the '
            'output of "git config --get remote.origin.url".')

    return result.group('user'), result.group('repo')


def get_install_requires():
    return tuple(read_requirements('requirements_install.txt'))


def get_tests_require():
    return tuple(read_requirements('requirements_test.txt'))


def get_populate_ini_settings():
    config = ConfigParser()
    config.readfp(open(join(this_dir, 'populate.ini')))
    values = dict(
        package_name=config.get('global', 'package_name'),
        package_version=config.get('global', 'package_version'),
        short_description=config.get('global', 'short_description'))

    empty_values = [k for k, v in items(values) if not v]

    if empty_values:
        raise RuntimeError(
            'Please specify values in "populate.ini" for the following: '
            '{empty}'.format(empty=empty_values))

    return values


def get_template_values():
    user, repo = get_github_info()

    values = dict(
        author_email=get_author_email(),
        author_name=get_author_name(),
        copyright_years=get_copyright_years(),
        github_user=user,
        repo_name=repo,
        install_requires=get_install_requires(),
        tests_require=get_tests_require())

    values.update(get_populate_ini_settings())

    return values


def replace_multiline(text, key, value, filter_name, replacement_fn):
    token = re.escape('{{{{ {k}|{f} }}}}'.format(k=key, f=filter_name))
    regex = re.compile('(?P<indent>[ \t]*){token}'.format(token=token))

    while True:
        match = regex.search(text)

        if not match:
            break

        indent = match.group('indent')
        replacement = replacement_fn(indent=indent, value=value)
        text = regex.sub(replacement, text, count=1)

    return text


def replace_pystrings(text, key, value):
    return replace_multiline(
        text=text, key=key, value=value,
        filter_name='pystring',
        replacement_fn=lambda indent, value: indent + ('\n' + indent).join(
            map(repr, textwrap.wrap(value, width=70 - len(indent)))))


def replace_pytuples(text, key, value):
    text = replace_multiline(
        text=text, key=key, value=value,
        filter_name='pytuple',
        replacement_fn=lambda indent, value: '\n'.join(
            map(lambda value: indent + repr(value) + ',', value)))

    # squash empty tuples
    text = re.sub('[(]\s+[)]', '()', text)

    return text


def replace_raw(text, key, value):
    return text.replace('{{{{ {k} }}}}'.format(k=key), value)


def replace_capitalize(text, key, value):
    return text.replace(
        '{{{{ {k}|capitalize }}}}'.format(k=key), capwords(value))


def do_replacements(text, key, value, fns):
    for fn in fns:
        text = fn(text=text, key=key, value=value)
    return text


def populate_files(template_values):
    for template_path in find_templated_files():
        with open(template_path) as f:
            content = f.read()

        for k, v in items(template_values):
            if isinstance(v, basestring):
                fns = replace_raw, replace_capitalize, replace_pystrings
            else:
                fns = replace_pytuples,

            content = do_replacements(text=content, key=k, value=v, fns=fns)

        with open(template_path, 'wb') as f:
            f.write(content)


def populate_directories(template_values):
    for template_dir in find_templated_directories():

        for k, v in items(template_values):
            renamed_dir = template_dir.replace('{{{{ {k} }}}}'.format(k=k), v)

            if renamed_dir != template_dir:
                os.rename(template_dir, renamed_dir)


def main():
    template_values = get_template_values()
    populate_files(template_values)
    populate_directories(template_values)


if __name__ == '__main__':
    main()