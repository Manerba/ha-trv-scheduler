"""Browser tests use a simulated HA websocket API; never contact live TRVs."""

import os
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

ENGINE = os.environ.get("TRV_BROWSER_ENGINE", "chromium")
CHROME = os.environ.get(
    "TRV_BROWSER_EXECUTABLE", "/tmp/tareas-ui-browsers/chromium-1243/chrome-linux64/chrome"
)
pytestmark = pytest.mark.skipif(
    ENGINE == "chromium" and not Path(CHROME).exists(),
    reason="Set TRV_BROWSER_EXECUTABLE to Chromium",
)
CARD = Path(__file__).parents[1] / "custom_components/trv_scheduler/frontend/trv-scheduler-card.js"


@pytest.fixture
async def page():
    async with async_playwright() as playwright:
        browser = (
            await playwright.webkit.launch()
            if ENGINE == "webkit"
            else await playwright.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        )
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
    await page.set_viewport_size({"width": 1280, "height": 900})
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
    await page.set_viewport_size({"width": 1280, "height": 900})
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


@pytest.mark.parametrize("width,height", [(320, 568), (390, 844)])
async def test_mobile_time_wheels_full_width_and_commit(page, width, height):
    await page.set_viewport_size({"width": width, "height": height})
    await page.get_by_role("button", name="Zeitsteuerung", exact=True).click()
    await page.get_by_label("Uhrzeit 08:00", exact=True).click()
    hours = page.get_by_role("spinbutton", name="Stunden", exact=True)
    minutes = page.get_by_role("spinbutton", name="Minuten", exact=True)
    await expect(hours).to_have_attribute("aria-valuenow", "8")
    await expect(minutes).to_have_attribute("aria-valuenow", "0")
    assert await page.locator(".picker").evaluate(
        "el => Math.abs(el.getBoundingClientRect().width - "
        "el.closest('table').getBoundingClientRect().width) < 2"
    )
    assert await page.locator("dialog").evaluate("el=>el.scrollWidth<=el.clientWidth+1")
    await hours.press("ArrowUp")
    await minutes.press("PageUp")
    for _ in range(5):
        await minutes.press("ArrowUp")
    await expect(hours).to_have_attribute("aria-valuenow", "9")
    await expect(minutes).to_have_attribute("aria-valuenow", "15")
    assert await page.evaluate("server.schedule.revision") == 1
    if width == 390:
        await page.screenshot(path="/tmp/trv-wheel-time.png", full_page=True)
    await page.get_by_role("button", name="Übernehmen", exact=True).click()
    await expect(page.locator(".picker")).to_have_count(0)
    await expect(page.get_by_label("Uhrzeit 09:15", exact=True)).to_have_value("09:15")
    assert await page.evaluate("server.schedule.revision") == 2


async def test_mobile_temperature_resolution_limits_and_cancel(page):
    await page.evaluate("server.limits.step=.1")
    await page.get_by_role("button", name="Zeitsteuerung", exact=True).click()
    await page.get_by_label("Zieltemperatur 08:00", exact=True).click()
    wheel = page.get_by_role("spinbutton", name="Zieltemperatur", exact=True)
    await expect(wheel).to_have_attribute("aria-valuenow", "17")
    await wheel.press("ArrowUp")
    await expect(wheel).to_have_attribute("aria-valuenow", "17.1")
    await wheel.press("End")
    await wheel.press("ArrowUp")
    await expect(wheel).to_have_attribute("aria-valuenow", "30")
    await wheel.press("Home")
    await wheel.press("ArrowDown")
    await expect(wheel).to_have_attribute("aria-valuenow", "4")
    await page.get_by_role("button", name="Abbrechen", exact=True).click()
    assert await page.evaluate("server.schedule.revision") == 1
    await expect(page.get_by_label("Zieltemperatur 08:00", exact=True)).to_have_value("17")
    await page.get_by_label("Zieltemperatur 08:00", exact=True).click()
    await wheel.press("ArrowUp")
    await page.screenshot(path="/tmp/trv-wheel-temperature.png", full_page=True)
    await page.get_by_role("button", name="Übernehmen", exact=True).click()
    await expect(page.get_by_label("Zieltemperatur 08:00", exact=True)).to_have_value("17.1")
    assert await page.evaluate("server.schedule.rows[0].temperature") == 17.1


async def test_wheel_scroll_and_escape_do_not_save(page):
    await page.get_by_role("button", name="Zeitsteuerung", exact=True).click()
    await page.get_by_label("Uhrzeit 08:00", exact=True).click()
    hours = page.get_by_role("spinbutton", name="Stunden", exact=True)
    await hours.hover()
    await page.mouse.wheel(0, 132)
    await expect(hours).not_to_have_attribute("aria-valuenow", "8")
    await page.keyboard.press("Escape")
    await expect(page.locator(".picker")).to_have_count(0)
    await expect(page.get_by_role("dialog")).to_be_visible()
    assert await page.evaluate("server.schedule.revision") == 1
    await page.keyboard.press("Escape")
    await expect(page.get_by_role("dialog")).not_to_be_visible()


async def test_wheel_conflict_preserves_selection(page):
    await page.get_by_role("button", name="Zeitsteuerung", exact=True).click()
    await page.get_by_label("Uhrzeit 08:00", exact=True).click()
    await page.get_by_role("spinbutton", name="Stunden", exact=True).press("ArrowUp")
    await page.evaluate("window.conflict=true")
    await page.get_by_role("button", name="Übernehmen", exact=True).click()
    await expect(page.locator(".message")).to_contain_text("An anderer Stelle geändert")
    await expect(page.get_by_label("Uhrzeit 09:00", exact=True)).to_have_value("09:00")
    assert await page.evaluate("server.schedule.rows[0].time") == "08:00"
    await page.get_by_role("button", name="Neu laden", exact=True).click()
    await expect(page.get_by_label("Uhrzeit 08:00", exact=True)).to_have_value("08:00")


@pytest.mark.skipif(ENGINE != "chromium", reason="Touch injection uses Chromium CDP")
async def test_touch_swipe_scrolls_wheel_without_opening_keyboard(page):
    cdp = await page.context.new_cdp_session(page)
    await cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
    await page.get_by_role("button", name="Zeitsteuerung", exact=True).click()
    field = page.get_by_label("Uhrzeit 08:00", exact=True)
    await expect(field).to_have_attribute("readonly", "")
    await field.click()
    hours = page.get_by_role("spinbutton", name="Stunden", exact=True)
    box = await hours.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + 160
    await cdp.send(
        "Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]}
    )
    for offset in [20, 40, 60, 80, 100]:
        await cdp.send(
            "Input.dispatchTouchEvent",
            {"type": "touchMove", "touchPoints": [{"x": x, "y": y - offset}]},
        )
    await cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    await expect(hours).not_to_have_attribute("aria-valuenow", "8")
    assert await page.evaluate("server.schedule.revision") == 1
    await page.get_by_role("button", name="Übernehmen", exact=True).click()
    await expect(page.locator(".picker")).to_have_count(0)
    assert await page.evaluate("server.schedule.revision") == 2
    assert await page.evaluate("server.schedule.rows[0].time") != "08:00"
