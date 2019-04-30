#!/usr/bin/python
# coding=utf-8

import os
import datetime
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import Flask, render_template, request, jsonify, flash, redirect, session, url_for, make_response
from flaskext.mysql import MySQL
from pymysql.cursors import DictCursor

from passlib.apps import custom_app_context as pwd_context

# Chart modules
import pygal
from pygal import Config
from pygal.style import Style

# Helper functions
from functions import *

# Get environment variables, either locally or from config vars
try:
    from settings import *
except ImportError:
    mysqlhost = os.environ['MYSQLHOST']
    mysqldb = os.environ['MYSQLDB']
    mysqluser = os.environ['MYSQLUSER']
    mysqlpassword = os.environ['MYSQLPASSWORD']
    secretkey = os.environ['SECRETKEY']
    smtpuser = os.environ['SMTPUSER']
    smtppassword = os.environ['SMTPPASSWORD']
    loc = os.environ['LOC']

locale.setlocale(locale.LC_ALL, loc)

# Configure Application
app = Flask(__name__)
app.config['MYSQL_DATABASE_HOST'] = mysqlhost
app.config['MYSQL_DATABASE_DB'] = mysqldb
app.config['MYSQL_DATABASE_USER'] = mysqluser
app.config['MYSQL_DATABASE_PASSWORD'] = mysqlpassword
app.secret_key = secretkey
app.config['SESSION_TYPE'] = 'filesystem'
mysql = MySQL(app, cursorclass=DictCursor)

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filters
app.jinja_env.filters['gbp'] = gbp
app.jinja_env.filters['shareprice'] = shareprice
app.jinja_env.filters['percentage'] = percentage
app.jinja_env.filters['dateFormat'] = dateFormat

try:
    cursor.execute("SET time_zone='UTC'")
except:
    pass

# Connect to MySQL database
def dbConnect():
    conn = mysql.connect()
    cursor = conn.cursor()
    return (conn, cursor)

# Function to get portfolio data, required for nav bar on every page
# Returns array with index of current selected portfolio
def getPortfolio():
    conn, cursor = dbConnect()

    cursor.execute('SELECT * FROM portfolios WHERE userid=%s', [session['user_id']])
    portfolios = cursor.fetchall()
    for i in range(len(portfolios)):
        if portfolios[i]['id'] == session['portfolio']:
            return [portfolios, i]

# Function to calculate users capital and cash
# Returns dictionary
def getAssets(date = "{} 23:59:59".format(datetime.datetime.utcnow().strftime("%Y-%m-%d"))):
    conn, cursor = dbConnect()
    cursor.execute('SELECT SUM(amount) AS capital FROM cash WHERE categoryid=10 AND date<=%s AND userid=%s AND portfolioid=%s', [date, session['user_id'], session['portfolio']])
    capital = cursor.fetchone()['capital']
    capital = float(capital) if capital else 0

    cursor.execute('SELECT SUM(x) AS money FROM (SELECT SUM(amount) x FROM cash WHERE date<=%s AND userid=%s AND portfolioid=%s UNION SELECT SUM(buycost) * -1 x FROM shares WHERE buydate<=%s AND userid=%s AND portfolioid=%s UNION SELECT SUM(value) x FROM shares WHERE selldate<=%s AND status=0 AND userid=%s AND portfolioid=%s) s',
        [date, session['user_id'], session['portfolio'], date, session['user_id'], session['portfolio'], date, session['user_id'], session['portfolio']])
    cash = cursor.fetchone()['money']
    cash = float(cash) if cash else 0
    
    return {
        'capital': capital,
        'cash': cash
    }
 
# Function to update assets in database
def updateAssets():
    conn, cursor = dbConnect()

    assets = getAssets()
    cursor.execute('UPDATE portfolios SET capital=%s, cash=%s WHERE id=%s AND userid=%s', [assets['capital'], assets['cash'], session['portfolio'], session['user_id']])
    conn.commit()

# Route for Index Page, shows current open positions
@app.route('/')
@login_required
def index():
    conn, cursor = dbConnect()

    # Get portfolio details and set last updated text to readable format
    portfolios = getPortfolio()
    
    # If portfolio variable added, change portfolio
    if request.args.get('portfolio'):
        try:
            newportfolio = int(request.args.get('portfolio'))
            for i in portfolios[0]:
                if i['id'] == newportfolio:
                    session['portfolio'] = newportfolio
                    portfolios = getPortfolio()
                    break
        except ValueError:
            pass
        
    portfolio_index = portfolios[1]
    portfolios[0][portfolio_index]['lastupdated'] = portfolios[0][portfolio_index]['lastupdated'].isoformat(); #.strftime('%a %d %b @ %I:%M:%S%p')

    # Get open share data from database
    cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolioid=%s AND status=1 ORDER BY epic ASC', [session['user_id'], session['portfolio']])
    sharedata = cursor.fetchall()

    # Calculate capital/cash
    assets = getAssets()
    
    # Get market exposure from last trading day to calculate daily performance
    cursor.execute('SELECT exposure, cash FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC LIMIT 2', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    if len(data) > 1:
        lastexposure = data[1]['exposure']
        lastcash = data[1]['cash']
    else:
        lastexposure = 0
        lastcash = assets['capital']
    
    # Calculate portfolio details
    # Market exposure, total sale cost (exposure - costs), daily performance
    portfoliodetails = {
        'exposure': 0,
        'sale_costs': 0,
        'dailyprofit': 0
    }
    for row in sharedata:
        # Calculate days held
        buyDatetime = verifyDate(row['buydate'], startofday=True)
        if row['selldate'] == None:
            row['daysHeld'] = (datetime.datetime.now(pytz.utc) - buyDatetime).days
        else:
            sellDatetime = verifyDate(row['selldate'], startofday=True)
            row['daysHeld'] = (sellDatetime - buyDatetime).days
        
        portfoliodetails['exposure'] += row['sellprice'] * row['quantity'] * 0.01
        portfoliodetails['sale_costs'] += row['selltradecost']
        row['dailygain'] = row['sellprice'] - row['bidopen']
    portfoliodetails['dailyprofit'] = portfoliodetails['exposure'] + portfolios[0][portfolio_index]['cash'] - lastexposure - lastcash
    if portfoliodetails['exposure'] != 0:
        portfoliodetails['dailypercent'] = 100 * portfoliodetails['dailyprofit'] / portfoliodetails['exposure']
    else:
        portfoliodetails['dailypercent'] = 0
    
    return render_template('index.html', sharedata=sharedata, portfoliodetails=portfoliodetails, portfolios=portfolios[0], portfolio_index=portfolio_index)

# Route for Share Entry Page
@app.route('/shares', methods=['GET', 'POST'])
@login_required
def shares():
    conn, cursor = dbConnect()

    if request.method == 'POST':
    
        submit = request.form.get('submit')
        if request.form.get('id'):
            id = int(request.form.get('id'))
        else:
            id = None

        # If deleting an entry
        if submit == 'delete':
            cursor.execute('DELETE FROM shares WHERE id=%s AND userid=%s', [id, session['user_id']])
            cursor.execute('SELECT id FROM shares WHERE userid=%s ORDER BY id ASC', [session['user_id']])
            data = cursor.fetchall()
            oldid = id
            id = 0
            if len(data) > 0:
                if data[-1]['id'] < oldid:
                    id = data[-1]['id']
                else:
                    for i in range(len(data) - 1, -1, -1):
                        if data[i]['id'] > oldid:
                            id = data[i]['id']
            submit = None
            cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND id=%s AND portfolioid=%s', [session['user_id'], id, session['portfolio']])
            share = cursor.fetchone()
            updateAssets()
        
        else:
        
            # Assume input is true to start with
            inputValidation = True
        
            # Validate EPIC code
            # Check to see that it is listed in companies db
            cursor.execute('SELECT * FROM companies WHERE symbol=%s', [request.form.get('epic')])
            if cursor.rowcount == 0: inputValidation = False
        
            # Dictionary to keep state when page is reloaded
            # All these values are verified or don't require verification
            share = {
                'id': id,
                'epic': request.form.get('epic').upper(),
                'company': request.form.get('company'),
                'dividends': 0,
                'status': int(request.form.get('status')),
                'comment': request.form.get('comment')
            }
            if request.form.get('dividends'):
                share['dividends'] = float(request.form.get('dividends'))
        
            # Dictionary of posted values to check, will be added to share dict
            # {field: [variable, type, require user entry, default, message]}
            
            values = {
                'buydate': [request.form.get('buydate'), 'date', False, datetime.datetime.now(pytz.timezone('Europe/London')), ''],
                'selldate': [request.form.get('selldate'), 'date', False, None, ''],
                'quantity': [request.form.get('quantity'), 'int', True, 0, 'Quantity required'],
                'stampduty': [request.form.get('stampduty'), 'float', False, 0, ''],
                'buytradecost': [request.form.get('buytradecost'), 'float', False, 0, ''],
                'sellprice': [request.form.get('sellprice'), 'float', False, 0, ''],
                'selltradecost': [request.form.get('selltradecost'), 'float', False, 0, ''],
                'value': [request.form.get('value'), 'float', False, 0, ''],
                'buyprice': [request.form.get('buyprice'), 'float', True, 0, 'Buy price required']
            }
        
            # Look through values and check that required items are correct
            for key, val in values.items():
                try:
                    # Check floats and ints cast properly
                    if val[1] == 'float' or val[1] == 'int':
                        share[key] = float(val[0])
                        if val[1] == 'int':
                            share[key] = int(float(val[0]))
                    
                    # Check date
                    if val[1] == 'date':
                        share[key] = pytz.timezone('Europe/London').localize(datetime.datetime.strptime(val[0], '%Y-%m-%d %H:%M:%S'))   
                        print(share[key])
                except ValueError:
                    # If casting fails, revert to default value
                    # If input required for this field, input validation fails here
                    share[key] = val[3]
                    if val[2]:
                        flash(val[4], 'danger')
                        inputValidation = False
        
            # Dictionary of values to check with defaults that depend on the last step
            defaults = {
                'buycost': [request.form.get('buycost'), 'float', False, (share['quantity'] * share['buyprice'] * 0.01) - share['stampduty'] - share['buytradecost']],
                'target': [request.form.get('target'), 'float', False, share['buyprice'] * 1.2],
                'stoploss': [request.form.get('stoploss'), 'float', False, share['buyprice'] * 0.9]
            }
        
            for key, val in defaults.items():
                try:
                    # Check floats cast properly
                    share[key] = float(val[0])
                except ValueError:
                    # If the rest of the input is validated, set these to default values for entry to db
                    # Otherwise set to 0
                    if inputValidation:
                        share[key] = val[3]
                    else:
                        share[key] = 0
            
            share['profitloss'] = share['value'] - share['buycost']
            if share['buyprice'] * share['quantity'] != 0:
                share['percentage'] = ((10000 * (share['value'] - share['stampduty'] - share['buytradecost'] - share['selltradecost'] + share['dividends']) / (share['buyprice'] * share['quantity'])) - 100)
            
            if share['status'] == 0 and not verifyDate(share['selldate']):
                share['selldate'] = datetime.datetime.now(pytz.timezone('Europe/London'))
            
            if submit == 'submit':
                quoteLogin()
                share['bidopen'] = quote(share['epic'])
                if share['bidopen'] == None:
                    flash('EPIC Required', 'danger')
                    valid = False
            else:
                share['bidopen'] = None
            
            # If input validated, try to write to database
            if inputValidation:
                goToIndex = 0

                # Set buydate as UTC for database
                buydate = verifyDate(request.form.get('buydate')).replace(tzinfo=None)
                buydate = pytz.timezone('Europe/London').localize(buydate).astimezone(pytz.utc)

                # Set selldate as UTC for database
                selldate = share['selldate']
                if selldate:
                    selldate = share['selldate'].replace(tzinfo=None)
                    selldate = pytz.timezone('Europe/London').localize(selldate).astimezone(pytz.utc)

                data = [session['user_id'], session['portfolio'], share['epic'], share['status'], buydate,
                        share['buyprice'], share['quantity'], share['stampduty'], share['buytradecost'],
                        share['buycost'], share['target'], share['stoploss'], selldate, 
                        share['sellprice'], share['selltradecost'], share['value'], share['profitloss'],
                        share['percentage'], share['comment'], share['bidopen']]
        
                # If entering a new entry
                if submit == 'submit':
                    goToIndex = cursor.execute('INSERT INTO shares (userid, portfolioid, epic, status, buydate, buyprice, quantity, stampduty, buytradecost, buycost, target, stoploss, selldate, sellprice, selltradecost, value, profitloss, percentage, comment, bidopen) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', data)
                    conn.commit()
                    
                # If updating an old entry
                elif submit == 'update':
                    data.pop()
                    data.append(request.form.get('id'))
                    cursor.execute('UPDATE shares SET userid=%s, portfolioid=%s, epic=%s, status=%s, buydate=%s, buyprice=%s, quantity=%s, stampduty=%s, buytradecost=%s, buycost=%s, target=%s, stoploss=%s, selldate=%s, sellprice=%s, selltradecost=%s, value=%s, profitloss=%s, percentage=%s, comment=%s WHERE id=%s', data)
                    conn.commit()
                
                updateAssets()
                    
                # If entry succeeded, go to index else go back to edit page
                if goToIndex == 1:
                    return redirect(url_for('index'))
    
    # Verify submit/id and get share data from database if updating
    updating = True           
    try:
        id = share['id']
        if id:
            submit = 'update'
    except:
        updating = False
    if request.args.get('submit') != 'submit' and not updating:
        submit = 'update'
        try:
            id = int(request.args.get('id'))
        except TypeError:
            id = None
        if id:
            cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND id=%s AND portfolioid=%s', [session['user_id'], id, session['portfolio']])
        else:
            cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolioid=%s ORDER BY id DESC LIMIT 1', [session['user_id'], session['portfolio']])
        if cursor.rowcount == 1:
            share = cursor.fetchone()
            # Add London timezone to dates
            for i in ['buydate', 'selldate']:
                if share[i]:
                    share[i] = pytz.utc.localize(share[i]).astimezone(pytz.timezone('Europe/London'))
            id = share['id']
        else:
            submit = 'submit'
    elif not updating:
        submit = 'submit'
        id = None
    
    # Create 'nav' dictionary to store navigation variables
    # numEntries, previd, nextid, lastid
    nav = {}
    cursor.execute('SELECT id FROM shares WHERE userid=%s AND portfolioid=%s ORDER BY id ASC', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    nav['numEntries'] = cursor.rowcount
    nav['lastid'] = 0 if nav['numEntries'] == 0 else data[-1]['id']
    
    # Set some default values
    if submit == 'submit':
        if request.method == 'GET' or request.form.get('submit') == "delete":
            share = {
                'buydate': datetime.datetime.now(pytz.timezone('Europe/London')),
                'selldate': None
            }   
        share['daysHeld'] = None
        dividends = []
            
    if submit == 'update':
        nav['index'] = data.index({'id': id}) + 1
        nav['previd'] = None if nav['index'] == 1 else data[nav['index'] - 2]['id']
        nav['nextid'] = None if nav['index'] == nav['numEntries'] else data[nav['index']]['id']
        
        buyDatetime = verifyDate(share['buydate'], startofday=True)
        if share['selldate'] == None:
            share['daysHeld'] = (datetime.datetime.now(pytz.utc) - buyDatetime).days
        else:
            sellDatetime = verifyDate(share['selldate'], startofday=True)
            share['daysHeld'] = (sellDatetime - buyDatetime).days
        
        cursor.execute('SELECT date, amount FROM cash WHERE shareid=%s AND userid=%s AND portfolioid=%s ORDER BY date DESC', [id, session['user_id'], session['portfolio']])
        dividends = cursor.fetchall()

    return render_template('shares.html', nav=nav, share=share, submit=submit, portfolios=getPortfolio()[0], dividends=dividends)

# Route for Cash Statement/Entry Page
@app.route('/statement', methods=['GET', 'POST'])
@login_required
def statement():
    conn, cursor = dbConnect()

    portfolios = getPortfolio()
    portfolio_index = portfolios[1]
    registerdate = portfolios[0][portfolio_index]['registerdate'].replace(tzinfo=pytz.utc)
    msg = []
    
    # Set default values for start and end date
    today = datetime.datetime.now(pytz.utc)
    startdate = today + datetime.timedelta(days=-365)
    if startdate < registerdate:
        startdate = registerdate
    startdate = startdate.replace(hour=0, minute=0, second=0, microsecond=0)
    dates = {
        'start': startdate,
        'end': verifyDate(today, endofday=True)
    }
    
    # If default button was not pressed, check for input and verify
    if request.args.get('default') != 'Default':
        if request.args.get('startdate'):
            date = verifyDate(request.args.get('startdate'), startofday=True)
            if date:
                dates['start'] = date
    
        if request.args.get('enddate'):
            date = verifyDate(request.args.get('enddate'), endofday=True)
            if date:
                dates['end'] = date
    
    print(dates['start'], dates['end'])
    # If new cash transaction posted
    if request.method == 'POST' and request.form.get('submit') != 'delete':
        
        valid = True
        prefill = {
            'amount': request.form.get('cash_amount'),
            'category': request.form.get('cash_category'),
            'epic': request.form.get('sharedividend'),
            'notes': request.form.get('cash_notes'),
            'date': request.form.get('cash_date')
        }
        # Check submitted amount is a number
        if not request.form.get('cash_amount'):
            msg.append('No amount entered')
            valid = False
        else:
            try:
                cash_amount = float(request.form.get('cash_amount'))
            except ValueError:
                msg.append('Amount should be a number')
                valid = False

        # Convert category to integer
        category = int(request.form.get('cash_category'))
        
        # Check date
        if category == 10 or category == 20 or category == 25:
            date = verifyDate(request.form.get('cash_date'), startofday=True)
        elif category == 15 or category == 30:
            date = verifyDate(request.form.get('cash_date'), endofday=True)
        print(1, verifyDate(today.replace(tzinfo=pytz.utc), endofday=True), date)
        print(verifyDate(today.replace(tzinfo=pytz.utc), endofday=True) > date)
        if verifyDate(today.replace(tzinfo=pytz.utc), endofday=True) < date:
            date = None
        if not date:
            msg.append('Invalid date')
            valid = False
        
        if valid:
            # If dividend
            if category == 20 and request.form.get('sharedividend'):
        
                # If category is dividend, get all possible shares from db
                cursor.execute('SELECT id, quantity FROM shares WHERE epic=%s AND status=1 AND userid=%s AND portfolioid=%s', [request.form.get('sharedividend'), session['user_id'], session['portfolio']])
                sharedata = cursor.fetchall()
            
                # Get total shares for epic
                total = sum([i['quantity'] for i in sharedata])
            
                # Calculate ratio of dividend for each share, add into cash db and update share row
                for share in sharedata:
                    ratio = share['quantity'] / total
                    cursor.execute('INSERT INTO cash (userid, portfolioid, amount, categoryid, shareid, notes, date) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                        [session['user_id'], session['portfolio'], cash_amount * ratio, category, share['id'], request.form.get('cash_notes'), date])
                    cursor.execute('UPDATE shares SET dividends=dividends+%s WHERE id=%s AND userid=%s AND portfolioid=%s',
                        [cash_amount * ratio, share['id'], session['user_id'], session['portfolio']])
                    conn.commit()
            
            else:
                # If withdrawal, make negative
                if category == 15 or category == 30:
                    cash_amount *= -1

                # If not a dividend, just add into cash db
                cursor.execute('INSERT INTO cash (userid, portfolioid, amount, categoryid, shareid, notes, date) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    [session['user_id'], session['portfolio'], cash_amount, category, None, request.form.get('cash_notes'), date])
                conn.commit()

            # Update user's cash
            cash = getAssets()['cash']
            cursor.execute('UPDATE portfolios SET cash=%s WHERE userid=%s AND id=%s', [cash, session['user_id'], session['portfolio']])
            conn.commit()
                
            if category >= 10 and category <= 15:
                # Update users capital invested if capital entry
                cursor.execute('UPDATE portfolios SET capital=capital+%s WHERE userid=%s AND id=%s', [cash_amount, session['user_id'], session['portfolio']])
            
                # Update log if a capital investment
                cursor.execute('UPDATE log SET cash=cash+%s, capital=capital+%s WHERE date>=%s AND userid=%s AND portfolioid=%s', [cash_amount, cash_amount, request.form.get('cash_date'), session['user_id'], session['portfolio']])
                conn.commit()
            else:
                # Update log if not a capital investment
                cursor.execute('UPDATE log SET cash=cash+%s WHERE date>=%s AND userid=%s AND portfolioid=%s', [cash_amount, request.form.get('cash_date'), session['user_id'], session['portfolio']])
                conn.commit()
            
            prefill = None
    
    # Delete cash transaction
    elif request.method == 'POST' and request.form.get('submit') == 'delete':
        cursor.execute('DELETE FROM cash WHERE id=%s AND userid=%s AND portfolioid=%s', [request.form.get('id'), session['user_id'], session['portfolio']])
        cursor.execute('UPDATE portfolios SET cash=cash-%s WHERE userid=%s AND id=%s', [request.form.get('value'), session['user_id'], session['portfolio']])
        if request.form.get('category') == '10' or request.form.get('category') == '15':
            cursor.execute('UPDATE portfolios SET capital=capital-%s WHERE userid=%s AND id=%s', [request.form.get('value'), session['user_id'], session['portfolio']])
        elif request.form.get('category') == '20':
            cursor.execute('UPDATE shares SET dividends=dividends-%s WHERE id=%s AND userid=%s AND portfolioid=%s', [request.form.get('value'), request.form.get('shareid'), session['user_id'], session['portfolio']])
        conn.commit()
        prefill = None
    
    else:
        prefill = None
    
    # Get cash categories
    cursor.execute('SELECT * FROM cash_categories')
    cash_categories = cursor.fetchall()
    
    # Get share buy data from database and add to statement list
    statement = []
    cursor.execute('SELECT id, buydate, company, buycost FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
    buydata = cursor.fetchall()
    for row in buydata:
        statement.append({
            'linkid': row['id'],
            'date': row['buydate'].replace(tzinfo=pytz.utc),
            'transaction': row['company'].title(),
            'debit': row['buycost'],
            'credit': None,
            'category': 'buy'
        })
    
    # Get share sell data from database and add to statement list
    cursor.execute('SELECT id, selldate, company, value FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolioid=%s AND status=0', [session['user_id'], session['portfolio']])
    selldata = cursor.fetchall()
    for row in selldata:
        statement.append({
            'linkid': row['id'],
            'date': row['selldate'].replace(tzinfo=pytz.utc),
            'transaction': row['company'].title(),
            'debit': None,
            'credit': row['value'],
            'category': 'sell'
        })
    
    # Get cash transactions from database and add to statement list
    cursor.execute('SELECT cash.id, shareid, date, category, notes, categoryid, amount FROM cash INNER JOIN cash_categories ON cash.categoryid=cash_categories.id WHERE userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
    cashdata = cursor.fetchall()
    for row in cashdata:
        transaction = {
            'cashid': row['id'],
            'linkid': row['shareid'],
            'date': row['date'].replace(tzinfo=pytz.utc),
            'transaction': 'Cash: {}'.format(row['category']),
            'debit': None,
            'credit': None,
            'notes': row['notes'],
            'category': row['categoryid']
        }
        if row['amount'] >= 0:
            transaction['credit'] = row['amount']
        else:
            transaction['debit'] = row['amount'] * -1
        statement.append(transaction)
    
    # Sort statement and calculate balance
    statement = sorted(statement, key=lambda k: k['date'], reverse=True)
    balance = 0
    for row in reversed(statement):
        if row['credit']:
            row['balance'] = balance + row['credit']
        else:
            row['balance'] = balance - row['debit']
        balance = row['balance']
    
    date = datetime.datetime.now(pytz.utc).strftime("%Y-%m-%d")
    return render_template('statement.html', prefill=prefill, cash_categories=cash_categories, statement=statement, portfolios=portfolios[0], date=date, msg=msg, dates=dates)

# Route for Log Page
@app.route('/log', methods=['GET', 'POST'])
@login_required
def log():
    conn, cursor = dbConnect()

    # Get all log data from database
    cursor.execute('SELECT * FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC', [session['user_id'], session['portfolio']])
    log = cursor.fetchall()
    
    # Recalculate all rows capital/cash in logging to fix errors
    if request.method == 'POST' and request.form.get('submit') == 'Recalculate':
        for i in range(len(log)):
            date = '{} 23:59:59'.format(log[i]['date'].replace(tzinfo=pytz.utc).strftime('%Y-%m-%d'))
            assets = getAssets(date)
            cursor.execute('UPDATE log SET capital=%s, cash=%s WHERE id=%s', [assets['capital'], assets['cash'], log[i]['id']])
            conn.commit()
            
        # Reload log from database
        cursor.execute('SELECT * FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC', [session['user_id'], session['portfolio']])
        log = cursor.fetchall()
    
    
    # Get FTSE100 when account created
    cursor.execute('SELECT ftse100 FROM portfolios WHERE userid=%s AND id=%s', [session['user_id'], session['portfolio']])
    ftse100base = cursor.fetchone()['ftse100']
    
    # Calculate percentages
    for i in range(len(log)):
        log[i]['ftse100percent'] = (100 * (log[i]['ftse100'] / ftse100base)) - 100
        log[i]['profitloss'] = log[i]['exposure'] + log[i]['cash'] - log[i]['capital']
        if log[i]['capital'] == 0:
            log[i]['percentage'] = 0
        else:
            log[i]['percentage'] = (100 * ((log[i]['exposure'] + log[i]['cash']) / log[i]['capital'])) - 100
        if i > 0:
            log[i - 1]['dailyprofit'] = previous_exp + previous_cash - log[i]['exposure'] - log[i]['cash']
            if previous_exp - log[i - 1]['dailyprofit'] != 0:
                log[i - 1]['dailypercent'] = 100 * (log[i - 1]['dailyprofit'] / (previous_exp - log[i - 1]['dailyprofit']))
            else:
                log[i - 1]['dailypercent'] = None
        previous_exp = log[i]['exposure']
        previous_cash = log[i]['cash']
    
    return render_template('log.html', log=log, portfolios=getPortfolio()[0], ftse100base=ftse100base)

# Route for Chart Page
@app.route('/charts', methods=['GET'])
@login_required
def charts():
    conn, cursor = dbConnect()

    portfolios = getPortfolio()
    portfolio_index = portfolios[1]
    registerdate = portfolios[0][portfolio_index]['registerdate'].replace(tzinfo=pytz.utc)
    
    # Set default values for start and end date
    today = datetime.datetime.now(pytz.utc)
    startdate = today + datetime.timedelta(days=-365)
    if startdate < registerdate:
        startdate = registerdate.replace(hour=0, minute=0, second=0, microsecond=0)
    dates = {
        'start': startdate,
        'end': today
    }
    
    # If default button was not pressed, check for input and verify
    if request.args.get('default') != 'Default':
        if request.args.get('startdate'):
            date = verifyDate(request.args.get('startdate'))
            if date:
                dates['start'] = date
    
        if request.args.get('enddate'):
            date = verifyDate(request.args.get('enddate'))
            if date:
                dates['end'] = date
    
    # Get info from portfolios db
    cursor.execute('SELECT name, ftse100 FROM portfolios WHERE userid=%s AND id=%s', [session['user_id'], session['portfolio']])
    data = cursor.fetchone()
    oldftse100 = data['ftse100']
    portfolioname = data['name']
    
    # Get charting data from log db
    cursor.execute('SELECT * FROM log WHERE date>=%s AND date<=%s AND userid=%s AND portfolioid=%s ORDER BY date ASC',
        [dates['start'], '{} 23:59:59'.format(dates['end']), session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    
    # Prepare data
    x_all = []
    x_axis = []
    interval = len(data) // 10 if len(data) > 10 else 1
    portfoliodata = []
    ftse100 = []
    difference = []
    maxvalue = 0
    minvalue = 0
    for i in range(len(data)):
    
        # Add dates to x_axis list
        x = {
            'value': i,
            'label': data[i]['date'].strftime("%Y-%m-%d")
        }
        x_all.append(x)
        if i % interval == 0: x_axis.append(x)
        
        # Calculate percentages
        if data[i]['capital'] != 0:
            percentage = (100 * ((data[i]['exposure'] + data[i]['cash']) / data[i]['capital'])) - 100
        else:
            percentage = 0    
        ftse100percentage = (100 * ((data[i]['ftse100']) / oldftse100)) - 100
        differencepercentage = percentage - ftse100percentage
        
        # Add percentages to lists
        portfoliodata.append((i, percentage))
        ftse100.append((i, ftse100percentage))
        difference.append((i, differencepercentage))
        
        # Get max and min y-axis values
        if percentage > maxvalue:
            maxvalue = percentage
        elif percentage < minvalue:
            minvalue = percentage
    
    # Prepare chart
    chart_style = Style(
        colors=('red', 'blue', 'lightgreen'),
        transition='200ms ease-in',
        font_family="Arial")
    
    chart_config = Config(
        height=400,
        fill=True,
        style=chart_style,
        x_label_rotation=60,
        range=(minvalue-10,maxvalue+5),
        dots_size=1
    )
    
    # Initialise chart
    chart = pygal.XY(chart_config)
    chart.x_labels = x_axis
    chart.add(portfolioname, portfoliodata)
    chart.add('FTSE100', ftse100)
    chart.add('Difference', difference)
    
    # Format hover display
    chart.value_formatter = lambda y: '{:+.2f}%'.format(y)
    if len(x_all) > 0:
        chart.x_value_formatter = lambda x: x_all[x]['label']
    chart_data = chart.render_data_uri()
    
    return render_template('charts.html', portfolios=portfolios[0], chart_data=chart_data, dates=dates)

# Route for User Control Panel
@app.route('/controlpanel', methods=['GET', 'POST'])
@login_required
def controlpanel():
    conn, cursor = dbConnect()

    # If form submitted...
    if request.method == 'POST':
    
        # Delete Portfolio
        if request.form.get('submit') == 'Delete':
            cursor.execute('DELETE FROM portfolios WHERE id=%s AND userid=%s', [request.form.get('id'), session['user_id']])
            cursor.execute('DELETE FROM log WHERE portfolioid=%s AND userid=%s', [request.form.get('id'), session['user_id']])
            cursor.execute('DELETE FROM cash WHERE portfolioid=%s AND userid=%s', [request.form.get('id'), session['user_id']])
            cursor.execute('DELETE FROM shares WHERE portfolioid=%s AND userid=%s', [request.form.get('id'), session['user_id']])
            conn.commit()
        
        # Switch Portfolio
        elif request.form.get('submit') == 'Switch':
            newportfolio = request.form.get('id')
            cursor.execute('UPDATE users SET lastportfolioid=%s WHERE id=%s', [newportfolio, session['user_id']])
            conn.commit()
            session['portfolio'] = int(newportfolio)
        
        # Add Portfolio
        elif request.form.get('submit') == 'Add':
            valid = True
            # Validate name
            if not request.form.get('addportfolioname'):
                valid = False
            else:
                # Check name is not duplicate
                portfolios = getPortfolio()[0]
                for i in portfolios:
                    if i['name'].lower() == request.form.get('addportfolioname').lower():
                        valid = False
                        break
            if valid:
                # Update database
                quoteLogin()
                ftse100 = quote('FTSE:UKX', 'price')
                cursor.execute('INSERT INTO portfolios (userid, name, ftse100) VALUES (%s, %s, %s)', [session['user_id'], request.form.get('addportfolioname'), ftse100])
                conn.commit()
        
        # Rename Portfolio
        elif request.form.get('submit') == 'Rename':
            valid = True
            # Validate name
            if not request.form.get('rename'):
                valid = False
            else:
                # Check name is not duplicate
                portfolios = getPortfolio()[0]
                for i in portfolios:
                    if i['name'].lower() == request.form.get('rename').lower():
                        valid = False
                        break
            if valid:
                # Update database
                cursor.execute('UPDATE portfolios SET name=%s WHERE userid=%s AND id=%s', [request.form.get('rename'), session['user_id'], request.form.get('id')])
                conn.commit()
        
        # Change Username
        elif request.form.get('submit') == 'Change Username':
            # Validate input
            valid = False
            if not request.form.get('changeusername_old'):
                flash('You must enter your current username!', 'danger')
                
            elif request.form.get('changeusername_old') != session['username']:
                flash('You got your username wrong!', 'danger')
                
            elif not request.form.get('changeusername_new'):
                flash('You must enter a new username!', 'danger')
                
            elif not request.form.get('changeusername_password'):
                flash('You must enter your password!', 'danger')
            
            else:
                valid = True
                
            if valid:
                # Check password
                cursor.execute('SELECT * FROM users WHERE id=%s AND username=%s', [session['user_id'], request.form.get('changeusername_old')])
                if pwd_context.verify(request.form.get('changeusername_password'), cursor.fetchone()['password']):
                    try:
                        cursor.execute('UPDATE users SET username=%s WHERE id=%s', [request.form.get('changeusername_new'), session['user_id']])
                        session['username'] = request.form.get('changeusername_new')
                        conn.commit()
                        flash('Username changed!', 'success')
                    except:
                        flash('Username already in use', 'danger')
                else:
                    flash('Wrong password!', 'danger')
        
        # Change Password
        elif request.form.get('submit') == 'Change Password':
            # Validate input
            valid = False
            if not request.form.get('changepassword_username'):
                flash('You must enter your username!', 'danger')
            
            elif request.form.get('changepassword_username') != session['username']:
                flash('You got your username wrong!', 'danger')
            
            elif not request.form.get('changepassword_old'):
                flash('You must enter your old password!', 'danger')
            
            elif not request.form.get('changepassword_new'):
                flash('You must enter a new password!', 'danger')
                
            elif not request.form.get('changepassword_confirm'):
                flash('You must confirm your new password!', 'danger')
                
            elif request.form.get('changepassword_new') != request.form.get('changepassword_confirm'):
                flash('Your new password does not match the confirmation!', 'danger')
            
            else:
                valid = True
                
            if valid:
                # Check password
                cursor.execute('SELECT * FROM users WHERE id=%s AND username=%s', [session['user_id'], request.form.get('changepassword_username')])
                if pwd_context.verify(request.form.get('changepassword_old'), cursor.fetchone()['password']):
                    try:
                        cursor.execute('UPDATE users SET password=%s WHERE id=%s', [pwd_context.encrypt(request.form.get('changepassword_new')), session['user_id']])
                        conn.commit()
                        flash('Password changed!', 'success')
                        if session['rememberme'] == 1:
                            session['password'] = request.form.get('changepassword_new')
                    except:
                        flash('Password change failed', 'danger')
                else:
                    flash('You got your old password wrong!', 'danger')
        
        # Change Daily Alert
        elif request.form.get('submit') == 'Change E-Mail':
            # Validate input
            valid = True
            email = request.form.get('email')
            print(request.form.get('dailyalert'))
            dailyalert = 1 if request.form.get('dailyalert') == 'on' else 0
            if email:
                if '@' not in email or '.' not in email:
                    flash('Invalid e-mail address', 'danger')
                    valid = False
            if valid:
                cursor.execute('UPDATE users SET email=%s, dailyalert=%s WHERE id=%s', [email, dailyalert, session['user_id']])
                conn.commit()
        
    # Open correct panel
    if request.method == 'GET':
        panel = int(request.args.get('panel')) if request.args.get('panel') else 0
    else:
        panel = int(request.form.get('panel')) if request.form.get('panel') else 0
    
    # Get email address
    cursor.execute('SELECT email, dailyalert FROM users WHERE id=%s', session['user_id'])
    user = cursor.fetchone()
    
    return render_template('controlpanel.html', portfolios=getPortfolio()[0], panel=panel, user=user)

# Route to schedule log and send daily e-mail
@app.route('/schedule')
def schedule():
    conn, cursor = dbConnect()

    # Get all users
    cursor.execute("SELECT id, email, dailyalert FROM users")
    users = cursor.fetchall()
    
    # Loop over users
    for user in users:
        # Prepare e-mail text
        html = '<!DOCTYPE html><html lang="en"><head><style>body{font-family:Helvetica,Arial,sans-serif;}td,th{padding:1px 7px;text-align:right;}th{font-weight:bold;}h3{margin-bottom:5px;}p{margin-top:5px;}</style></head><body><p>Here\'s an update on your portfolio after today\'s trading.</p>'
        plaintext = 'Here\'s an update on your portfolio after today\'s trading.\n'

        # Get all portfolios and shares
        cursor.execute('SELECT id, name FROM portfolios WHERE userid=%s', user['id'])
        portfolios = cursor.fetchall()
        session['user_id'] = user['id']
        
        # Loop over portfolios, get data and add to message
        for portfolio in portfolios:
            session['portfolio'] = portfolio['id']
            data = updateshareprices()
            content = json.loads(data.get_data())
            updated_shares = content[0]
            details = content[-1]
            html += '<h3>Portfolio: <a href="https://share-trader.herokuapp.com/?portfolio={}">{}</a></h3><p><strong>Market Exposure:</strong> {}<br /><strong>Profit:</strong> {} ({})<br /><strong>Daily Proft:</strong> {} ({})</p><table><thead><tr><th>EPIC</th><th>Target</th><th>Stop Loss</th><th>Bid Price</th><th>Daily</th><th>Value</th><th colspan="2">Profit/Loss</th></tr></thead><tbody>'.format(portfolio['id'], portfolio['name'], gbp(details['exposure']), gbp(details['profitloss']), percentage(details['percentage']), gbp(details['dailyprofit']), percentage(details['dailypercent']))
            plaintext += '\nPortfolio: {}\nMarket Exposure: {}\nProfit: {} ({})\nDaily Proft: {} ({})\n'.format(portfolio['name'], gbp(details['exposure']), gbp(details['profitloss']), percentage(details['percentage']), gbp(details['dailyprofit']), percentage(details['dailypercent']))
            for share in updated_shares:
                if share['portfolioid'] == session['portfolio']:
                    plaintext += '{}: {} ({}) {} {} {}\n'.format(share['epic'], shareprice(share['sellprice']), shareprice(share['sellprice'] - share['bidopen'], profitloss=True), gbp(share['value']), gbp(share['profitloss'], profitloss=True), percentage(share['percentage']))
                    html += '<tr><td><a href="https://share-trader.herokuapp.com/shares?submit=update&id={}">{}</a></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(share['id'], share['epic'], shareprice(share['target']), shareprice(share['stoploss']), shareprice(share['sellprice']), shareprice(share['sellprice'] - share['bidopen'], profitloss=True), gbp(share['value']), gbp(share['profitloss'], profitloss=True), percentage(share['percentage']))
            html += '</tbody></table>'
            session.pop('portfolio', None)
        plaintext += '\nTo stop receiving these updates, please update your settings at http://sharetrader.stevebunting.com/controlpanel?panel=1\n'
        html += '<p>To stop receiving these updates, please update your <a href="http://sharetrader.stevebunting.com/controlpanel?panel=1">settings</a>.</p></body></html>'
        session.pop('user_id', None)
        
        # Send e-mail if requested
        if user['dailyalert'] == 1 and user['email'] != '':
            msg = MIMEMultipart('alternative')
            msg.attach(MIMEText(plaintext, 'plain'))
            msg.attach(MIMEText(html, 'html'))
            msg['Subject'] = 'Stock portfolio update for {}'.format(dateFormat(datetime.datetime.now()))
            msg['From'] = 'sharetrader@stevebunting.com'
            msg['To'] = user['email']
            server = smtplib.SMTP('smtp.34sp.com', 587)
            server.login(smtpuser, smtppassword)
            server.sendmail('sharetrader@stevebunting.com', user['email'], msg.as_string())
            server.close()
    return 'True'

# Route to reset bidopen, scheduled for 5am every weekday
@app.route('/resetbidopen')
def resetbidopen():
    conn, cursor = dbConnect()

    cursor.execute('UPDATE shares SET bidopen=sellprice WHERE status=1')
    conn.commit()
    return 'true'

# Route to update share prices and return values as JSON for insertion by JS
@app.route('/updateshareprices', methods=['GET', 'POST'])
def updateshareprices():
    conn, cursor = dbConnect()

    # Get all active share data
    cursor.execute('SELECT * FROM shares WHERE userid=%s AND portfolioid=%s AND status=1 ORDER BY epic ASC', [session['user_id'], session['portfolio']])
    sharedata = cursor.fetchall()
    
    # Calculate new row values based on new quote data
    if not quoteLogin():
        return
    exposure = 0
    salevaluedelta = 0
    for i in range(cursor.rowcount):

        # Get new sell price
        sharedata[i]['sellprice'] = quote(sharedata[i]['epic'])
        if not sharedata[i]['sellprice']:
            return ''
        
        # Calculate share gain, value, profitloss, percentage
        sharedata[i]['sharegain'] = sharedata[i]['sellprice'] - sharedata[i]['bidopen']
        sharedata[i]['value'] = (sharedata[i]['sellprice'] * sharedata[i]['quantity'] * 0.01)
        costs = sharedata[i]['buytradecost'] + sharedata[i]['selltradecost'] + sharedata[i]['stampduty']
        sharedata[i]['profitloss'] = sharedata[i]['value'] - (sharedata[i]['buyprice'] * sharedata[i]['quantity'] * 0.01) - costs + sharedata[i]['dividends']
        sharedata[i]['percentage'] = ((10000 * (sharedata[i]['value'] - costs + sharedata[i]['dividends']) / (sharedata[i]['buyprice'] * sharedata[i]['quantity'])) - 100)
        
        # Add values to calculate totals
        exposure += sharedata[i]['value']
        salevaluedelta -= sharedata[i]['selltradecost']
        
        # Update db with new values
        cursor.execute('UPDATE shares SET sellprice=%s, value=%s, profitloss=%s, percentage=%s WHERE userid=%s AND id=%s AND portfolioid=%s',
            [sharedata[i]['sellprice'], sharedata[i]['value'], sharedata[i]['profitloss'], sharedata[i]['percentage'], session['user_id'], sharedata[i]['id'], session['portfolio']])
        conn.commit()
        
        # Calculate days held
        buyDatetime = verifyDate(sharedata[i]['buydate'], startofday=True)
        if sharedata[i]['selldate'] == None:
            sharedata[i]['daysHeld'] = (datetime.datetime.now(pytz.utc) - buyDatetime).days
        else:
            sellDatetime = verifyDate(sharedata[i]['selldate'], startofday=True)
            sharedata[i]['daysHeld'] = (sellDatetime - buyDatetime).days
    
    # Update exposure and lastupdated in portfolios db
    lastupdated = datetime.datetime.now(pytz.utc)
    cursor.execute('UPDATE portfolios SET exposure=%s, lastupdated=%s WHERE userid=%s AND id=%s', [exposure, lastupdated, session['user_id'], session['portfolio']])
    conn.commit()
    
    # Update log
    cursor.execute('SELECT * FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC LIMIT 1', [session['user_id'], session['portfolio']])
    lastlog = cursor.fetchone()
    ftse100 = quote('FTSE:UKX', 'price')

    # Calculate capital/cash
    assets = getAssets()
    
    # Log values
    date = datetime.datetime.utcnow()
    if not lastlog or lastlog['date'].strftime("%Y-%m-%d") == date.strftime("%Y-%m-%d") or lastlog['exposure'] != round(exposure, 2) or lastlog['ftse100'] != ftse100:
        if lastlog and lastlog['date'].strftime("%Y-%m-%d") == date.strftime("%Y-%m-%d"):
            cursor.execute('UPDATE log SET date=NOW(), exposure=%s, capital=%s, cash=%s, ftse100=%s WHERE id=%s', [exposure, assets['capital'], assets['cash'], ftse100, lastlog['id']])
        else:
            cursor.execute('INSERT INTO log (userid, portfolioid, exposure, capital, cash, ftse100) VALUES (%s, %s, %s, %s, %s, %s)', [session['user_id'], session['portfolio'], exposure, assets['capital'], assets['cash'], ftse100])
        cursor.execute('UPDATE portfolios SET lastlog=NOW() WHERE userid=%s AND id=%s', [session['user_id'], session['portfolio']])
        conn.commit()
    
    # Get log from 2 entries ago and todays buys to calculate daily performance
    cursor.execute('SELECT * FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC LIMIT 2', [session['user_id'], session['portfolio']])
    if cursor.rowcount == 2:
        prevdata = cursor.fetchall()[1]
        lastexposure = prevdata['exposure']
        lastcash = prevdata['cash']
    else:
        lastexposure = 0
        lastcash = assets['capital']
    
    # Calculate master details
    details = {
        'exposure': exposure,
        'salevalue': exposure + salevaluedelta,
        'profitloss': exposure + salevaluedelta + assets['cash'] - assets['capital'],
        'percentage': 0,
        'dailyprofit': exposure + assets['cash'] - lastexposure - lastcash,
        'dailypercent': 0,
        'lastupdated': lastupdated
    }
    if assets['capital'] != 0: details['percentage'] = (100 * ((exposure + salevaluedelta + assets['cash']) / assets['capital'])) - 100
    if exposure != 0: details['dailypercent'] = 100 * (details['dailyprofit'] / (exposure + assets['cash']))
    
    return jsonify([sharedata, details])

# Route to accept target/stop loss data back from index page to update database
# Returns new value (or current value if invalid entry)
@app.route('/updateindex', methods=['POST'])
def updateindex():
    conn, cursor = dbConnect()

    content = request.get_json()
    data = content[0].split('-')
    try:
        value = float(content[1])
        if data[2] == 'target':
            cursor.execute('UPDATE shares SET target=%s WHERE userid=%s AND portfolioid=%s AND id=%s', [value, session['user_id'], session['portfolio'], data[0]])
        elif data[2] == 'stoploss':
            cursor.execute('UPDATE shares SET stoploss=%s WHERE userid=%s AND portfolioid=%s AND id=%s', [value, session['user_id'], session['portfolio'], data[0]])
        conn.commit()
    except:
        cursor.execute('SELECT target, stoploss FROM shares WHERE userid=%s AND portfolioid=%s AND id=%s', [session['user_id'], session['portfolio'], data[0]])
        value = cursor.fetchone()[(data[2])]
    return str(value)

# Route to get all company data for open shares from database and return JSON
@app.route('/getepics')
def getsharedata():
    conn, cursor = dbConnect()

    cursor.execute('SELECT DISTINCT epic, company FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE status=1 AND userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
    return jsonify(cursor.fetchall())

# Route to get company name from database and return JSON
# Used for share page to dynamically update company name
@app.route('/getcompanyname', methods=['GET', 'POST'])
def company():
    conn, cursor = dbConnect()

    cursor.execute('SELECT * FROM companies WHERE symbol=%s', [request.args.get('epic')])
    data = cursor.fetchall()
    return jsonify(data)

# Route to change portfolio
@app.route('/portfoliochange', methods=['POST'])
def portfoliochange():
    conn, cursor = dbConnect()

    newportfolio = int(request.get_json())
    cursor.execute('UPDATE users SET lastportfolioid=%s WHERE id=%s', [newportfolio, session['user_id']])
    conn.commit()
    session['portfolio'] = newportfolio
    return 'true'

# Route to register new user
@app.route('/register', methods=['GET', 'POST'])
def register():
    conn, cursor = dbConnect()

    if request.method == 'POST':
        # Check for errors
        valid = False
        reg_username = ''
        if not request.form.get('reg_username'):
            flash('No username entered!', 'danger')
            
        elif not request.form.get('reg_password'):
            flash('No password entered!', 'danger')
            reg_username = request.form.get('reg_username')
            
        elif not request.form.get('reg_confirmpassword'):
            flash('You must confirm your password!', 'danger')
            reg_username = request.form.get('reg_username')
            
        elif request.form.get('reg_password') != request.form.get('reg_confirmpassword'):
            flash('Passwords must match', 'danger')
            reg_username = request.form.get('reg_username')
            
        else:
            valid = True
            
            # Insert new user into database and new portfolio
            try:
                cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)',
                    [request.form.get('reg_username'), pwd_context.encrypt(request.form.get('reg_password'))])
            except:
                flash('Username already taken, please choose another.', 'warning')
                valid = False
        
        if valid:
            # Add default portfolio
            id = cursor.lastrowid
            quoteLogin()
            ftse100 = quote('FTSE:UKX', 'price')
            cursor.execute('INSERT INTO portfolios (userid, name, ftse100) VALUES (%s, %s, %s)', [id, 'Main', ftse100])
            lastportfolioid = cursor.lastrowid
            cursor.execute('UPDATE users SET lastportfolioid=%s WHERE id=%s', [lastportfolioid, id])
            conn.commit()

            # Set user as logged in
            session['user_id'] = id
            session['username'] = request.form.get('reg_username')
            session['portfolio'] = lastportfolioid
            flash("Registered! Hello {}!".format(request.form.get('reg_username')), 'success')
    
    if not valid:
        return render_template('register.html', reg_username=reg_username)
    else:
        return redirect(url_for('index'))

# Route to log user in
@app.route('/login', methods=['GET', 'POST'])
def login():
    conn, cursor = dbConnect()

    if request.method == 'POST':
        # Check for errors
        valid = True
        if not request.form.get('login_username'):
            flash('No username entered!', 'danger')
            valid = False
        if not request.form.get('login_password'):
            flash('No password entered!', 'danger')
            valid = False
        
        if valid:
            # Check database for user
            cursor.execute('SELECT * FROM users WHERE username=%s', [request.form.get('login_username')])
            
            # If user in database
            if cursor.rowcount == 1:
                userdata = cursor.fetchone()
                
                # If password correct
                if pwd_context.verify(request.form.get('login_password'), userdata['password']):
                    
                    # Log user in
                    session['user_id'] = userdata['id']
                    session['username'] = request.form.get('login_username')
                    session['portfolio'] = userdata['lastportfolioid']
                    if request.form.get('login_remember') == 'on':
                        session['password'] = request.form.get('login_password')
                        session['rememberme'] = 1
                    else:
                        session.pop('password', None)
                        session.pop('rememberme', None)
                    flash('Logged in. Welcome back {}!'.format(request.form.get('login_username')), 'success')
                else:
                    flash('Incorrect password!', 'danger')
                    valid = False
            else:
                flash('Incorrect username!', 'danger')
                valid = False
    else:
        valid = False
    
    # Load index page
    if valid:
        return redirect(url_for('index'))
    else:
        return render_template('login.html')

# Route to logout
@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('portfolio', None)
    flash('Logged out!', 'success')
    return redirect(url_for('login'))