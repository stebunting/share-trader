# coding=utf-8
import os
import datetime
import locale
import pytz

# Flask module
from flask import session, redirect, url_for, request, make_response

# HTML request modules
import requests
from lxml import html

from functools import wraps, update_wrapper

# Get environment variables, either locally or from config vars
try:
    from settings import *
except ImportError:
    advfnuser = os.environ['ADVFNUSER']
    advfnpassword = os.environ['ADVFNPASSWORD']

ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'

def gbp(value, **kwargs):
    try:
        value = float(value)
    except TypeError:
        return value
    try:
        retval = locale.currency(value, grouping=True)
    except ValueError:
        retval = locale.format_string("£%10.2f", value, grouping=True)
    if 'profitloss' in kwargs and kwargs['profitloss'] and value >= 0:
        retval = '+{}'.format(retval)
    return retval

def shareprice(value, **kwargs):
    try:
        value = float(value)
    except TypeError:
        return value
    if 'profitloss' in kwargs and kwargs['profitloss'] and value >= 0:
        return "{:+.2f}".format(value)
    else:
        return "{:.2f}".format(value)

def percentage(value, **kwargs):
    precision = 1
    if 'precision' in kwargs:
        try:
            precision = int(kwargs['precision'])
        except ValueError:
            return value
    return "{:+.{precision}f}%".format(value, precision=precision)

def dateFormat(value, **kwargs):
    format = "%d %b %Y"
    if 'format' in kwargs and kwargs['format'] == 'ISO':
        format = "%Y-%m-%d"
    elif 'format' in kwargs and kwargs['format'] == 'datetimeISO':
        format = "%Y-%m-%d %H:%M:%S"
    return datetime.datetime.strftime(value, format)

def quoteLogin():
    login_url = 'http://uk.advfn.com/common/account/login'
    protected_page = 'https://secure.advfn.com/login/secure'

    request_session = requests.session()
    request_session.headers['User-Agent'] = ua
    result = request_session.get(login_url)

    # Return true if login successful else false
    if not 200 <= result.status_code < 300:
        return False

    tree = html.fromstring(result.text)

    payload = {
        'login_username': advfnuser,
        'login_password': advfnpassword,
        'site': 'uk'
    }
    payload['redirect_url'] = list(set(tree.xpath("//input[@name='redirect_url']/@value")))[0]

    headers = {
        'Referer': login_url,
        'User-Agent': ua
    }

    result = request_session.post(
        protected_page, 
        data=payload, 
        headers=headers
    )

    tree = html.fromstring(result.text)
    title = tree.xpath("//title/text()")[0].strip()
    
    # Return true if login successful else false
    if not 200 <= result.status_code < 300 or title == 'ADVFN Login':
        return False
    else:
        return True

def quote(epic, price='bid'):
    headers = {
        'User-Agent': ua
    }

    if epic != 'FTSE:UKX':
        epic = 'LSE:{}'.format(epic)
    page = requests.get('http://uk.advfn.com/p.php?pid=financials&symbol={}'.format(epic), headers=headers)
    tree = html.fromstring(page.content)
    cell = tree.xpath('.//td[@class="m"][@align="center"]/text()')
    value = None
    if len(cell) < 5:
        return value
    if price == 'price':
        value = cell[0]
    elif price == 'offer':
        value = cell[4]
    else:
        value = cell[3]
    if not value:
        return value
    else:
        return float(value.strip().replace(',', ''))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Last-Modified'] = datetime.datetime.now()
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response
        
    return update_wrapper(no_cache, view)

# Function to verify date
def verifyDate(test, **kwargs):
    if 'startofday' in kwargs and kwargs['startofday']:
        try:
            verified = datetime.datetime.strptime(str(test).split(' ')[0], "%Y-%m-%d")
            return verified.replace(tzinfo=pytz.utc)
        except:
            return False
    elif 'endofday' in kwargs and kwargs['endofday']:
        try:
            verified = datetime.datetime.strptime(str(test).split(' ')[0], "%Y-%m-%d")
            return verified.replace(hour=23, minute=59, second=59, tzinfo=pytz.utc)
        except:
            return False
    else:
        try:
            verified = datetime.datetime.strptime(str(test), "%Y-%m-%d %H:%M:%S")
            return verified.replace(tzinfo=pytz.utc)
        except:
            pass
        try:
            verified = datetime.datetime.strptime(str(test).split(' ')[0], "%Y-%m-%d")
            time = datetime.datetime.time(datetime.datetime.now())
            return datetime.datetime.combine(verified, time).replace(tzinfo=pytz.utc)
        except:
            pass