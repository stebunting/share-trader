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

@app.route('/')
@login_required
def index():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolio=%s AND status=1 ORDER BY epic ASC', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    cursor.execute('SELECT * FROM portfolio WHERE userid=%s AND portfolioid=%s', [session['user_id'], session['portfolio']])
    portfolio = cursor.fetchone()
    details = {
        'market_exposure': 0,
        'sale_costs': 0
    }
    for row in data:
        details['market_exposure'] += row['sellprice'] * row['quantity'] * 0.01
        details['sale_costs'] += row['selltradecost']
    
    lastupdated = portfolio['lastupdated'].strftime('%a %d %b @ %I:%M:%S')
    
    return render_template('index.html', data=data, details=details, portfolio=portfolio, lastupdated=lastupdated)






@app.route('/shares', methods=['GET', 'POST'])
@login_required
def shares():
    
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
            cursor.execute('DELETE FROM shares WHERE id=%s', [id])
            conn.commit()
            cursor.execute('SELECT id FROM shares ORDER BY id ASC')
            data = cursor.fetchall()
            j = 0
            if data[-1]['id'] < id:
                j = data[-1]['id']
            else:
                for i in range(len(data) - 1, -1, -1):
                    print(data[i]['id'])
                    if data[i]['id'] > id:
                        j = data[i]['id']
            id = j
            submit = 'update'
            cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND id=%s AND portfolio=%s', [session['user_id'], id, session['portfolio']])
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
                'totalsale': [request.form.get('totalsale'), 'float', False, 0],
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
                'stoploss': [request.form.get('stoploss'), 'float', False, share['buyprice'] * 0.9],
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
            
            # If input validated, try to write to database
            if inputValidation:
                goToIndex = 0
                data = [session['user_id'], 1, share['epic'], share['status'], share['buydate'],
                        share['buyprice'], share['quantity'], share['stampduty'], share['buytradecost'],
                        share['buycost'], share['target'], share['stoploss'], share['selldate'], 
                        share['sellprice'], share['selltradecost'], share['totalsale'], share['comment']]
        
                # If entering a new entry
                if submit == 'submit':
                    try:
                       goToIndex = cursor.execute('INSERT INTO shares (userid, portfolio, epic, status, buydate, buyprice, quantity, stampduty, buytradecost, buycost, target, stoploss, selldate, sellprice, selltradecost, totalsale, comment) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', data)
                       conn.commit()
                    except:
                        pass
            
                # If updating an old entry
                elif submit == 'update':
                    data.append(request.form.get('id'))
                    try:
                        cursor.execute('UPDATE shares SET userid=%s, portfolio=%s, epic=%s, status=%s, buydate=%s, buyprice=%s, quantity=%s, stampduty=%s, buytradecost=%s, buycost=%s, target=%s, stoploss=%s, selldate=%s, sellprice=%s, selltradecost=%s, totalsale=%s, comment=%s WHERE id=%s', data)
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
                cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND id=%s AND portfolio=%s', [session['user_id'], id, session['portfolio']])
            else:
                cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolio=%s ORDER BY id DESC LIMIT 1', [session['user_id'], session['portfolio']])
            share = cursor.fetchone()
            id = share['id']
            if cursor.rowcount == 0:
                submit = 'submit'
    
    # Create 'nav' dictionary to store navigation variables
    # numEntries, previd, nextid, lastid
    nav = {}
    cursor.execute('SELECT id FROM shares WHERE userid=%s AND portfolio=%s ORDER BY id ASC', [session['user_id'], session['portfolio']])
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
        
    return render_template('shares.html', nav=nav, share=share, submit=submit)





@app.route('/statement', methods=['GET'])
@login_required
def statement():
    statement = []
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolio=%s AND buydate>0', [session['user_id'], session['portfolio']])
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
    cursor.execute('SELECT * FROM shares INNER JOIN companies ON shares.epic=companies.symbol WHERE userid=%s AND portfolio=%s AND selldate>0', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    for row in data:
        statement.append({
            'id': row['id'],
            'date': row['selldate'],
            'transaction': row['company'].title(),
            'debit': '',
            'credit': row['totalsale'],
            'notes': '',
            'type': 'sell'
        })
    cursor.execute('SELECT * FROM cash INNER JOIN cash_categories ON cash.categoryid=cash_categories.id WHERE userid=%s', [session['user_id']])
    data = cursor.fetchall()
    for row in data:
        transaction = {
            'id': row['id'],
            'date': row['date'],
            'transaction': 'Cash: {}'.format(row['category']),
            'debit': '',
            'credit': '',
            'notes': row['notes'],
            'type': 'cash'
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
    return render_template('statement.html', statement=statement)

@app.route('/cash', methods=['GET', 'POST'])
@login_required
def cash():
    if request.method == 'POST':
        
        # Error checking
        try:
            cash_amount = float(request.form.get('cash_amount'))
        except TypeError:
            return redirect(url_for('cash'))
        
        conn = mysql.connect()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO cash (userid, amount, categoryid, notes, date) VALUES (%s, %s, %s, %s, %s)',
            [session['user_id'], cash_amount, request.form.get('cash_category'), request.form.get('cash_notes'), request.form.get('cash_date')])
        conn.commit()

        # Update users capital invested        
        if request.form.get('cash_category') == '1':
            cursor.execute('UPDATE portfolio SET portfoliocapital=portfoliocapital+%s WHERE userid=%s AND portfolioid=1',
                [cash_amount, session['user_id']])
            conn.commit()

        # Update user's cash
        cursor.execute('SELECT SUM(buycost) AS debit FROM shares WHERE userid=%s AND portfolio=%s', [session['user_id'], session['portfolio']])
        debitdata = cursor.fetchone()
        cursor.execute('SELECT SUM(totalsale) AS credit FROM shares WHERE userid=%s AND portfolio=%s and status=0', [session['user_id'], session['portfolio']])
        creditdata = cursor.fetchone()
        cursor.execute('SELECT SUM(amount) AS cash FROM cash WHERE userid=%s', [session['user_id']])
        cashdata = cursor.fetchone()
        cash = creditdata['credit'] - debitdata['debit'] + cashdata['cash']
        cursor.execute('UPDATE portfolio SET portfoliocash=%s WHERE userid=%s AND portfolioid=1',
                    [cash, session['user_id']])
        conn.commit()

        return redirect(url_for('cash'))
            
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cash_categories')
    cash_categories = cursor.fetchall()
            
    if request.method == 'GET':
        return render_template('cash.html', cash_categories=cash_categories)
    

@app.route('/log')
@login_required
def log():
    return render_template('log.html')

@app.route('/updatesharedata')
def symbols():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM shares WHERE userid=%s AND portfolio=%s AND status=1 ORDER BY epic ASC', [session['user_id'], session['portfolio']])
    data = cursor.fetchall()
    
    payload = {
        'login_username': 'sharetrader6',
        'login_password': 'st54st54',
        'redirect_url': 'aHR0cDovL3VrLmFkdmZuLmNvbS9jb21tb24vYWNjb3VudC9sb2dpbg==',
        'site': 'uk'
    }
    session_requests = requests.session()
    result = session_requests.get('http://uk.advfn.com/common/account/login')
    tree = html.fromstring(result.text)
    payload['redirect_url'] = list(set(tree.xpath("//input[@name='redirect_url']/@value")))[0]
    result = session_requests.post(
        'https://secure.advfn.com/login/secure', 
        data = payload, 
        headers = dict(referer='http://uk.advfn.com/common/account/login')
    )
    for i in range(cursor.rowcount):
        data[i]['bid'] = quote(data[i]['epic'])
    return jsonify(data)

# Route to accept share data back from Javascript to update database
@app.route('/updatedb', methods=['POST'])
def update():
    content = request.get_json()
    conn = mysql.connect()
    cursor = conn.cursor()
    for row in content:
        cursor.execute('UPDATE shares SET sellprice=%s, totalsale=%s, profitloss=%s, percentage=%s WHERE userid=%s AND id=%s',
            [row['bid'], row['value'], row['profitloss'], row['percentage'], session['user_id'], row['id']])
        cursor.execute('UPDATE portfolio SET lastupdated=NOW() WHERE userid=%s AND portfolioid=1', [session['user_id']])
        conn.commit()
    return '1'

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
            cursor.execute('UPDATE shares SET target=%s WHERE id=%s', [value, data[0]])
        elif data[2] == 'stoploss':
            cursor.execute('UPDATE shares SET stoploss=%s WHERE id=%s', [value, data[0]])
        conn.commit()
    except:
        pass
    return '1'

@app.route('/company')
def company():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM companies WHERE symbol=%s', [request.args.get('epic')])
    data = cursor.fetchall()
    return jsonify(data)

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
        print("HELLO")
        cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)',
            [request.form.get('reg_username'), pwd_context.encrypt(request.form.get('reg_password'))])
    except:
        # Username already taken
        flash('Username already taken')
        return render_template('register.html', reg_username='')
    conn.commit()
    
    # Add default portfolio
    id = cursor.lastrowid
    cursor.execute('INSERT INTO portfolio (userid, portfolioname) VALUES (%s, %s)', [id, 'Main'])
    defaultportfolio = cursor.lastrowid
    cursor.execute('UPDATE users SET defaultportfolio=%s WHERE id=%s', [defaultportfolio, id])
    conn.commit()
    
    # Set user as logged in
    session['user_id'] = id
    session['portfolio'] = defaultportfolio
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
                session['portfolio'] = data['defaultportfolio']
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
    flash('Logged out')
    return redirect(url_for('login'))