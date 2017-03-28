#!/usr/bin/env python3
# coding=utf-8

import datetime
import json

from flask import Flask, render_template, request, jsonify, flash, redirect, session, url_for
from flask_session import Session
from flaskext.mysql import MySQL
from pymysql.cursors import DictCursor

from passlib.apps import custom_app_context as pwd_context

import requests
from lxml import html

from functions import *

app = Flask(__name__)
app.config['MYSQL_DATABASE_HOST'] = 'localhost'
app.config['MYSQL_DATABASE_DB'] = 'sharetrader'
app.config['MYSQL_DATABASE_USER'] = 'sharetrader'
app.config['MYSQL_DATABASE_PASSWORD'] = 'st54'
app.secret_key = '%\xd1/\xc3\xdb2\xc1\x92#\xd5\xab\xfaq\x94\xd2\xdc\x81\x7f\xb6\xd2(i\x81f'
app.config['SESSION_TYPE'] = 'filesystem'
mysql = MySQL(app, cursorclass=DictCursor)
Session(app)

# Custom filters
app.jinja_env.filters['gbp'] = gbp
app.jinja_env.filters['shareprice'] = shareprice
app.jinja_env.filters['percentage'] = percentage
app.jinja_env.filters['dateFormat'] = dateFormat





def getPortfolio():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM portfolios WHERE userid=%s', [session['user_id']])
    portfolio = cursor.fetchall()
    for i in range(len(portfolio)):
        if portfolio[i]['id'] == session['portfolio']:
            return [i, portfolio]




        
@app.route('/')
@login_required
def index():
    portfolio = getPortfolio()
    portfolio_index, portfolio = portfolio[0], portfolio[1]
    portfolio[portfolio_index]['lastupdated'] = portfolio[portfolio_index]['lastupdated'].strftime('%a %d %b @ %I:%M:%S%p')
    
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolioid=%s AND status=1 ORDER BY epic ASC', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    details = {
        'market_exposure': 0,
        'sale_costs': 0
    }
    for row in data:
        details['market_exposure'] += row['sellprice'] * row['quantity'] * 0.01
        details['sale_costs'] += row['selltradecost']
    
    cursor.execute('SELECT * FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC LIMIT 2', [session['user_id'], session['portfolio']])
    daily = cursor.fetchall()[1]
    details['dailyprofit'] = details['market_exposure'] - daily['exposure']
    details['dailypercent'] = 100 * (details['dailyprofit'] / details['market_exposure'])
    
    return render_template('index.html', data=data, details=details, portfolio=portfolio, portfolio_index=portfolio_index)





@app.route('/shares', methods=['GET', 'POST'])
@login_required
def shares():
    portfolio = getPortfolio()
    portfolio_index, portfolio = portfolio[0], portfolio[1]
    
    # Create connection to MySQL DB
    conn = mysql.connect()
    cursor = conn.cursor()

    if request.method == 'POST':
    
        submit = request.form.get('submit')
        if request.form.get('id'):
            id = int(request.form.get('id'))
        else:
            id = None

        # If deleting an entry
        if submit == 'delete':
            cursor.execute('DELETE FROM shares WHERE id=%s AND userid=%s', [id, session['user_id']])
            conn.commit()
            cursor.execute('SELECT id FROM shares WHERE userid=%s ORDER BY id ASC', [session['user_id']])
            data = cursor.fetchall()
            j = 0
            if data[-1]['id'] < id:
                j = data[-1]['id']
            else:
                for i in range(len(data) - 1, -1, -1):
                    if data[i]['id'] > id:
                        j = data[i]['id']
            id = j
            submit = 'update'
            cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND id=%s AND portfolioid=%s', [session['user_id'], id, session['portfolio']])
            share = cursor.fetchone()
        
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
                'dividends': float(request.form.get('dividends')),
                'status': request.form.get('status'),
                'comment': request.form.get('comment')
            }
        
            # Dictionary of posted values to check, will be added to share dict
            # {field: [variable, type, require user entry, default]}
            values = {
                'buydate': [request.form.get('buydate'), 'date', False, datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S')],
                'selldate': [request.form.get('selldate'), 'date', False, None],
                'quantity': [request.form.get('quantity'), 'int', True, 0],
                'stampduty': [request.form.get('stampduty'), 'float', False, 0],
                'buytradecost': [request.form.get('buytradecost'), 'float', False, 0],
                'sellprice': [request.form.get('sellprice'), 'float', False, 0],
                'selltradecost': [request.form.get('selltradecost'), 'float', False, 0],
                'value': [request.form.get('value'), 'float', False, 0],
                'buyprice': [request.form.get('buyprice'), 'float', True, 0]
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
                        share[key] = str(datetime.datetime.strptime(val[0], '%Y-%m-%d %H:%M:%S'))
                except ValueError:
                    # If casting fails, revert to default value
                    # If input required for this field, input validation fails here
                    share[key] = val[3]
                    if val[2]:
                        inputValidation = False
        
            # Dictionary of values to check with defaults that depend on the last step
            defaults = {
                'buycost': [request.form.get('buycost'), 'float', False, share['quantity'] * share['buyprice'] * 0.01],
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
            
            share['profitloss'] = (share['quantity'] * (share['sellprice'] - share['buyprice']) * 0.01) - share['stampduty'] - share['buytradecost'] - share['selltradecost'] + share['dividends']
            share['percentage'] = ((10000 * (share['value'] - share['stampduty'] - share['buytradecost'] - share['selltradecost'] + share['dividends']) / (share['buyprice'] * share['quantity'])) - 100)
            
            # If input validated, try to write to database
            if inputValidation:
                goToIndex = 0
                data = [session['user_id'], session['portfolio'], share['epic'], share['status'], share['buydate'],
                        share['buyprice'], share['quantity'], share['stampduty'], share['buytradecost'],
                        share['buycost'], share['target'], share['stoploss'], share['selldate'], 
                        share['sellprice'], share['selltradecost'], share['value'], share['profitloss'],
                        share['percentage'], share['comment']]
        
                # If entering a new entry
                if submit == 'submit':
                    try:
                       goToIndex = cursor.execute('INSERT INTO shares (userid, portfolioid, epic, status, buydate, buyprice, quantity, stampduty, buytradecost, buycost, target, stoploss, selldate, sellprice, selltradecost, value, profitloss, percentage, comment) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', data)
                       conn.commit()
                    except:
                        pass
            
                # If updating an old entry
                elif submit == 'update':
                    data.append(request.form.get('id'))
                    try:
                        cursor.execute('UPDATE shares SET userid=%s, portfolioid=%s, epic=%s, status=%s, buydate=%s, buyprice=%s, quantity=%s, stampduty=%s, buytradecost=%s, buycost=%s, target=%s, stoploss=%s, selldate=%s, sellprice=%s, selltradecost=%s, value=%s, profitloss=%s, percentage=%s, comment=%s WHERE id=%s', data)
                        conn.commit()
                    except Exception as e:
                        flash(e)
                        pass
            
                # If entry succeeded, go to index else go back to edit page
                if goToIndex == 1:
                    return redirect(url_for('index'))
    
    elif request.method == 'GET':
          
        # Get submit and id variables
        submit = request.args.get('submit')
        id = request.args.get('id')
        
        # Verify submit/id and get share data from database if updating
        if submit != 'submit':
            submit = 'update'
            try:
                id = int(id)
            except TypeError:
                id = None
            if id:
                cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND id=%s AND portfolioid=%s', [session['user_id'], id, session['portfolio']])
            else:
                cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolioid=%s ORDER BY id DESC LIMIT 1', [session['user_id'], session['portfolio']])
            share = cursor.fetchone()
            id = share['id']
            if cursor.rowcount == 0:
                submit = 'submit'
    
    # Create 'nav' dictionary to store navigation variables
    # numEntries, previd, nextid, lastid
    nav = {}
    cursor.execute('SELECT id FROM shares WHERE userid=%s AND portfolioid=%s ORDER BY id ASC', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    nav['numEntries'] = cursor.rowcount
    nav['lastid'] = data[-1]['id']
    
    # Set some default values
    if submit == 'submit':
        id = None
        if request.method == 'GET':
            share = {
                'buydate': str(datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S'))
            }   
        share['daysHeld'] = None
        dividends = []
            
    elif submit == 'update':
        nav['index'] = data.index({'id': id}) + 1
        nav['previd'] = None if nav['index'] == 1 else data[nav['index'] - 2]['id']
        nav['nextid'] = None if nav['index'] == nav['numEntries'] else data[nav['index']]['id']
        
        buyDatetime = datetime.datetime.strptime(str(share['buydate']), '%Y-%m-%d %H:%M:%S')
        if share['selldate'] == None:
            share['daysHeld'] = (datetime.datetime.now() - buyDatetime).days
        else:
            sellDatetime = datetime.datetime.strptime(str(share['selldate']), '%Y-%m-%d %H:%M:%S')
            share['daysHeld'] = (sellDatetime - buyDatetime).days
        
        cursor.execute('SELECT date, amount FROM cash WHERE shareid=%s AND userid=%s AND portfolioid=%s ORDER BY date DESC', [id, session['user_id'], session['portfolio']])
        dividends = cursor.fetchall()
        
    return render_template('shares.html', nav=nav, share=share, submit=submit, portfolio=portfolio, portfolio_index=portfolio_index, dividends=dividends)





@app.route('/statement', methods=['GET'])
@login_required
def statement():
    portfolio = getPortfolio()
    portfolio_index, portfolio = portfolio[0], portfolio[1]
    
    statement = []
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    for row in data:
        statement.append({
            'id': row['id'],
            'date': row['buydate'],
            'transaction': row['company'].title(),
            'debit': row['buycost'],
            'credit': '',
            'notes': '',
            'type': 'buy'
        })
    cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolioid=%s AND status=0', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    for row in data:
        statement.append({
            'id': row['id'],
            'date': row['selldate'],
            'transaction': row['company'].title(),
            'debit': '',
            'credit': row['value'],
            'notes': '',
            'type': 'sell'
        })
    cursor.execute('SELECT * FROM cash INNER JOIN cash_categories ON cash.categoryid=cash_categories.id WHERE userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    for row in data:
        transaction = {
            'id': row['shareid'],
            'date': row['date'],
            'transaction': 'Cash: {}'.format(row['category']),
            'debit': '',
            'credit': '',
            'notes': row['notes'],
            'type': row['categoryid']
        }
        if row['amount'] > 0:
            transaction['credit'] = row['amount']
        else:
            transaction['debit'] = row['amount'] * -1
        statement.append(transaction)
    statement = sorted(statement, key=lambda k: k['date'])
    balance = 0
    for row in statement:
        if row['credit']:
            row['balance'] = balance + row['credit']
        else:
            row['balance'] = balance - row['debit']
        balance = row['balance']
    statement = sorted(statement, key=lambda k: k['date'], reverse=True)
    return render_template('statement.html', statement=statement, portfolio=portfolio, portfolio_index=portfolio_index)





@app.route('/cash', methods=['GET', 'POST'])
@login_required
def cash():
    portfolio = getPortfolio()
    portfolio_index, portfolio = portfolio[0], portfolio[1]
    
    if request.method == 'POST':
        
        conn = mysql.connect()
        cursor = conn.cursor()
        
        # Error checking
        try:
            cash_amount = float(request.form.get('cash_amount'))
        except TypeError:
            return redirect(url_for('cash'))
        
        if request.form.get('cash_category') == '2' and request.form.get('sharedividend'):
            epic = request.form.get('sharedividend')
            cursor.execute('SELECT id, quantity FROM shares WHERE epic=%s AND status=1 AND userid=%s AND portfolioid=%s', [epic, session['user_id'], session['portfolio']])
            data = cursor.fetchall()
            total = 0
            for i in data:
                total += int(i['quantity'])
            for i in data:
                ratio = i['quantity'] / total
                cursor.execute('INSERT INTO cash (userid, portfolioid, amount, categoryid, shareid, notes, date) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    [session['user_id'], session['portfolio'], cash_amount * ratio, request.form.get('cash_category'), i['id'], request.form.get('cash_notes'), request.form.get('cash_date')])
                cursor.execute('UPDATE shares SET dividends=dividends+%s WHERE id=%s AND userid=%s AND portfolioid=%s',
                    [cash_amount * ratio, i['id'], session['user_id'], session['portfolio']])
                conn.commit()
        else:
            shareid = None
            cursor.execute('INSERT INTO cash (userid, portfolioid, amount, categoryid, shareid, notes, date) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                [session['user_id'], session['portfolio'], cash_amount, request.form.get('cash_category'), shareid, request.form.get('cash_notes'), request.form.get('cash_date')])
            conn.commit()
            
        
        # Update users capital invested        
        if request.form.get('cash_category') == '1':
            cursor.execute('UPDATE portfolios SET capital=capital+%s WHERE userid=%s AND id=%s',
                [cash_amount, session['user_id'], session['portfolio']])
            conn.commit()

        # Update user's cash
        cursor.execute('SELECT SUM(buycost) AS debit FROM shares WHERE userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
        debitdata = cursor.fetchone()
        cursor.execute('SELECT SUM(value) AS credit FROM shares WHERE userid=%s AND portfolioid=%s and status=0', [session['user_id'], session['portfolio']])
        creditdata = cursor.fetchone()
        cursor.execute('SELECT SUM(amount) AS cash FROM cash WHERE userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
        cashdata = cursor.fetchone()
        cash = creditdata['credit'] - debitdata['debit'] + cashdata['cash']
        cursor.execute('UPDATE portfolios SET cash=%s WHERE userid=%s AND id=%s',
                    [cash, session['user_id'], session['portfolio']])
        conn.commit()
        
        if request.form.get('cash_category') == '1':
            cursor.execute('UPDATE log SET cash=cash+%s, capital=capital+%s WHERE date>=%s AND userid=%s AND portfolioid=%s',
                        [cash_amount, cash_amount, request.form.get('cash_date'), session['user_id'], session['portfolio']])
            conn.commit()
        else:
            cursor.execute('UPDATE log SET cash=cash+%s WHERE date>=%s AND userid=%s AND portfolioid=%s',
                        [cash_amount, request.form.get('cash_date'), session['user_id'], session['portfolio']])
            conn.commit()

        return redirect(url_for('cash'))
            
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cash_categories')
    cash_categories = cursor.fetchall()
            
    if request.method == 'GET':
        return render_template('cash.html', cash_categories=cash_categories, portfolio=portfolio, portfolio_index=portfolio_index)





@app.route('/log')
@login_required
def log():
    portfolio = getPortfolio()
    portfolio_index, portfolio = portfolio[0], portfolio[1]
    
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC', [session['user_id'], session['portfolio']])
    log = cursor.fetchall()
    cursor.execute('SELECT ftse100 FROM portfolios WHERE userid=%s AND id=%s', [session['user_id'], session['portfolio']])
    ftse100base = cursor.fetchone()['ftse100']
    
    # Update capital/cash in logging
    """for i in range(len(log)):
        cursor.execute('SELECT SUM(amount) AS capital FROM cash WHERE categoryid=1 AND date<=%s AND userid=%s AND portfolioid=%s', [log[i]['date'], session['user_id'], session['portfolio']])
        capital = float(cursor.fetchone()['capital'])
        cursor.execute('SELECT SUM(amount) AS csh FROM cash WHERE date<=%s AND userid=%s AND portfolioid=%s', [log[i]['date'], session['user_id'], session['portfolio']])
        cash = float(cursor.fetchone()['csh'])
        cursor.execute('SELECT SUM(buycost) AS buys FROM shares WHERE buydate<=%s AND userid=%s AND portfolioid=%s', [log[i]['date'], session['user_id'], session['portfolio']])
        buys = float(cursor.fetchone()['buys'])
        cursor.execute('SELECT SUM(value) AS sells FROM shares WHERE selldate<=%s AND userid=%s AND portfolioid=%s', [log[i]['date'], session['user_id'], session['portfolio']])
        sells = float(cursor.fetchone()['sells'])
        cursor.execute('UPDATE log SET capital=%s, cash=%s WHERE id=%s', [capital, cash - buys + sells, log[i]['id']])
        conn.commit()"""
    
    return render_template('log.html', log=log, portfolio=portfolio, portfolio_index=portfolio_index, ftse100base=ftse100base)





@app.route('/controlpanel', methods=['GET', 'POST'])
@login_required
def controlpanel():
    portfolio = getPortfolio()
    portfolio_index, portfolio = portfolio[0], portfolio[1]
    
    conn = mysql.connect()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        if request.form.get('submit') == 'Delete':
            cursor.execute('DELETE FROM portfolios WHERE id=%s AND userid=%s', [request.form.get('id'), session['user_id']])
            conn.commit()
        
        elif request.form.get('submit') == 'Add':
            valid = True
            if not request.form.get('addportfolioname'):
                valid = False
            else:
                for i in portfolio:
                    if i['name'].lower() == request.form.get('addportfolioname').lower():
                        valid = False
                        break
            if valid:
                quoteLogin()
                ftse100 = quote('UKX', 'price')
                cursor.execute('INSERT INTO portfolios (userid, name, ftse100) VALUES (%s, %s, %s)', [session['user_id'], request.form.get('addportfolioname'), ftse100])
                conn.commit()
        
        elif request.form.get('submit') == 'Rename':
            valid = True
            if not request.form.get('rename'):
                valid = False
            else:
                for i in portfolio:
                    if i['name'].lower() == request.form.get('rename').lower():
                        valid = False
                        break
            if valid:
                cursor.execute('UPDATE portfolios SET name=%s WHERE userid=%s AND id=%s', [request.form.get('rename'), session['user_id'], request.form.get('id')])
                conn.commit()
            
        portfolio = getPortfolio()
        portfolio_index, portfolio = portfolio[0], portfolio[1]
    
    cursor.execute('SELECT username FROM users WHERE id=%s', [session['user_id']])
    username = cursor.fetchone()['username']
    
    return render_template('controlpanel.html', username=username, portfolio=portfolio, portfolio_index=portfolio_index)





@app.route('/updatesharedata')
def updatesharedata():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT id, epic, buyprice, quantity, stampduty, buytradecost, selltradecost, value, dividends, profitloss, percentage FROM shares WHERE userid=%s AND portfolioid=%s AND status=1 ORDER BY epic ASC', [session['user_id'], session['portfolio']])
    sharedata = cursor.fetchall()
    
    # Calculate new row values based on new quote data
    quoteLogin()
    exposure = 0
    salevaluedelta = 0
    for i in range(cursor.rowcount):
        sharedata[i]['sellprice'] = quote(sharedata[i]['epic'])
        sharedata[i]['value'] = (sharedata[i]['sellprice'] * sharedata[i]['quantity'] * 0.01)
        exposure += sharedata[i]['value']
        
        costs = sharedata[i]['buytradecost'] + sharedata[i]['selltradecost'] + sharedata[i]['stampduty']
        salevaluedelta -= sharedata[i]['selltradecost']
        sharedata[i]['profitloss'] = sharedata[i]['value'] - (sharedata[i]['buyprice'] * sharedata[i]['quantity'] * 0.01) - costs + sharedata[i]['dividends']
        sharedata[i]['percentage'] = ((10000 * (sharedata[i]['value'] - costs + sharedata[i]['dividends']) / (sharedata[i]['buyprice'] * sharedata[i]['quantity'])) - 100)
        if sharedata[i]['sellprice'] == False:
            return ''
        
        # Add new values to db
        cursor.execute('UPDATE shares SET sellprice=%s, value=%s, profitloss=%s, percentage=%s WHERE userid=%s AND id=%s AND portfolioid=%s',
            [sharedata[i]['sellprice'], sharedata[i]['value'], sharedata[i]['profitloss'], sharedata[i]['percentage'], session['user_id'], sharedata[i]['id'], session['portfolio']])
        conn.commit()
    
    # Update exposure and lastupdated in portfolios db
    date = datetime.datetime.now()
    cursor.execute('UPDATE portfolios SET exposure=%s, lastupdated=NOW() WHERE userid=%s AND id=%s', [exposure, session['user_id'], session['portfolio']])
    conn.commit()
    
    # Update log
    cursor.execute('SELECT * FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC LIMIT 1', [session['user_id'], session['portfolio']])
    lastlog = cursor.fetchone()
    ftse100 = quote('UKX', 'price')

    # Calculate capital/cash
    cursor.execute('SELECT SUM(amount) AS capital FROM cash WHERE categoryid=1 AND date<=%s AND userid=%s AND portfolioid=%s', [date, session['user_id'], session['portfolio']])
    capital = float(cursor.fetchone()['capital'])
    cursor.execute('SELECT SUM(amount) AS csh FROM cash WHERE date<=%s AND userid=%s AND portfolioid=%s', [date, session['user_id'], session['portfolio']])
    cash = float(cursor.fetchone()['csh'])
    cursor.execute('SELECT SUM(buycost) AS buys FROM shares WHERE buydate<=%s AND userid=%s AND portfolioid=%s', [date, session['user_id'], session['portfolio']])
    cash -= float(cursor.fetchone()['buys'])
    cursor.execute('SELECT SUM(value) AS sells FROM shares WHERE selldate<=%s AND userid=%s AND portfolioid=%s', [date, session['user_id'], session['portfolio']])
    cash += float(cursor.fetchone()['sells'])
    
    if lastlog['date'].strftime("%Y-%m-%d") == date.strftime("%Y-%m-%d") or lastlog['exposure'] != exposure or lastlog['ftse100'] != ftse100:
        if lastlog['date'].strftime("%Y-%m-%d") == date.strftime("%Y-%m-%d"):
            cursor.execute('UPDATE log SET exposure=%s, capital=%s, cash=%s, ftse100=%s WHERE id=%s', [exposure, capital, cash, ftse100, lastlog['id']])
        else:
            cursor.execute('INSERT INTO log (userid, portfolioid, exposure, capital, cash, ftse100) VALUES (%s, %s, %s, %s, %s, %s)', [session['user_id'], session['portfolio'], exposure, capital, cash, ftse100])
        cursor.execute('UPDATE portfolios SET lastlog=NOW() WHERE userid=%s AND id=%s', [session['user_id'], session['portfolio']])
        conn.commit()
    
    # Calculate master details
    cursor.execute('SELECT * FROM log WHERE userid=%s AND portfolioid=%s ORDER BY date DESC LIMIT 2', [session['user_id'], session['portfolio']])
    daily = cursor.fetchall()[1]
    details = {
        'exposure': exposure,
        'salevalue': exposure + salevaluedelta,
        'profitloss': exposure + salevaluedelta + cash - capital,
        'percentage': (100 * ((exposure + salevaluedelta + cash) / capital)) - 100,
        'dailyprofit': exposure - daily['exposure'],
        'dailypercent': 100 * ((exposure - daily['exposure']) / exposure)
    }
    return jsonify([sharedata, details])





# Route to accept target/stop loss data back from index page to update database
@app.route('/updateindex', methods=['POST'])
def updateindex():
    content = request.get_json()
    data = content[0].split('-')
    try:
        value = float(content[1])
        conn = mysql.connect()
        cursor = conn.cursor()
        if data[2] == 'target':
            cursor.execute('UPDATE shares SET target=%s WHERE userid=%s AND portfolioid=%s AND id=%s', [value, session['user_id'], session['portfolio'], data[0]])
        elif data[2] == 'stoploss':
            cursor.execute('UPDATE shares SET stoploss=%s WHERE userid=%s AND portfolioid=%s AND id=%s', [value, session['user_id'], session['portfolio'], data[0]])
        conn.commit()
    except:
        pass
    return 'true'





@app.route('/getsharedata')
def getsharedata():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT epic, company FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE status=1 AND userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
    sharedata = cursor.fetchall()
    return jsonify(sharedata)





@app.route('/company')
def company():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM companies WHERE symbol=%s', [request.args.get('epic')])
    data = cursor.fetchall()
    return jsonify(data)





@app.route('/portfoliochange', methods=['GET', 'POST'])
def portfoliochange():
    newportfolio = int(request.get_json())
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET lastportfolioid=%s WHERE id=%s', [newportfolio, session['user_id']])
    conn.commit()
    session['portfolio'] = newportfolio
    return 'true'





@app.route('/register', methods=['GET', 'POST'])
def register():
        
    # Check for errors
    if not request.form.get('reg_username'):
        return render_template('register.html', reg_username='')
    elif not request.form.get('reg_password') or not request.form.get('reg_confirmpassword') or request.form.get('reg_password') != request.form.get('reg_confirmpassword'):
        return render_template('register.html', reg_username=request.form.get('reg_username'))
    
    # Insert new user into database and new portfolio
    conn = mysql.connect()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)',
            [request.form.get('reg_username'), pwd_context.encrypt(request.form.get('reg_password'))])
    except:
        # Username already taken
        flash('Username already taken')
        return render_template('register.html', reg_username='')
    conn.commit()
    
    # Add default portfolio
    id = cursor.lastrowid
    quoteLogin()
    ftse100 = quote('UKX', 'price')
    cursor.execute('INSERT INTO portfolio (userid, name, ftse100) VALUES (%s, %s, %s)', [id, 'Main', ftse100])
    lastportfolioid = cursor.lastrowid
    cursor.execute('UPDATE users SET lastportfolioid=%s WHERE id=%s', [lastportfolioid, id])
    conn.commit()
    
    # Set user as logged in
    session['user_id'] = id
    session['portfolio'] = lastportfolioid
    flash("Registered! Hello {}!".format('username'))
    
    # Load index page
    return redirect(url_for('index'))





@app.route('/login', methods=['GET', 'POST'])
def login():
    
    # Check for errors
    if not request.form.get('login_username') or not request.form.get('login_password'):
        return render_template('login.html')
    
    # Check database for user
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username=%s', [request.form.get('login_username')])
    
    if cursor.rowcount == 1:
        data = cursor.fetchone()
        if pwd_context.verify(request.form.get('login_password'), data['password']):
            session['user_id'] = data['id']
            session['username'] = request.form.get('login_username')
            if request.form.get('login_remember') == 'on':
                session['password'] = request.form.get('login_password')
                session['rememberme'] = 1
                session['portfolio'] = data['lastportfolioid']
            else:
                session.pop('username', None)
                session.pop('password', None)
                session.pop('rememberme', None)
                session.pop('portfolio', None)
            flash('Logged in. Welcome back {}.'.format(request.form.get('login_username')))
    
    # Load index page
    return redirect(url_for('index'))





@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user_id', None)
    session.pop('portfolio', None)
    flash('Logged out')
    return redirect(url_for('login'))