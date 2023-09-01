import os
import pwd
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from flask import Flask, request, render_template


KINIT = "/usr/bin/kinit"
SMBPASSWD = "/usr/bin/smbpasswd"
USER_BLOCKLIST = ("root",)


app = Flask(__name__)


def check_credentials(username: str, password: str, ccache: str) -> bool:
    # Check if the username is correctly formatted
    #
    # really what we want to make sure is that someone can't try to inject
    # any characters that would allow them to add/modify kinit arguments or
    # authenticate against a some other realm which could block the user with
    # the same username in the local realm from authenticating.
    if re.match("^[a-z][-a-z0-9_]*$", username) is None:
        return False

    # Check that the username is not in the block list
    #
    # not _really_ necessary for root since we won't override the smbpasswd
    # for already existing local users, but this avoids an unnuecessary
    # step where we check password validity with kerberos.
    if username in USER_BLOCKLIST:
        return False

    # Check that all characters in the password are 'printable'
    #
    # examples of non-printable characters are carriage return and line feed,
    # and things like the null character (end of string in C) etc.
    if not password.isprintable():
        return False

    try:
        subprocess.run(
            [KINIT, "-c", f"FILE:{ccache}", username],
            input=f"{password}\n",
            encoding="utf-8",
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_or_create_user(username: str, password: str) -> pwd.struct_passwd:
    # check if username already exists as local user
    try:
        return pwd.getpwnam(username)
    except KeyError:
        pass

    # not already a local_user, use smbpasswd to create a local user
    try:
        subprocess.run([SMBPASSWD, "-a", username], input=f"{password}\n", check=True)
    except subprocess.CalledProcessError:
        raise RuntimeError(f"Failed to add local user {username}")

    try:
        return pwd.getpwnam(username)
    except KeyError:
        raise RuntimeError(f"Failed to find new user {username}")


def do_login(username: str, password: str) -> Optional[str]:
    with tempfile.NamedTemporaryFile() as cctemp:
        # check if we can authenticate this user with the kerberos realm
        if not check_credentials(username, password, cctemp.name):
            return "Username or password incorrect"

        # make sure we have a matching local user account
        try:
            user = get_or_create_user(username, password)
        except RuntimeError as exc:
            return exc.args[0]

        # Move saved credentials to user's krb ccache
        #
        # Try to run kinit as the new user first because it probably knows best
        # how to properly handle the credentials cache file.
        try:
            subprocess.run(
                [
                    "su",
                    "-s",
                    "/bin/sh",
                    "-c",
                    KINIT,
                    "--login",
                    username,
                    username,
                ],
                input=f"{password}\n",
                encoding="utf-8",
                check=True,
            )
        except subprocess.CalledProcessError:
            cc_temp = Path(cctemp.name)
            cc_temp.chmod(0o600)
            os.chown(cc_temp, user.pw_uid, user.pw_gid)
            cc_temp.replace(f"/tmp/krb5cc_{user.pw_uid}")
            Path(cctemp.name).write_bytes(b"")
    return None


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        error = do_login(username, password)
        if error is None:
            # return render_template("login_success.html", username=username)
            error = f"Successfully authenticated {username}"
    else:
        error = ""

    return render_template("login.html", error=error)
