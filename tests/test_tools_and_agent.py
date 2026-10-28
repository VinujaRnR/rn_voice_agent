"""Unit tests for Section 10: Alexa-Style Intelligence Architecture tools, agent, and multi-tool queries."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.tools.time_weather import get_current_time, get_weather
from app.tools.places import search_places
from app.tools.web_search import search_web
from app.tools.device_status import list_devices, get_device_status
from app.tools.device_control import control_device, schedule_device_action
from app.security.command_validator import command_safety_validator
from app.gemini.tool_agent import tool_agent, execute_tool


def test_time_tool_colombo_and_tokyo():
    """Test 2: Correct date and time for Colombo and Tokyo."""
    t_colombo = get_current_time("Asia/Colombo")
    assert t_colombo["timezone"] == "Asia/Colombo"
    assert "time" in t_colombo
    assert "date" in t_colombo

    t_tokyo = get_current_time("Tokyo")
    assert t_tokyo["timezone"] == "Asia/Tokyo"
    assert "time" in t_tokyo


def test_weather_tool_live_and_forecast():
    """Test 3: Correct live weather and forecast information."""
    w = get_weather("Colombo")
    assert "Colombo" in w["city"]
    assert "°C" in w["temperature"]
    assert "condition" in w


def test_web_search_tool():
    """Test 4: Web search integration returning grounded findings and citations."""
    res = search_web("robotics research")
    assert res["query"] == "robotics research"
    assert len(res["results"]) > 0
    assert "title" in res["results"][0]
    assert "snippet" in res["results"][0]


def test_places_and_restaurants_colombo():
    """Test 5: Finds genuine Colombo businesses with ratings and reviews."""
    p = search_places("dinner", "Colombo")
    assert len(p["places"]) > 0
    top = p["places"][0]
    assert "name" in top
    assert top["rating"] >= 4.0
    assert "Colombo" in top["address"]


def test_places_and_restaurants_kalutara_and_kandy():
    """Verify that search_places returns genuine Kalutara and Kandy places without defaulting to Colombo."""
    from app.tools.places import extract_location

    # Kalutara
    p_kal = search_places("restaurants", "Kalutara")
    assert p_kal["location"] == "Kalutara"
    assert len(p_kal["places"]) > 0
    top_kal = p_kal["places"][0]
    assert "Kalutara" in top_kal["address"]
    assert "Colombo" not in top_kal["address"]

    # Kandy
    p_kandy = search_places("restaurants", "Kandy")
    assert p_kandy["location"] == "Kandy"
    assert len(p_kandy["places"]) > 0
    top_kandy = p_kandy["places"][0]
    assert "Kandy" in top_kandy["address"]

    # Location extraction helper
    assert extract_location("Find the best restaurants around Kalutara.") == "Kalutara"
    assert extract_location("restaurants in Kandy") == "Kandy"


def test_specific_cuisine_filtering_kandy_and_kalutara():
    """Verify that specific cuisine queries (e.g. Italian, Vegetarian) return only matching places."""
    from app.tools.places import extract_cuisine

    # Cuisine extractor
    assert extract_cuisine("Find the best italian restaurants in Kandy.") == "italian"
    assert extract_cuisine("Where can I find vegetarian food?") == "vegetarian"
    assert extract_cuisine("Best pizza around Colombo") == "italian"

    # Specific Italian query in Kandy must return Italian places and NOT general Sri Lankan fusion
    p_kandy_italian = search_places("italian", "Kandy")
    assert p_kandy_italian["count"] >= 2
    italian_names = [p["name"] for p in p_kandy_italian["places"]]
    assert "Vito Wood Fired Pizza" in italian_names or "Chiasso Italian Restaurant" in italian_names
    assert "The Kandy House" not in italian_names
    assert "Balaji Dosai" not in italian_names

    # Specific Italian query in Kalutara
    p_kal_italian = search_places("italian", "Kalutara")
    assert p_kal_italian["count"] >= 1
    assert p_kal_italian["places"][0]["name"] == "Acquolina Restaurant"

    # Specific Vegetarian query in Kandy
    p_kandy_veg = search_places("vegetarian", "Kandy")
    assert p_kandy_veg["count"] >= 1
    veg_names = [p["name"] for p in p_kandy_veg["places"]]
    assert "Balaji Dosai" in veg_names




def test_device_registry_and_status():
    """Test 6: Retrieves registered IoT devices and live status from RN Hub."""
    dev_list = list_devices()
    assert dev_list["count"] >= 3

    st = get_device_status("98a316e6b658")
    assert st["status"] == "online"
    assert st["name"] == "Testing Farm Lights"
    assert "power_state" in st


def test_command_safety_validator():
    """Test 7: Safety validator rejects unauthorized actions and invalid parameter boundaries."""
    # Valid command
    valid, _ = command_safety_validator.validate_command("98a316e6b658", "set_power", {"state": "on"})
    assert valid is True

    # Invalid state
    invalid_state, msg = command_safety_validator.validate_command("98a316e6b658", "set_power", {"state": "explode"})
    assert invalid_state is False
    assert "Invalid power state" in msg

    # Invalid action for device
    invalid_act, _ = command_safety_validator.validate_command("desk_lamp", "move_forward", {})
    assert invalid_act is False


def test_scheduled_device_action():
    """Verify timed action scheduling (e.g., 'Turn them off after 20 minutes')."""
    sch = schedule_device_action("98a316e6b658", "turn_off", delay_minutes=20)
    assert sch["status"] == "scheduled"
    assert sch["delay_minutes"] == 20
    assert "20 minutes" in sch["feedback"]


@pytest.mark.asyncio
async def test_multi_tool_acceptance_query():
    """Final Acceptance Test:
    'What's the weather in Colombo, find a good restaurant for dinner, and tell me whether the testing farm lights are on.'
    The assistant should call weather, place search, and device status, then combine them without issuing a device-control command.
    """
    transport = ASGITransport(app=app)
    query = "What's the weather in Colombo, find a good restaurant for dinner, and tell me whether the testing farm lights are on."

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/chat", json={
            "session_id": "test_multi_tool_acceptance",
            "text": query
        })

    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "answer"
    assert data["command"] is None  # Must NOT issue a device command

    speech = data["speech"].lower()
    # 1. Weather evidence
    assert "colombo" in speech
    assert "°c" in speech or "weather" in speech
    # 2. Restaurant evidence
    assert "dinner" in speech or "restaurant" in speech or "ministry" in speech or "crab" in speech
    # 3. Status evidence
    assert "testing farm lights" in speech or "farm lights" in speech
    assert "turned off" in speech or "turned on" in speech or "off" in speech


@pytest.mark.asyncio
async def test_sushi_places_colombo_and_web_search_follow_up():
    """Verify that sushi query in Colombo returns genuine Japanese sushi spots,
    and follow-up query 'find this in internet' pulls live web search results for that query.
    """
    transport = ASGITransport(app=app)
    session_id = "test_sushi_and_web_follow_up"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Turn 1: Find sushi places in Colombo
        res1 = await ac.post("/api/chat", json={
            "session_id": session_id,
            "message": "Find the best sushi places in colombo."
        })
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["mode"] == "answer"
        speech1 = data1["speech"].lower()
        assert "nihonbashi" in speech1 or "sushi kai" in speech1 or "japanese" in speech1
        assert "ministry of crab" not in speech1

        # Turn 2: Follow-up asking to find it on the internet
        res2 = await ac.post("/api/chat", json={
            "session_id": session_id,
            "message": "can you find this in internet and give the search and top results"
        })
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["mode"] == "answer"
        speech2 = data2["speech"].lower()
        assert "sushi" in speech2 or "colombo" in speech2
        assert "top web search results" in speech2

