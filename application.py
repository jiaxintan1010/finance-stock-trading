import os
import logging

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
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


@app.route("/login", methods=["GET", "POST"])
def login():

    # Forget any user_id
    try:
        if session["user_id"]:
            session.clear()
    except:
        pass

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Please provide username.")
            return redirect("/login")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Please provide password.")
            return redirect("/login")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid username/password.")
            return redirect("/login")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to user's home page (portfolio)
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():

    # Forget any user_id
    session.clear()

    # Redirect user to login page
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Validate submission
        if not username:
            flash("Please provide your username.")
            return redirect("/register")

        if not password:
            flash("Please provide your password.")
            return redirect("/register")

        if not confirmation:
            flash("Please confirm your password.")
            return redirect("/register")

        if password != confirmation:
            flash("Password does not match.")
            return redirect("/register")

        if db.execute("SELECT * FROM users WHERE username = ?", username):
            flash("Username already taken.")
            return redirect("/register")

        # Insert new user (username and hashed password) into "users" if they register successfully
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, generate_password_hash(password))

        flash("You have been registered successfully! Login now and start trading.")
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/")
@login_required
def index():

    # Show user's portfolio of stocks
    rows = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])

    portfolios = []
    stock_value = 0

    for row in rows:
        stock = row["symbol"]
        name = lookup(stock)["name"]
        amount = row["shares"]
        current = lookup(stock)["price"]
        value = round(current * amount, 2)
        stock_info = [stock, name, amount, current, value]
        portfolios.append(stock_info)
        stock_value += value

    # Show user's cash balance, stock value and grand total
    cash_balance = round(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"], 2)
    stock_value = round(stock_value, 2)
    grand_total = round(cash_balance + stock_value, 2)

    # Show user's start value, end value (current value) and P/L to date
    start_value = 10000
    end_value = grand_total
    profit_loss = round(end_value - start_value, 2)

    return render_template("index.html", portfolios=portfolios, cash_balance=cash_balance, stock_value=stock_value, grand_total=grand_total,
    start_value=start_value, end_value=end_value, profit_loss=profit_loss)


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        stock = lookup(request.form.get("symbol"))

        # Validate submission
        if not stock:
            flash("Invalid stock.")
            return redirect("/quote")

        return render_template("quoted.html", stock=stock)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        stock = lookup(symbol)

        # Validate submission
        if not symbol:
            flash("Please provide stock's symbol.")
            return redirect("/buy")

        if not shares:
            flash("Please provide amount.")
            return redirect("/buy")

        if not stock:
            flash("Invalid stock.")
            return redirect("/buy")

        if float(shares) <= 0:
            flash("Invalid amount.")
            return redirect("/buy")

        # Check user's cash for transaction
        price_current = stock["price"]
        value = round(price_current * float(shares), 2)
        cash_current = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        cash_updated = round(cash_current - value, 2)

        # Unsuccessful transaction
        if cash_updated < 0:
            flash("You don't have enough balance for this transaction.")
            return redirect("/buy")

        # Successful transaction
        # Check if user already has stock from this company
        # Update shares
        symbol = stock["symbol"]
        name = stock["name"]
        shares = round(float(shares), 2)

        if db.execute("SELECT * FROM stocks WHERE user_id = ? AND symbol = ?", session["user_id"], symbol):
            shares_current = db.execute("SELECT shares FROM stocks WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)[0]["shares"]
            shares_updated = round((shares_current + shares), 2)
            db.execute("UPDATE stocks SET shares = ? WHERE user_id = ? AND symbol = ?", shares_updated, session["user_id"], symbol)

        else:
            db.execute("INSERT INTO stocks (user_id, symbol, shares) VALUES (?, ?, ?)", session["user_id"], symbol, shares)

        # Update user's cash
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_updated, session["user_id"])

        # Update transactions
        db.execute("INSERT INTO transactions (user_id, symbol, name, shares, open, value, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
        session["user_id"], symbol, name, shares, price_current, value, datetime.now())

        # Redirect user to home page with success message
        flash("Successful transaction: Bought!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        stock = lookup(symbol)

        # Validate submission
        if not symbol:
            flash("Please provide stock's symbol.")
            return redirect("/sell")

        if not shares:
            flash("Please provide amount.")
            return redirect("/sell")

        if not stock:
            flash("Invalid stock.")
            return redirect("/sell")

        symbol_current = db.execute("SELECT symbol FROM stocks WHERE user_id = ?", session["user_id"])
        match = False

        for item in symbol_current:
            if item["symbol"] == symbol:
                match = True
                break

        if not match:
            flash("You do not own that stock.")
            return redirect("/sell")

        shares_current = db.execute("SELECT shares FROM stocks WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)[0]["shares"]

        if float(shares) <= 0:
            flash("Invalid amount.")
            return redirect("/sell")

        if float(shares) > shares_current:
            flash("You do not own that many shares.")
            return redirect("/sell")

        # Successful transaction
        # Update shares
        symbol = stock["symbol"]
        name = stock["name"]
        shares_updated = round(shares_current - float(shares), 2)

        if shares_updated == 0:
            db.execute("DELETE FROM stocks WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)

        db.execute("UPDATE stocks SET shares = ? WHERE user_id = ? AND symbol = ?", shares_updated, session["user_id"], symbol)

        # Update user's cash
        price_current = stock["price"]
        value = round(price_current * float(shares), 2)
        cash_current = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        cash_updated = round(cash_current + value, 2)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_updated, session["user_id"])

        # Update transactions
        db.execute("INSERT INTO transactions (user_id, symbol, name, shares, close, value, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
        session["user_id"], symbol, name, shares, price_current, value, datetime.now())

        # Redirect user to home page with success message
        flash("Successful transaction: Sold!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Query infos from db
        rows = db.execute("SELECT symbol, shares FROM stocks WHERE user_id = ?", session["user_id"])
        return render_template("sell.html", rows=rows)


@app.route("/history")
@login_required
def history():

    # Show transaction history
    rows = db.execute("SELECT * FROM transactions WHERE user_id = ?", session["user_id"])

    transactions = []
    total_buy, total_sell = 0, 0

    for row in rows:
        stock_info = [row["symbol"], lookup(row["symbol"])["name"], row["shares"], row["open"], row["close"], row["value"], row["date"]]
        transactions.append(stock_info)

        if row["open"]:
            total_buy += row["value"]

        if row["close"]:
            total_sell += row["value"]

    total_buy = round(total_buy, 2)
    total_sell = round(total_sell, 2)

    return render_template("history.html", transactions=transactions, total_buy=total_buy, total_sell=total_sell)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)