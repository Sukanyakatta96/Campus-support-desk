import os
import sys

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'
PASSWORD = os.environ['CAMPUS_DEMO_PASSWORD']
SHOTS = 'docs/screenshots'
os.makedirs(SHOTS, exist_ok=True)


def sign_in(page, role):
    page.goto(BASE)
    page.wait_for_selector('#lu')
    user = page.locator('#lu option', has_text=f'({role})').first.get_attribute('value')
    page.select_option('#lu', user)
    page.fill('#lp', PASSWORD)
    page.click('#li')


def step(label):
    print(f'PASS  {label}')


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' and '40' not in m.text else None)

    page.goto(BASE); page.wait_for_selector('#lu'); page.screenshot(path=f'{SHOTS}/01_login.png')
    page.fill('#lp', 'wrong'); page.click('#li')
    expect(page.locator('#toast')).to_contain_text('invalid credentials'); step('wrong password shows an error')

    sign_in(page, 'learner')
    page.wait_for_selector('h2:has-text("Tickets (")')
    expect(page.locator('nav')).not_to_contain_text('Dashboard'); step('learner sees only Tickets and New request')
    page.click('nav >> text=New request'); page.select_option('#ct', 'CAT-REG-ENR')
    page.fill('#sj', 'add drop deadline'); page.fill('#bd', 'enrollment add drop deadline question'); page.click('#sv')
    page.wait_for_selector('.msg')
    expect(page.locator('#m')).to_contain_text('source KB-'); expect(page.locator('#m')).to_contain_text('ANSWERED')
    page.screenshot(path=f'{SHOTS}/02_new_request_answered.png'); step('learner files a request and gets a cited answer')
    page.click('#lo')

    sign_in(page, 'support_staff')
    page.wait_for_selector('text=SLA breach rate'); page.screenshot(path=f'{SHOTS}/03_dashboard.png'); step('staff dashboard loads metrics')
    expect(page.locator('nav')).not_to_contain_text('Audit'); step('staff does not see the admin-only Audit tab')
    page.click('nav >> text=Tickets'); page.wait_for_selector('tr.c')
    page.select_option('[data-f=status]', 'in_progress'); page.wait_for_selector('tr.c')
    page.locator('tr.c').first.click(); page.wait_for_selector('#rs')
    page.screenshot(path=f'{SHOTS}/04_ticket_detail.png')
    page.select_option('#rt', '5'); page.click('#rs')
    expect(page.locator('.ok')).to_contain_text('Resolved'); step('staff filters, opens and resolves a ticket with rating')
    page.click('#lo')

    sign_in(page, 'platform_administrator')
    page.click('nav >> text=Audit'); page.wait_for_selector('table tr:nth-child(5)')
    expect(page.locator('table tr')).to_have_count(6); page.screenshot(path=f'{SHOTS}/05_audit.png'); step('administrator sees the 5-check audit')
    assert not errors, errors
    step('no JavaScript errors'); browser.close()
