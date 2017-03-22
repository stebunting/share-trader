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
    cursor.execute('SELECT * FROM shares WHERE userid=%s AND portfolio=1 AND status=1 ORDER BY epic ASC', [session['user_id']])
    data = cursor.fetchall()
    cursor.execute('SELECT * FROM portfolio WHERE userid=%s AND portfolioid=1', [session['user_id']])
    portfolio = cursor.fetchone()
    details = {
        'market_exposure': 0,
        'sale_costs': 0
    }
    for row in data:
        details['market_exposure'] += row['sellprice'] * row['quantity'] * 0.01
        details['sale_costs'] += row['selltradecost']
    return render_template('index.html', data=data, details=details, portfolio=portfolio)

@app.route('/shares', methods=['GET', 'POST'])
@login_required
def shares():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT company, market, sector, subsector FROM companylist ORDER BY company ASC')
    companies = cursor.fetchall()
        
    if request.method == 'POST':
        if request.form.get('submit') == 'delete':
            cursor.execute('DELETE FROM shares WHERE id=%s', [request.form.get('id')])
            conn.commit()
            return redirect(url_for('index'))
        
        elif request.form.get('submit') == 'submit':
            valid = True
            
            # Dictionary of posted values
            # {field: [variable, type, require user entry, default]}
            values = {
                'buydate': [request.form.get('buydate'), 'date', False, str(datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S'))],
                'selldate': [request.form.get('selldate'), 'date', False, '0000-00-00 00:00:00'],
                'quantity': [request.form.get('quantity'), 'int', True, 0],
                'stampduty': [request.form.get('stampduty'), 'float', False, 0],
                'buytradecost': [request.form.get('buytradecost'), 'float', False, 0],
                'sellprice': [request.form.get('sellprice'), 'float', False, 0],
                'selltradecost': [request.form.get('selltradecost'), 'float', False, 0],
                'totalsale': [request.form.get('totalsale'), 'float', False, 0],
                'buyprice': [request.form.get('buyprice'), 'float', True, 0]
            }
            
            share = {}
            for key, val in values.items():
                try:
                    if val[1] == 'float' or val[1] == 'int':
                        share[key] = float(val[0])
                        if val[1] == 'int':
                            share[key] = int(float(val[0]))
                    if val[1] == 'date':
                        print(datetime.datetime.strptime(val[0], '%Y-%m-%d'))
                except ValueError:
                    share[key] = val[3]
                    if val[2]:
                        valid = False
                        
            defaults = {
                'buycost': [request.form.get('buycost'), 'float', False, share['quantity'] * share['buyprice'] * 0.01],
                'target': [request.form.get('target'), 'float', False, share['buyprice'] * 1.2],
                'stoploss': [request.form.get('stoploss'), 'float', False, share['buyprice'] * 0.9],
            }
            
            for key, val in defaults.items():
                try:
                    share[key] = float(val[0])
                    if val[1] == 'int':
                        share[key] = int(float(val[0]))
                except ValueError:
                    if valid:
                        share[key] = val[3]
                    else:
                        share[key] = 0
                    if val[2]:
                        valid = False
            
            share = {**share, **{
                'epic': request.form.get('epic'),
                'company': request.form.get('company'),
                'status': request.form.get('status'),
                'comment': request.form.get('comment')
            }}
            flash(valid)
            if valid:
                data = [session['user_id'], 1, share['epic'], share['company'], share['status'],
                        share['buydate'], share['buyprice'], share['quantity'], share['stampduty'],
                        share['buytradecost'], share['buycost'], share['target'], share['stoploss'],
                        share['sellprice'], share['selltradecost'], share['totalsale'], share['comment']]
                        
                try:
                   cursor.execute('INSERT INTO shares (userid, portfolio, epic, company, status, buydate, buyprice, quantity, stampduty, buytradecost, buycost, target, stoploss, sellprice, selltradecost, totalsale, comment) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', data)
                   conn.commit()
                except Exception as e:
                    flash(e)
                    valid = False
            
            if valid:
               return redirect(url_for('index'))
            else:    
                return render_template('shares.html', companies=companies, share=share)
            
        elif request.form.get('submit') == 'update':
            data = [request.form.get('status'), request.form.get('buydate'), request.form.get('buyprice'),
                request.form.get('stampduty'), request.form.get('buytradecost'), request.form.get('buycost'),
                request.form.get('target'), request.form.get('stoploss'), request.form.get('selldate'),
                request.form.get('sellprice'), request.form.get('selltradecost'), request.form.get('totalsale'),
                request.form.get('comment')]
            #cursor.execute('UPDATE shares (status, buydate, buyprice, stampduty, buytradecost, buycost, target, stoploss, selldate, sellprice, selltradecost, totalsale, comment) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) WHERE id=%s',
            #    data)
            return str(data)
        print(data)
        

    elif request.method == 'GET':
        try:
            id = int(request.args.get('id'))
            cursor.execute('SELECT * FROM shares INNER JOIN companylist ON shares.company=companylist.company WHERE userid=%s AND id=%s', [session['user_id'], id])
            share = cursor.fetchall()
            numRows = len(share)
        except TypeError:
            numRows = 0
        if numRows == 0:
            share = [False]
        if numRows == 0:
            daysHeld = ''
        elif not share[0]['selldate']:
            daysHeld = (datetime.datetime.now() - share[0]['buydate']).days
        else:
            daysHeld = (share[0]['selldate'] - share[0]['buydate']).days
        return render_template('shares.html', companies=companies, share=share[0], daysHeld=daysHeld)

@app.route('/submit', methods=['POST'])
def submit():
    flash('Added')
    return "hello"

@app.route('/statement')
@login_required
def statement():
    statement = []
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM shares WHERE userid=%s AND portfolio=1 AND buydate>0', [session['user_id']])
    data = cursor.fetchall()
    for row in data:
        statement.append({
            'id': row['id'],
            'date': row['buydate'],
            'company': row['company'].title(),
            'debit': row['buycost'],
            'credit': '',
            'notes': '',
            'type': 'buy'
        })
    cursor.execute('SELECT * FROM shares WHERE userid=%s AND portfolio=1 AND selldate>0', [session['user_id']])
    data = cursor.fetchall()
    for row in data:
        statement.append({
            'id': row['id'],
            'date': row['selldate'],
            'company': row['company'].title(),
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
            'company': 'Cash: {}'.format(row['category']),
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
        cursor.execute('SELECT SUM(buycost) AS debit FROM shares WHERE userid=%s AND portfolio=1', [session['user_id']])
        debitdata = cursor.fetchone()
        cursor.execute('SELECT SUM(totalsale) AS credit FROM shares WHERE userid=%s AND portfolio=1 and status=0', [session['user_id']])
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
    
    

@app.route('/symbols')
def symbols():
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM shares WHERE userid=%s AND portfolio=1 AND status=1 ORDER BY epic ASC', [session['user_id']])
    data = cursor.fetchall()
    return jsonify(data)

@app.route('/update', methods=['POST'])
def update():
    content = request.get_json()
    conn = mysql.connect()
    cursor = conn.cursor()
    cursor.execute('UPDATE shares SET sellprice=%s, totalsale=%s, profitloss=%s, percentage=%s WHERE userid=%s AND id=%s',
        [content['bid'], content['value'], content['profitloss'], content['percentage'], session['user_id'], content['id']])
    cursor.execute('UPDATE portfolio SET lastupdated=NOW() WHERE userid=%s AND portfolioid=1', [session['user_id']])
    conn.commit()
    return '1'
        
@app.route('/bid')
def bid():
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
    return quote(request.args.get('epic'))

@app.route('/register', methods=['POST'])
def register():
        
    # Check for errors
    if not request.form.get('username'):
        return render_template('register.html', username='')
    elif not request.form.get('password') or not request.form.get('confirmpassword') or request.form.get('password') != request.form.get('confirmpassword'):
        return render_template('register.html', username=request.form.get('username'))
    
    # Insert new user into database
    conn = mysql.connect()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (username, password) VALUES (:username, :password)',
            [request.form.get('username'), pwd_context.encrypt(request.form.get("password"))])
    except:
        # Username already taken
        flash('Username already taken')
        return render_template('register.html', username='')
    conn.commit()
    
    # Set user as logged in
    id = cursor.lastrowid
    session['user_id'] = id
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
        data = cursor.fetchall()
        if pwd_context.verify(request.form.get('login_password'), data[0]['password']):
            session['user_id'] = data[0]['id']
            session['username'] = request.form.get('login_username')
            if request.form.get('login_remember') == 'on':
                session['password'] = request.form.get('login_password')
                session['rememberme'] = 1
            else:
                session.pop('username', None)
                session.pop('password', None)
                session.pop('rememberme', None)
            flash('Logged in. Welcome back {}.'.format(request.form.get('login_username')))
    
    # Load index page
    return redirect(url_for('index'))

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user_id', None)
    flash('Logged out')
    return redirect(url_for('login'))