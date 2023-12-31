#
# SPDX-FileCopyrightText: 2023 Carnegie Mellon University
# SPDX-License-Identifier: GPL-2.0-only
#
# Authentication helper for OpenAFS appliance
#
# Provides a web-based workflow for creating new local Samba accounts with
# authentication against a Kerberos realm with the goal to let a Samba daemon
# process obtain AFS and Coda authentication tokens for read/write user access
# to afs and coda shares.
#

import json
import pwd
import re
import secrets
import subprocess
import tempfile
from pathlib import Path
from shutil import which
from typing import Dict, Tuple

from flask import Flask, flash, redirect, render_template, request, url_for

SMBPASSWD = which("smbpasswd")
KINIT = which("kinit")
CLOG = which("clog")

USER_BLOCKLIST = ("root",)  # example as root will be blocked because of uid
REALM_WHITELIST = ()
REALM_BLOCKLIST = ()


app = Flask(__name__)
app.config.from_mapping(CODA_ENABLED=CLOG is not None)

SECRET_PATH = Path(".webauth_secret")
if not SECRET_PATH.exists():
    SECRET_PATH.write_text(secrets.token_hex())
app.secret_key = SECRET_PATH.read_text()


def validate_username_field(username_field: str) -> Tuple[str, str]:
    """Wrapper around validate_username to check username fields in submitted forms."""
    username = request.form[username_field]
    auth = username_field.split("_", 1)[0].capitalize()
    return validate_username(username, auth)


def validate_username(username: str, auth: str = "local") -> Tuple[str, str]:
    """Check if the username is correctly formatted, not on a blocked username list
    and not associated with a local system account.

    Also splits off the optional @REALM and checks that the realm looks reasonable.

    Returns the username and realm after they pass validation.

    Raises:
    - ValueError for incorrectly formatted or blocked user or realm names.
    """
    # Really what we want to make sure is that someone can't try to inject
    # any characters that would allow them to add/modify kinit arguments or
    # authenticate against a some other realm which could block the user with
    # the same username in the local realm from authenticating.
    #
    # rules for domain names (realms) really are far more complicated possibly
    # having to pass it through an IDN library to handle unicode and all that.
    username_realm_regex = re.compile(
        r"""
       ^([a-z][a-z0-9-_]*)    # the username
        (@                    # the optional @realm
          (?:                   # one or more domain parts
            [a-zA-Z0-9]         # cannot start with '-'
            (?:                 # 1-63 alphanumeric+'-' characters
              [a-zA-Z0-9-]{0,61}
              [a-zA-Z0-9]         # cannot end with '-'
            )?
            \.                  # parts are separated by '.'
          )+
          (?:                   # last part has optional '.' at end
            [a-zA-Z0-9]         # cannot start with '-'
            [a-zA-Z0-9-]{0,61}  # 2?-63 characters (no single character TLDs?)
            [a-zA-Z0-9]         # cannot end with '-'
            \.?                 # fqdn names may end with a period
          )
        )?$
    """,
        re.VERBOSE | re.ASCII,
    )
    match = username_realm_regex.match(username)
    if match is None:
        raise ValueError(f"Invalid {auth} username")

    username, realm = match.groups()

    # local (samba) username should not have a realm part
    if auth == "local" and realm is not None:
        raise ValueError("Invalid username")

    # Check that the username is not in the block list
    #
    # not _really_ necessary for root since we won't override the smbpasswd
    # for already existing local users, but this avoids an unnecessary step
    # where we check password validity with kerberos.
    if username in USER_BLOCKLIST:
        raise ValueError(f"{auth} username blocked by administrator")

    # Check that the username is not associated with one of the system accounts
    try:
        user = pwd.getpwnam(username)
        if auth == "local" and user.pw_uid < 1000:
            raise ValueError("Cannot use a reserved username")
    except KeyError:
        pass

    if realm is None:
        return username, ""

    # I _think_ the regex should have caught these already
    if "." not in realm:
        raise ValueError(f"Invalid {auth} realm")

    if REALM_WHITELIST and realm[1:] not in REALM_WHITELIST:
        raise ValueError(f"{auth} realm not authorized by administrator")

    # Check that the realm is not in the block list
    if REALM_BLOCKLIST and realm[1:] in REALM_BLOCKLIST:
        raise ValueError(f"{auth} realm blocked by administrator")

    return username, realm


def validate_password(password_field: str) -> str:
    password = request.form[password_field]

    # Check that all characters in the password are 'printable'
    #
    # examples of non-printable characters are carriage return and line feed,
    # and things like the null character (end of string in C) etc.
    if not password.isprintable():
        auth = password_field.split("_", 1)[0].capitalize()
        raise ValueError(f"Invalid {auth} password")

    return password


def load_settings(username: str) -> Dict[str, str]:
    # check if username exists as local user and load previously used
    # authentication settings
    try:
        user = pwd.getpwnam(username)
        home = Path(user.pw_dir)
        config = json.loads(home.joinpath(".webauth.conf").read_text())
    except (KeyError, FileNotFoundError, ValueError):
        config = dict(new_user=True, krb5_user=username, coda_user=username)

    config["coda_enabled"] = app.config["CODA_ENABLED"]
    return config


def save_settings(username: str, config: Dict[str, str]) -> None:
    user = pwd.getpwnam(username)
    config_path = Path(user.pw_dir).joinpath(".webauth.conf")
    config_json = json.dumps(config)
    config_path.write_text(config_json)


def check_krb5_credentials(krb5_username: str, krb5_password: str) -> None:
    assert KINIT is not None
    with tempfile.NamedTemporaryFile() as cctemp:
        try:
            subprocess.run(
                [KINIT, "-c", f"FILE:{cctemp.name}", krb5_username],
                input=f"{krb5_password}\n",
                encoding="utf-8",
                check=True,
            )
        except subprocess.CalledProcessError:
            raise ValueError("Username or password incorrect")
    flash(f"Successfully authenticated {krb5_username}")


def get_or_create_local_user(
    samba_username: str, samba_password: str, new_user: bool
) -> None:
    assert SMBPASSWD is not None
    # check if username already exists
    try:
        pwd.getpwnam(samba_username)

        # !!! we have to make sure we're not racing with another user
        # creating the same local account !!!
        if new_user:
            raise ValueError("User already exists, try again")

        # user exists, update the password...
        if samba_password:
            try:
                subprocess.run(
                    [SMBPASSWD, samba_username],
                    input=f"{samba_password}\n{samba_password}\n",
                    encoding="utf-8",
                    check=True,
                )
            except subprocess.CalledProcessError:
                raise ValueError("Failed to change local password")

            flash(f"Updated Local SMB password for {samba_username}")
        return
    except KeyError:
        pass

    # create new user
    try:
        subprocess.run(
            [SMBPASSWD, "-a", samba_username],
            input=f"{samba_password}\n{samba_password}\n",
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError:
        raise ValueError("Failed to create local account")

    flash(f"Created Local SMB user {samba_username}")


def do_krb5_login(samba_username: str, krb5_username: str, krb5_password: str) -> None:
    assert KINIT is not None
    try:
        subprocess.run(
            [
                "su",
                "-s",
                "/bin/sh",
                "-c",
                KINIT,
                "--login",
                samba_username,
                krb5_username,
            ],
            input=f"{krb5_password}\n",
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError:
        raise ValueError("Failed to obtain Kerberos credentials")

    flash(f"Obtained Kerberos credentials for {krb5_username}")


def do_coda_login(samba_username: str, coda_username: str, coda_password: str) -> None:
    if not app.config["CODA_ENABLED"] or not coda_password:
        return

    assert CLOG is not None
    try:
        subprocess.run(
            [
                "/bin/su",
                "-s",
                "/bin/sh",
                "-c",
                CLOG,
                "--login",
                samba_username,
                f"{coda_username}",
            ],
            input=f"{coda_password}\n",
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError:
        raise ValueError("Failed to obtain Coda credentials")

    flash(f"Obtained Coda tokens for {coda_username}")


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            # local username shouldn't contain a realm, make sure we call
            # validate_username(...) and not validate_username_field(...)
            username = request.form["username"]
            validate_username(username)
            return redirect(url_for("login", username=username))
        except ValueError as exc:
            flash(exc.args[0])

    return render_template("index.html")


@app.route("/l/<username>", methods=["GET", "POST"])
def login(username):
    try:
        validate_username(username)
        config = load_settings(username)
    except ValueError as exc:
        flash(exc.args[0])
        return redirect(url_for("index"))

    if request.method == "POST":
        # initial form field validation
        try:
            new_user = "new_user" in config
            if new_user:
                # because we use the kerberos credentials to identify the user,
                # these should not change after the local account is created.
                user, realm = validate_username_field("krb5_username")
                krb5_user = f"{user}{realm.upper()}"
            else:
                krb5_user = config["krb5_user"]

            krb5_pass = validate_password("krb5_password")
            samba_pass = validate_password("samba_password")

            # there is a lot going on here...

            # - authenticate with krb5 KDC to validate the user's account
            check_krb5_credentials(krb5_user, krb5_pass)

            # - create new local/Samba user if local user does not exist
            # - update Samba password if user already exists
            if new_user and not samba_pass:
                flash("Using your Kerberos password for SMB authentication")
                samba_pass = krb5_pass

            get_or_create_local_user(username, samba_pass, new_user)

            # - create kerberos credential cache for the local user
            do_krb5_login(username, krb5_user, krb5_pass)

            # - obtain Coda tokens for the local user
            if "coda_username" in request.form:
                user, realm = validate_username_field("coda_username")
                coda_user = f"{user}{realm.lower()}"
                coda_pass = validate_password("coda_password")
                do_coda_login(username, coda_user, coda_pass)
            else:
                coda_user = ""

            # - save webauth config
            save_settings(username, dict(krb5_user=krb5_user, coda_user=coda_user))

            return redirect(url_for("success", username=username))
        except ValueError as exc:
            flash(exc.args[0])

    return render_template("login.html", username=username, config=config)


@app.route("/a/<username>", methods=["GET"])
def success(username):
    try:
        validate_username(username)
        config = load_settings(username)
    except ValueError as exc:
        flash(exc.args[0])
        return redirect(url_for("index"))

    return render_template("success.html", username=username, config=config)
