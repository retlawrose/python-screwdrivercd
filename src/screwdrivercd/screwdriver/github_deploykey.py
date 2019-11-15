# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache 2.0 license.  See the LICENSE file in the project root for terms
"""
Screwdriver github deploy key setup utility
"""
import base64
import logging
import os
import shutil
import subprocess  # nosec
import sys
import tempfile
from urllib.parse import urlparse

from ..installdeps.cli import main as installdeps_main
from ..utility.contextmanagers import InTemporaryDirectory


logger = logging.getLogger(__name__)


fingerprints = {
    'old github fingerprint': b'16:27:ac:a5:76:28:2d:36:63:1b:56:4d:eb:df:a6:48',     # Old github fingerprint, For openssh < 7.4
    'new github_fingerprint': b'SHA256:nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8',  # New github fingerprint for openssh >= 7.4
}


ssh_agent_deploy_conf = """
[build-system]
# Minimum requirements for the build system to execute.
requires = ["setuptools", "wheel"]  # PEP 508 specifications.

[tool.sdv4_installdeps]
    install = ['apk', 'apt-get', 'yum']

[tool.sdv4_installdeps.apk]
    deps = ['openssh-client']

[tool.sdv4_installdeps.apt-get]
    deps = ['openssh-client']

[tool.sdv4_installdeps.yum]
    deps = ['openssh-clients']
"""


def git_key_secret() -> str:
    git_key = os.environ.get('GIT_KEY', None)
    if not git_key:  # Nothing to do
        return ''

    git_key_decoded = base64.b64decode(git_key)
    return git_key_decoded


def add_github_to_known_hosts(known_hosts_filename: str = '~/.ssh/known-hosts'):
    """
    Add the github hosts to the known hosts

    Parameters
    ----------
    known_hosts_filename: str, optional
        The known_hosts file to update
    """
    known_hosts_filename = os.path.expanduser(known_hosts_filename)
    known_hosts_dirname = os.path.dirname(known_hosts_filename)
    os.makedirs(os.path.expanduser(known_hosts_dirname), exist_ok=True, mode=0o700)
    github_hosts = subprocess.check_output(['ssh-keyscan', '-H', 'github.com'])  # nosec
    with open(known_hosts_filename, 'ab') as fh:
        os.fchmod(fh.fileno(), 0o0600)
        fh.write(b'\n')
        fh.write(github_hosts)


def validate_known_good_hosts(known_hosts_filename: str = '~/.ssh/known-hosts') -> bool:
    """
    Check the known hosts for the github hosts

    Returns
    -------
    bool
        True if at least one good host is present, False otherwise
    """
    known_hosts_filename = os.path.expanduser(known_hosts_filename)

    match = False
    output = subprocess.check_output(['ssh-keygen', '-l', '-f', known_hosts_filename])  # nosec
    for desc, fingerprint in fingerprints.items():
        if fingerprint not in output:
            logger.debug(f'Known github fingerprint {desc} is missing from known-hossts', file=sys.stderr)
            continue
        match = True
    return match


def load_github_key(git_key):
    """
    Load the github key into the ssh-agent
    """
    with tempfile.TemporaryDirectory() as tempdir:
        key_filename = os.path.join(tempdir, 'git_key')
        with open(key_filename, 'w') as fh:
            os.fchmod(fh.fileno(), 0o0600)
            fh.write(git_key)
        subprocess.check_call(['ssh-add', key_filename])  # nosec


def set_git_mail_config():
    """
    Set the git mail config variables
    """
    subprocess.check_call(['git', 'config', '--global', 'user.email', "dev-null@screwdriver.cd"])  # nosec
    subprocess.check_call(['git', 'config', '--global', 'user.name', "sd-buildbot"])  # nosec


def update_git_remote():
    """
    Update the git remote address to use the git protocol via ssh
    """
    new_git_url = None
    remote_output = subprocess.check_output(['git', 'remote', '-v'])  # nosec
    for line in remote_output.split(b'\n'):
        line = line.strip()
        remote, old_git_url, remote_type = line.split()
        if remote != b'origin':
            continue
        if remote_type != b'(push)':
            continue
        if 'http' not in old_git_url:
            continue
        parsed_url = urlparse(old_git_url)
        new_git_url = f'git@{parsed_url.netloc}:{parsed_url.path.lstrip("/")}'
        break
    if new_git_url:
        subprocess.check_call(['git', 'remote', 'set-url', '--push', 'origin', new_git_url])  # nosec


def install_ssh_agent():
    """
    Install ssh-agent if it is missing
    """
    if shutil.which('ssh-agent'):  # Already installed
        return

    with InTemporaryDirectory():
        with open('pyproject.toml', 'w') as fh:
            fh.write(ssh_agent_deploy_conf)
            installdeps_main()


def setup_ssh_main() -> int:  # pragma: no cover
    """
    Github deploykey ssh setup, setup ssh eiddcchttjfenrtetcgbiglgcgfureejrluufcbjbngj
    so that ssh-agent can be startedx.

    Returns
    -------
    int:
        The returncode to be returned from the utility
    """
    git_key = git_key_secret()
    if not git_key:  # Nothing to do
        print('No GIT_KEY secret present')
        return 0

    logger.debug('Installing ssh clients if it is not installed')
    install_ssh_agent()

    logger.debug('Adding github.com to known_hosts')
    add_github_to_known_hosts()

    logger.debug('Validating known good hosts')
    validate_known_good_hosts()

    return 0


def add_deploykey_main() -> int:  # pragma: no cover
    """
    Github deploykey setup utility, this utility adds the keys from the screwdriver secrets into the ssh-agent.

    This tool requires that ssh-agent be running already.

    Returns
    -------
    int:
        The returncode to be returned from the utility
    """
    git_key = git_key_secret()
    if not git_key:  # Nothing to do
        return 0

    logger.debug('Loading the github key into the ssh-agent')
    load_github_key(git_key)

    logger.debug('Setting the git user.email and user.name config settings')
    set_git_mail_config()

    logger.debug('Updating the git remote to use the ssh url')
    update_git_remote()

    return 0
