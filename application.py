import os
import datetime as dt
import pandas as pd

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

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


portfolio = []


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    stocks, user_total, cash_total, port_total = get_portfolio()

    #user_total = usd(user_total)
    return render_template("index.html", stocks=stocks, usd=usd, user_total=user_total, cash_total=cash_total, port_total=port_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        response = lookup(symbol)
        name = response["name"]
        if response == None:
            return apology("Symbol cannot be found")
        else:
            user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session['user_id'])
            user_cash = user[0]['cash']
            shares = int(request.form.get("shares"))
            price = response['price']
            if user_cash <= shares * price:
                return apology("Too Expensive")
            else:
                user_cash = user_cash - shares * price
                db.execute("""UPDATE users
                                SET cash = :user_cash
                                WHERE id = :user_id""",
                                user_cash=user_cash, user_id=session['user_id'])
                db.execute("""INSERT INTO stocks (symbol, shares, price, user_id, date)
                            VALUES (:symbol, :shares, :price, :user_id, :date)""",
                            symbol=symbol, shares=shares, price=price, user_id=session.get("user_id"), date=dt.datetime.now())

                message = "You bought {} number of shares of {} ({}) stock".format(shares, name, symbol)
                return render_template("info.html", message=message)



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute(
        """SELECT *
            FROM stocks
            WHERE user_id = :session_id""",
            session_id = session['user_id'])

    for row in rows:
        if row['shares'] > 0:
            row['trans'] = "Bought"
        else: row['trans'] = "Sold"
        row['time'] = row['date'].split(" ")[1]
        row['time'] = row['time'].split(":")
        hours = int(row['time'][0])
        m = "AM"
        if hours > 12:
            hours = hours - 12
            m = "PM"
        minutes= row['time'][1]
        row['time'] = "{}:{} {}".format(str(hours), minutes, m)
        row['day'] = row['date'].split(" ")[0]
        row['day'] = dt.datetime.strptime(row['day'], "%Y-%m-%d")
        row['day'] = dt.datetime.strftime(row['day'], "%A, %B %d, %Y")
        row['name'] = lookup(row['symbol'])['name']

        #row['day'] = dt.datetime(row['day'])

    return render_template("history.html", rows=rows, usd=usd)


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
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        response = lookup(symbol)
        if response == None:
            return apology("Can't locate Symbol, Try Again")
        name = response['name']
        price = usd(response['price'])
        message = "A share of {} ({}) costs {} per share.".format(name, symbol, price)
        print(name)
        return render_template("info.html", message=message)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()
    names= []
    #print(db.execute("SELECT username FROM users"))

    if request.method == 'GET':
        return render_template("register.html")
    else:
        username = request.form.get('username')
        if not username:
            return apology("must provide username", 403)
        for user in db.execute("SELECT username FROM users"):
            name = user['username']
            names.append(name)
        if username in names:
            return apology("sorry, this username already exisits", 403)
        password = request.form.get('password')
        if not password:
            return apology("must provide a password", 403)
        confirmation = request.form.get('confirmation')
        if not confirmation:
            return apology("must enter a password again", 403)
        if password != confirmation:
            return apology("passwords must match", 403)

        else:
            hash = generate_password_hash(password)
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)
            session["user_id"] = db.execute("SELECT id FROM users WHERE users.username = username")
            return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    stocks, user_total, user_cash, port_total = get_portfolio()

    if request.method == "GET":
        return render_template("sell.html", stocks=stocks, user_total=user_total, user_cash=user_cash, port_total=port_total)

    else:
        user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session['user_id'])
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        for stock in stocks:
            if stock['symbol'] == symbol:
                user_shares = int(stock['shares'])
        if user_shares < shares:
            flash("You dont enough enough shares")
            return redirect("/sell")
        price = lookup(symbol)['price']
        name = lookup(symbol)['name']
        user_cash = user[0]['cash'] + shares * price
        message = "You sold {} number of shares of {} ({}) stock".format(shares, name, symbol)
        shares = -shares

        db.execute(
            """UPDATE users
                SET cash = :user_cash
                WHERE id = :user_id""",
                user_cash=user_cash, user_id=session['user_id'])
        db.execute(
            """INSERT INTO stocks (symbol, shares, price, user_id, date)
                VALUES (:symbol, :shares, :price, :user_id, :date)""",
                symbol=symbol, shares=shares, price=price, user_id=session.get("user_id"), date=dt.datetime.now())
        return render_template("info.html", message=message)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)

def get_portfolio():
    symbols = []
    stocks = []
    user_total = 0

    # start a cumulative count for the portfolio total
    session_id = session.get("user_id")
    rows = db.execute("""SELECT * FROM stocks WHERE user_id = :session_id""", session_id=session_id)
    user = db.execute("""SELECT * FROM users WHERE id = :session_id""", session_id=session_id)

    for row in rows:
        row['lookup'] = lookup(row['symbol'])
        row['total'] = row['shares'] * row['lookup']['price']
        user_total = user_total + row['total']

        if row['symbol'] not in symbols:
            symbols.append(row['symbol'])
            row['name'] = row['lookup']['name']
            row['shares'] = int(row['shares'])
            stocks.append(row)

        else:
            # iterate through existing stocks and update total
            for stock in stocks:
                if stock['symbol'] == row['symbol']:
                    # adjust existing cells to update totals
                    stock['shares'] = int(stock['shares'] + row['shares'])
                    stock['total'] =  stock['shares'] * row['lookup']['price']

    cash_total = user[0]['cash']
    port_total = cash_total + user_total

    return(stocks, user_total, cash_total, port_total)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
