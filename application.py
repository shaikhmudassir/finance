import os


from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get symbol, name, shares, price from details table
    rows = db.execute("SELECT symbol, name, shares, price FROM details WHERE user_id = :user_id ",
                      user_id=session["user_id"])

    # Get cash available in users account
    cash = db.execute("SELECT cash FROM users WHERE id = :id",
                      id=session["user_id"])

    # Delete the row, if no shares
    delete = db.execute("DELETE from details WHERE user_id = :user_id AND shares = :shares",
                        user_id=session["user_id"],
                        shares=0)

    # Redirect to self if delete any
    if delete == 1:
        return redirect("/")

    # If any stock is bought then get total amount with cash
    total = cash[0]["cash"]
    if len(rows) != 0:
        for row in rows:
            row["total"] = usd(row["price"] * row["shares"])
            total += row["price"] * row["shares"]

    # convert into USD
    cash = usd(cash[0]["cash"])
    total = usd(total)

    return render_template("index.html", rows=rows, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Get the cash from user's account
        cash = db.execute("SELECT cash FROM users WHERE id = :id",
                          id=session["user_id"])

        stock = lookup(symbol)

        # Check for invalid Symbol
        if lookup(symbol) == None:
            return apology("Missing shares")

        # Compare cash with no. of share price
        elif (stock["price"] * int(shares)) > cash[0]["cash"]:
            return apology("Can't Afford ")

        # Update the cash in user's table
        cash = cash[0]["cash"] - stock["price"] * int(shares)
        db.execute("UPDATE users SET cash = :cash WHERE id = :id",
                   cash=cash,
                   id=session["user_id"])

        # Insert details into History table
        db.execute("INSERT INTO history (user_id, symbol, shares, price, datetime) VALUES (:user_id, :symbol, :shares, :price, :datetime)",
                   user_id=session["user_id"],
                   symbol=stock["symbol"],
                   shares=shares,
                   price=stock["price"],
                   datetime=datetime.now())

        # Get the shares from details table to replace existing shares
        rows = db.execute("SELECT shares FROM details WHERE symbol = :symbol AND user_id = :id",
                          symbol=symbol,
                          id=session["user_id"])

        # Update the existing shares
        if len(rows) > 0:
            db.execute("UPDATE details SET shares = :shares WHERE symbol = :symbol AND user_id = :user_id",
                       shares=(rows[0]["shares"] + int(shares)),
                       symbol=symbol,
                       user_id=session["user_id"])
            return redirect("/")

        # Insert details into details table
        db.execute("INSERT INTO details (user_id, symbol, name, shares, price, datetime) VALUES (:user_id, :symbol, :name, :shares, :price, :datetime)",
                   user_id=session["user_id"],
                   symbol=stock["symbol"],
                   name=stock["name"],
                   shares=shares,
                   price=stock["price"],
                   datetime=datetime.now())

        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Get the whole history of perticular user
    rows = db.execute("SELECT * from history WHERE user_id = :user_id ",
                      user_id=session["user_id"])

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    if request.method == "POST":
        symbol = request.form.get("symbol")

        # Check for invalid Symbol
        if lookup(symbol) == None:
            return apology("Invalid Symbol")

        # Get name, price, symbol of stocks
        stock = lookup(symbol)

        # convert price into USD
        stock["price"] = usd(stock["price"])

        # reached to Quoted.html with details
        return render_template("quoted.html", stock=stock)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Check for all required fields
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 403)
        elif not request.form.get("password"):
            return apology("must provide password", 403)
        elif not request.form.get("passwordAgain"):
            return apology("must provide password again", 403)

        # Search for same usernmae
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        username = request.form.get("username")
        password = request.form.get("password")
        passwordAgain = request.form.get("passwordAgain")

        # Check for duplicate user, password length, confirmation
        if len(rows) != 0:
            return apology("Username is already exist", 403)
        elif len(password) < 8:
            return apology("Password must have at least 8 character ", 403)
        elif password != passwordAgain:
            return apology("Password doesn't match", 403)

        # Convert and store password hash.
        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                   username=username, hash=hash)

        # Get the id of current user
        id = db.execute("SELECT id FROM users WHERE username = :username",
                        username=username)

        # Remember which user has logged in
        session["user_id"] = id[0]["id"]
        # Redirect user to home page
        return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("Select the symbol", 403)

        # Get the shares from details table
        rows = db.execute("SELECT shares FROM details WHERE symbol = :symbol AND user_id = :user_id",
                          symbol=symbol,
                          user_id=session["user_id"])

        # Check apology for shares
        if int(shares) < 1:
            return apology("Too few shares", 403)
        elif int(shares) > rows[0]["shares"]:
            return apology("Too many shares", 403)

        # Update the shares after Sold
        db.execute("UPDATE details SET shares = :shares WHERE symbol = :symbol AND user_id = :user_id",
                   shares=rows[0]["shares"] - int(shares),
                   symbol=symbol,
                   user_id=session["user_id"])

        stock = lookup(symbol)

        # Insert details into History table
        db.execute("INSERT INTO history (user_id, symbol, shares, price, datetime, cond) VALUES (:user_id, :symbol, :shares, :price, :datetime, :cond)",
                   user_id=session["user_id"],
                   symbol=stock["symbol"],
                   shares=shares,
                   price=stock["price"],
                   datetime=datetime.now(),
                   cond=1)

        # Get cash from user's account
        cash = db.execute("SELECT cash FROM users WHERE id = :id",
                          id=session["user_id"])

        # Update the cash after sold
        db.execute("UPDATE users SET cash = :cash WHERE id = :id ",
                   cash=cash[0]["cash"] + stock["price"]* int(shares),
                   id=session["user_id"])

        return redirect("/")

    # Pass symbol to sell.html
    rows = db.execute("SELECT symbol, shares FROM details WHERE user_id = :id ",
                      id=session["user_id"])

    return render_template("sell.html", rows=rows)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
