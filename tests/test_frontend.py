"""Browser tests use a simulated HA websocket API; never contact live TRVs."""

import os
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

CHROME = os.environ.get(
    "TRV_BROWSER_EXECUTABLE", "/tmp/tareas-ui-browsers/chromium-1243/chrome-linux64/chrome"
)
pytestmark = pytest.mark.skipif(
    not Path(CHROME).exists(), reason="Set TRV_BROWSER_EXECUTABLE to Chromium"
)
CARD = Path(__file__).parents[1] / "custom_components/trv_scheduler/frontend/trv-scheduler-card.js"


@pytest.fixture
async def page():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        await page.route(
            "http://trv.test/**",
            lambda route: route.fulfill(
                content_type="text/html",
                body='<html lang="de"><body style="margin:12px;background:#eef2f5"></body></html>',
            ),
        )
        await page.goto("http://trv.test/")
        await page.add_script_tag(content=CARD.read_text())
        await page.evaluate("""() => {
          window.server = {can_edit:true,lock_supported:true,device_lock:{locked:false},
            temperature_unit:'°C',limits:{min:4,max:30,step:.5},
            schedule:{revision:1,enabled:true,rows:[
            {id:'a',time:'08:00',temperature:17,enabled:true,locked:true},
            {id:'b',time:'17:30',temperature:22,enabled:true,locked:false}]}};
          const card=document.createElement('trv-scheduler-card');
          card.setConfig({entity:'climate.test'});
          card.hass={states:{'climate.test':{attributes:{
            friendly_name:'Schlafzimmer',temperature:21}}},callWS:async msg=>{
            if(msg.type==='trv_scheduler/replace') {
              if(window.conflict){window.conflict=false;throw {code:'revision_conflict'};}
              if(msg.expected_revision!==server.schedule.revision)throw {code:'revision_conflict'};
              server.schedule={revision:server.schedule.revision+1,enabled:msg.enabled,rows:msg.rows};
            }
            if(msg.type==='trv_scheduler/unlock')server.device_lock.locked=false;
            return structuredClone(server);
          }};
          document.body.append(card);
        }""")
        yield page
        await browser.close()


@pytest.mark.parametrize("width", [320, 390, 1280])
async def test_dialog_fits_and_can_close(page, width):
    await page.set_viewport_size({"width": width, "height": 844})
    await page.get_by_role("button", name="Zeitsteuerung", exact=True).click()
    await expect(page.get_by_role("dialog")).to_be_visible()
    await expect(page.locator("tbody tr")).to_have_count(2)
    assert await page.locator("dialog").evaluate("(el)=>el.scrollWidth<=el.clientWidth+1")
    assert await page.locator("table").evaluate(
        "(el)=>el.getBoundingClientRect().right <= "
        'el.closest("dialog").getBoundingClientRect().right'
    )
    if width == 390:
        await page.screenshot(path="/tmp/trv-dialog-mobile.png", full_page=True)
    await page.keyboard.press("Escape")
    await expect(page.get_by_role("dialog")).not_to_be_visible()


async def test_inline_edit_toggle_lock_add_delete(page):
    await page.get_by_role("button", name="Zeitsteuerung", exact=True).click()
    time = page.get_by_label("Uhrzeit 08:00", exact=True)
    await time.fill("09:15")
    await page.keyboard.press("Tab")
    await expect(page.get_by_label("Uhrzeit 09:15", exact=True)).to_be_visible()
    temp = page.get_by_role("spinbutton", name="Zieltemperatur 09:15")
    await temp.fill("18.5")
    await page.keyboard.press("Tab")
    await page.get_by_role("switch", name="Schaltzeit 09:15 aktivieren").click()
    await page.get_by_role("button", name="Drehring ab 09:15 sperren").click()
    data = await page.evaluate('server.schedule.rows.find(r=>r.id==="a")')
    assert data == {
        "id": "a",
        "time": "09:15",
        "temperature": 18.5,
        "enabled": False,
        "locked": False,
    }
    await page.get_by_role("button", name="Schaltzeit 09:15 löschen").click()
    await expect(page.locator("tbody tr")).to_have_count(1)
    await page.get_by_role("button", name="＋ Schaltzeit hinzufügen").click()
    await expect(page.locator("tbody tr")).to_have_count(2)
    data = await page.evaluate('server.schedule.rows.find(r=>r.time==="12:00")')
    assert data["enabled"] is False and data["locked"] is False


async def test_conflict_keeps_draft_until_explicit_reload(page):
    await page.get_by_role("button", name="Zeitsteuerung", exact=True).click()
    await page.evaluate("window.conflict=true")
    temp = page.get_by_role("spinbutton", name="Zieltemperatur 08:00")
    await temp.fill("18")
    await page.keyboard.press("Tab")
    await expect(page.locator(".message")).to_contain_text("An anderer Stelle geändert")
    await expect(temp).to_have_value("18")
    assert await page.evaluate("server.schedule.rows[0].temperature") == 17
    await page.get_by_role("button", name="Neu laden", exact=True).click()
    await expect(temp).to_have_value("17")
