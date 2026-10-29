"""Use a normal browser login, then the exact read-only calls used by myPPC."""
import hashlib
import http.cookiejar
import json
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from .browser_runtime import browser_binaries
from .finance import merge_records
from .models import rows, normalize

ROOT = 'https://myppc.ppcenergy.ro'
ENDPOINT = ROOT + '/bff/api/soap'
# Public client routing value shipped in the portal JS, not a credential.
CLIENT_UUID = 'e59080c8-7aa0-11f1-ab07-0242ac120002'
READ_METHODS = {'ConsumptionLocationsAssociatedV2', 'InvoicesListV4', 'PaymentsList',
                'OnlinePaymentsListV2', 'BalanceFromPaymentCode'}


class LoginRequired(Exception):
    pass


class PortalError(Exception):
    pass




class Portal:
    def __init__(self, directory, username, password, payment_code=''):
        self.directory = Path(directory)
        self.username, self.password, self.payment_code = username, password, payment_code
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def login(self):
        chrome, driver_binary = browser_binaries(self.directory)
        with tempfile.TemporaryDirectory(prefix='profile-', dir=self.directory) as profile:
            options = webdriver.ChromeOptions()
            options.binary_location = chrome
            for option in ['--headless=new','--no-sandbox','--disable-dev-shm-usage',
                           '--no-first-run','--no-default-browser-check','--disable-background-networking',
                           '--disable-component-update','--disable-sync',f'--user-data-dir={profile}']:
                options.add_argument(option)
            driver = webdriver.Chrome(service=Service(driver_binary), options=options)
            try:
                driver.set_page_load_timeout(60)
                driver.get(ROOT + '/autentificare')
                wait = WebDriverWait(driver, 40)
                wait.until(lambda d: any(e.is_displayed() and e.get_attribute('type')=='password'
                                         for e in d.find_elements(By.TAG_NAME,'input')))
                for element in driver.find_elements(By.TAG_NAME,'button'):
                    if element.is_displayed() and element.text.strip() == 'Reject All':
                        element.click()
                        break
                if not driver.current_url.startswith(ROOT + '/'):
                    raise LoginRequired('Destinație de autentificare neașteptată')
                inputs = [e for e in driver.find_elements(By.TAG_NAME,'input') if e.is_displayed()]
                usernames = [e for e in inputs if e.get_attribute('type') in ('email','tel','text')]
                passwords = [e for e in inputs if e.get_attribute('type')=='password']
                if len(usernames)!=1 or len(passwords)!=1:
                    raise LoginRequired('Formularul PPC s-a schimbat')
                usernames[0].send_keys(self.username)
                passwords[0].send_keys(self.password)
                # The label can be remotely configured by PPC.  Select the
                # semantic submit control instead of depending on its text.
                buttons = [e for e in driver.find_elements(By.CSS_SELECTOR,
                           'button[type="submit"]') if e.is_displayed()]
                if not buttons:
                    buttons = [e for e in driver.find_elements(By.CSS_SELECTOR,
                               'app-button[type="submit"]') if e.is_displayed()]
                if not buttons:
                    raise LoginRequired('Buton de autentificare indisponibil')
                buttons[0].click()
                try:
                    wait.until(lambda d: d.current_url.startswith(ROOT + '/acasa') or
                               bool(d.find_elements(By.CSS_SELECTOR,
                                                    'a[href="/facturi-si-plati"]')))
                except Exception as exc:
                    # A visible challenge is not solved, and the login is not retried.
                    notices = []
                    selectors = ('[role="alert"]', 'mat-error', '.error-message',
                                 '.toast-message', '.snackbar')
                    for selector in selectors:
                        for element in driver.find_elements(By.CSS_SELECTOR, selector):
                            text = ' '.join(element.text.split())
                            if element.is_displayed() and text and text not in notices:
                                notices.append(text[:240])
                    if not notices:
                        body = driver.find_element(By.TAG_NAME, 'body').text
                        keywords = ('eroare', 'parol', 'captcha', 'autentific', 'încearc')
                        for line in body.splitlines():
                            text = ' '.join(line.split())
                            if text and any(word in text.lower() for word in keywords):
                                if text not in notices:
                                    notices.append(text[:240])
                    detail = '; '.join(notices[:2])
                    message = 'PPC nu a confirmat autentificarea'
                    if detail:
                        message += ': ' + detail
                    else:
                        message += '; verifică datele sau cerința de securitate'
                    raise LoginRequired(message) from exc
                for cookie in driver.get_cookies():
                    self.jar.set_cookie(http.cookiejar.Cookie(version=0, name=cookie['name'],
                        value=cookie['value'], port=None, port_specified=False,
                        domain=cookie['domain'], domain_specified=True,
                        domain_initial_dot=cookie['domain'].startswith('.'), path=cookie['path'],
                        path_specified=True, secure=cookie.get('secure',True),
                        expires=cookie.get('expiry'), discard=False, comment=None,
                        comment_url=None, rest={'HttpOnly':cookie.get('httpOnly',False)}, rfc2109=False))
            finally:
                driver.quit()

    def call(self, method, data):
        if method not in READ_METHODS:
            raise PortalError('Metodă nepermisă')
        headers = {'Content-Type':'application/json', 'Origin':ROOT, 'Referer':ROOT+'/',
                   'TID':CLIENT_UUID, 'SID':CLIENT_UUID, 'TOUCHPOINT':'web'}
        for cookie in self.jar:
            if cookie.name == 'XSRF-TOKEN':
                headers['X-XSRF-TOKEN'] = cookie.value
        request = urllib.request.Request(ENDPOINT, data=json.dumps({'method':method,'data':data}).encode(),
                                         headers=headers, method='POST')
        try:
            with self.opener.open(request, timeout=45) as response:
                result = json.loads(response.read())
        except (urllib.error.URLError, ValueError) as exc:
            raise PortalError(f'Cererea PPC {method} nu a reușit') from exc
        if not result.get('success') or not isinstance(result.get('data'),dict):
            raise PortalError(f'Răspuns PPC neutilizabil pentru {method}')
        return result['data']

    def fetch(self, previous=None):
        previous = previous or {}
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.login()
        locations = []
        for group in rows(self.call('ConsumptionLocationsAssociatedV2', {})):
            children = group.get('consumptionLocations',{}).get('Row',[])
            children = children if isinstance(children,list) else [children] if isinstance(children,dict) else []
            for location in children:
                locations.append({**location, 'paymentCode':str(group['paymentCode'])})
        if self.payment_code:
            selected = [p for p in locations if p['paymentCode']==self.payment_code]
        else:
            selected = locations
        ids = {str(p['idConsumptionLocation']) for p in selected}
        if len(ids)!=1:
            raise PortalError('Specifică un cod de plată care identifică un singur loc de consum')
        location = selected[0]
        code = location['paymentCode']
        if previous and previous.get('payment_code') != code:
            raise PortalError('Codul de plată diferă de istoricul salvat')
        params = {'idConsumptionLocation':location['idConsumptionLocation']}
        invoices = self.call('InvoicesListV4',params)
        payments = self.call('PaymentsList',params)
        outstanding = self.call('OnlinePaymentsListV2',{})
        signed_balance = self.call('BalanceFromPaymentCode',{'paymentCode':code})
        data = normalize(invoices,payments,outstanding,signed_balance,code)
        data['invoices'] = sorted(merge_records(previous.get('invoices',[]),data['invoices']),
                                   key=lambda r:(r['issued'],r['id']), reverse=True)
        data['payments'] = sorted(merge_records(previous.get('payments',[]),data['payments']),
                                   key=lambda r:r['date'], reverse=True)
        data.update(payment_code=code, history_complete=False, history_scope='visible_portal_entries',
                    balance_source='ppc_signed_balance', updated_at=datetime.now(timezone.utc).isoformat(),
                    latest_invoice=data['invoices'][0] if data['invoices'] else None,
                    latest_payment=data['payments'][0] if data['payments'] else None,
                    latest_invoice_detail={})
        return data
