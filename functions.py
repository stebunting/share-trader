# coding=utf-8
import datetime
import locale

# Flask module
from flask import session, redirect, url_for, request

# HTML request modules
import requests
from lxml import html

from functools import wraps

locale.setlocale(locale.LC_ALL, 'en_GB')

def gbp(value):
    #return "£{:,.2f}".format(value)
    return locale.currency(value, grouping=True)

def shareprice(value):
	return "{:.2f}".format(value)

def percentage(value):
    return "{:+.1f}%".format(value)

def dateFormat(value):
    return datetime.datetime.strftime(value, "%d %b %Y")

def quoteLogin():
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

def quote(epic, price='bid'):
    page = requests.get('http://uk.advfn.com/p.php?pid=financials&symbol=LSE:{}'.format(epic))
    tree = html.fromstring(page.content)
    cell = tree.xpath('.//td[@class="m"][@align="center"]/text()')
    if price == 'price':
        value = cell[0]
    elif price == 'offer':
        value = cell[4]
    else:
        value = cell[3]
    return float(value.strip().replace(',', ''))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Function to verify date
def verifyDate(test):
    try:
        verified = datetime.datetime.strptime(str(test), "%Y-%m-%d").strftime("%Y-%m-%d")
        return verified
    except:
        return False
    
