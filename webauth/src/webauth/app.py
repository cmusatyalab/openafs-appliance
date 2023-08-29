import pwd
import re

from flask import Flask, request, render_template

app = Flask(__name__)

USER_BLOCKLIST = (
    "root",
)


def do_login(username: str, password: str) -> bool:
    # Check if the username is correctly formatted
    if re.match("^[a-z][-a-z0-9_]*$", username) is None:
        return False

    # Check that the username is not in the block list
    #
    # not really necessary for root since we never override the smbpasswd for
    # already existing users.
    if username in USER_BLOCKLIST:
        return False

    # check if we can authenticate this user against our kerberos realm
    # kinit? user/password, save credentials...
    if not auth_user:
        return False

    # check if username already exists as local user
    try:
        pwd.getpwnam(username)
    except KeyError:
        # not already a local_user
        # smbpasswd -a user
        pass

    # run kinit as user and/or copy saved credentials to user krbccache
    # su -s /bin/sh -c "kinit user" - user 
    return True


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if do_login(username, password):
            return render_template("login_success.html", username=username)
    else:
        error = "Invalid username/password"

    return render_template("login.html", error=error)
