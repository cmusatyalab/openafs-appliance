import pwd
import re
import subprocess
import tempfile
from typing import Optional

from flask import Flask, request, render_template

app = Flask(__name__)

USER_BLOCKLIST = (
    "root",
)


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
            [
                kinit,
                "--password-file=STDIN",
                "-c",
                f"FILE:{ccache}",
                username,
            ],
            input=f"{password}\n",
            encoding="utf-8",
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def do_login(username: str, password: str) -> Optional[str]:
    with tempfile.NamedTemporaryFile() as cctemp:
        # check if we can authenticate this user with the kerberos realm
        # kinit? user/password, save credentials...
        if not check_credentials(username, password, cctemp.name):
            return "Username or password incorrect"

        # check if username already exists as local user
        try:
            user = pwd.getpwnam(username)
        except KeyError:
            # not already a local_user, use smbpasswd to create a local user
            try:
                subprocess.run([smbpasswd, "-a", username], input=f"{password}\n", check=True)
                user = pwd.getpwnam(username)
            except (subprocess.CalledProcessError, KeyError):
                return f"Failed to add local user {username}"
        
        # Move saved credentials to user's krbccache
        cc_path = Path("/tmp", f"krb5cc_{user.pw_uid}")
        cc_temp = Path(cctemp.name)
        cc_temp.chmod(0o600)
        os.chown(cc_temp, user.pw_uid, user.pw_gid)
        cc = cc_temp.replace(cc_path)
            
    return None

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        error = do_login(username, password):
        if error is None:
            return render_template("login_success.html", username=username)
    else:
        error = ""

    return render_template("login.html", error=error)
