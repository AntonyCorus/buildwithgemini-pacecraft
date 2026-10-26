# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import uuid
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.a2ui.basic_catalog.provider import BasicCatalog
from app.a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore
from google.cloud import storage
from google.genai import types

from app.a2ui_utils import a2ui_callback


MODEL = "gemini-3.8-flash"
PROJECT_ID = "qwiklabs-gcp-03-024425596638"
GCS_BUCKET_NAME = "pacecraft-workouts-qwiklabs-03"

db = firestore.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)
image_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")


def list_workouts(category: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
    """List workouts from the workouts catalog, optionally filtered by category.

    Args:
        category: Optional category or difficulty to filter by (e.g. 'Intervals', 'Recovery', 'Tempo', 'Long Run', 'Beginner').
        max_results: Maximum number of workouts to return.

    Returns:
        A list of workout dictionaries containing id, title, category, description, target_distance_km, estimated_duration_min, interval_type, run_interval_seconds, and walk_interval_seconds.
    """
    col = db.collection("workouts")
    query = col.limit(max_results)
    docs = query.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        if category:
            cat_match = category.lower() in data.get("category", "").lower() or category.lower() in data.get("difficulty", "").lower()
            if not cat_match:
                continue
        results.append(data)
    return results


def get_workout(workout_id: str) -> Dict[str, Any]:
    """Retrieve detailed information for a specific workout by its ID.

    Args:
        workout_id: The unique ID of the workout (e.g. 'c25k_w1d1', 'easy_recovery_5k').

    Returns:
        The workout dictionary or an error message if not found.
    """
    doc_ref = db.collection("workouts").document(workout_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {"error": f"Workout '{workout_id}' not found."}
    return doc.to_dict()


def create_workout(
    title: str,
    category: str,
    description: str,
    target_distance_km: float,
    estimated_duration_min: int,
    interval_type: str = "continuous",
    run_interval_seconds: int = 0,
    walk_interval_seconds: int = 0,
    difficulty: str = "Beginner",
) -> Dict[str, Any]:
    """Create a new workout in the catalog (e.g. tailored custom workout or walk-run session).

    Args:
        title: Workout name (e.g. 'Intro Walk-Run 4K').
        category: Category (e.g. 'Intervals / Beginner', 'Long Run', 'Tempo').
        description: Workout steps and instructions.
        target_distance_km: Distance in kilometers.
        estimated_duration_min: Estimated total duration in minutes.
        interval_type: Type of interval ('run_walk', 'tempo', 'speed_repeats', or 'continuous').
        run_interval_seconds: Length of running interval in seconds (if walk-run or intervals).
        walk_interval_seconds: Length of walking recovery interval in seconds (if walk-run).
        difficulty: Difficulty level ('Beginner', 'Intermediate', 'Advanced').

    Returns:
        A confirmation dict with the generated workout ID and details.
    """
    doc_id = title.lower().replace(" ", "_").replace("-", "_")[:30]
    data = {
        "id": doc_id,
        "title": title,
        "category": category,
        "description": description,
        "target_distance_km": target_distance_km,
        "estimated_duration_min": estimated_duration_min,
        "interval_type": interval_type,
        "run_interval_seconds": run_interval_seconds,
        "walk_interval_seconds": walk_interval_seconds,
        "difficulty": difficulty,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection("workouts").document(doc_id).set(data)
    return {"status": "success", "workout": data}


def log_completed_run(
    user_id: str,
    distance_km: float,
    duration_min: int,
    notes: str,
    rpe_effort: Optional[int] = None,
) -> Dict[str, Any]:
    """Log a completed run or walk-run session for a user.

    Args:
        user_id: The ID or username of the runner.
        distance_km: Distance completed in kilometers.
        duration_min: Duration in minutes.
        notes: Notes on how the run felt, pace, or intervals completed.
        rpe_effort: Rate of Perceived Exertion (1-10 scale), optional.

    Returns:
        A confirmation dict of the logged activity.
    """
    run_data = {
        "user_id": user_id,
        "distance_km": distance_km,
        "duration_min": duration_min,
        "notes": notes,
        "rpe_effort": rpe_effort,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    doc_ref = db.collection("user_runs").document()
    doc_ref.set(run_data)
    run_data["log_id"] = doc_ref.id
    return {"status": "success", "logged_run": run_data}


def get_user_run_history(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieve recent logged runs for a user to assess progress and volume.

    Args:
        user_id: The runner's ID or username.
        limit: Number of recent runs to return.

    Returns:
        List of recent logged runs.
    """
    docs = (
        db.collection("user_runs")
        .where("user_id", "==", user_id)
        .limit(limit)
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def calculate_training_paces(
    recent_distance_km: float,
    recent_time_minutes: float,
    walk_run_ratio: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate personalized training pace zones and walk-run splits from a recent race or time trial.

    Args:
        recent_distance_km: Distance of a recent run, 5K, or time trial in kilometers (e.g. 5.0).
        recent_time_minutes: Time taken in minutes for that distance (e.g. 30.0 for a 30-min 5K).
        walk_run_ratio: Optional walk-run format for interval sessions, e.g. '1:1', '2:1', or 'run_60_walk_90'.

    Returns:
        A dictionary with pace zones (Easy, Marathon, Threshold/Tempo, Interval/VO2max) in mm:ss/km and walk-run intervals.
    """
    if recent_distance_km <= 0 or recent_time_minutes <= 0:
        return {"error": "Distance and time must be greater than zero."}

    # Base pace in seconds per km
    base_sec_per_km = (recent_time_minutes * 60.0) / recent_distance_km

    def fmt_pace(sec: float) -> str:
        m = int(sec // 60)
        s = int(round(sec % 60))
        if s == 60:
            m += 1
            s = 0
        return f"{m}:{s:02d}/km"

    # Standard training zone factors relative to baseline ~5K effort
    paces = {
        "easy_recovery_pace": f"{fmt_pace(base_sec_per_km * 1.25)} - {fmt_pace(base_sec_per_km * 1.35)}",
        "marathon_long_run_pace": fmt_pace(base_sec_per_km * 1.15),
        "threshold_tempo_pace": fmt_pace(base_sec_per_km * 1.06),
        "interval_vo2max_pace": fmt_pace(base_sec_per_km * 0.96),
    }

    result: Dict[str, Any] = {
        "baseline_pace": fmt_pace(base_sec_per_km),
        "training_pace_zones": paces,
    }

    if walk_run_ratio:
        result["walk_run_strategy"] = {
            "ratio": walk_run_ratio,
            "run_interval_pace": fmt_pace(base_sec_per_km * 1.10),
            "walk_interval_pace": "10:00 - 11:00/km (brisk walking)",
            "guidance": "Run at comfortable conversational pace during run segments, walk briskly during recovery segments.",
        }

    return result


def get_running_weather(city: str) -> Dict[str, Any]:
    """Fetch current real-world weather conditions and running suitability for a given city.

    Args:
        city: City name to look up weather for (e.g. 'San Francisco', 'New York', 'London').

    Returns:
        A dictionary containing temperature, humidity, apparent 'feels like' temperature, wind speed, precipitation, and running conditions guidance.
    """
    import urllib.parse
    import urllib.request
    import json

    try:
        # Step 1: Geocode city name to lat/lon via Open-Meteo Geocoding API
        encoded_city = urllib.parse.quote(city)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=1"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "PaceCraft/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            geo_data = json.loads(response.read().decode())

        if not geo_data.get("results"):
            return {"error": f"Could not find coordinates for city: '{city}'."}

        location = geo_data["results"][0]
        lat, lon = location["latitude"], location["longitude"]
        city_name = location.get("name", city)
        country = location.get("country", "")

        # Step 2: Fetch current weather metrics
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m"
            "&temperature_unit=celsius"
        )
        req_weather = urllib.request.Request(weather_url, headers={"User-Agent": "PaceCraft/1.0"})
        with urllib.request.urlopen(req_weather, timeout=5) as response:
            w_data = json.loads(response.read().decode())

        current = w_data.get("current", {})
        temp_c = current.get("temperature_2m")
        feels_c = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind_kmh = current.get("wind_speed_10m")
        precip_mm = current.get("precipitation")

        # Running assessment
        advice = []
        if temp_c is not None:
            if temp_c > 25:
                advice.append("Warm/hot weather: carry water, run early morning or late evening, and slow down your target pace.")
            elif temp_c < 5:
                advice.append("Cold conditions: dress in breathable layers and spend extra time warming up your muscles.")
            else:
                advice.append("Great moderate temperature for running.")

        if precip_mm and precip_mm > 0:
            advice.append("Precipitation detected: watch for slippery pavement and wear reflective/water-resistant gear.")
        if wind_kmh and wind_kmh > 25:
            advice.append("Brisk winds: consider starting into the headwind so the tailwind pushes you home.")

        return {
            "city": f"{city_name}, {country}",
            "temperature_celsius": temp_c,
            "feels_like_celsius": feels_c,
            "humidity_percent": humidity,
            "wind_speed_kmh": wind_kmh,
            "precipitation_mm": precip_mm,
            "running_advice": " ".join(advice),
        }
    except Exception as e:
        return {"error": f"Failed to retrieve weather for {city}: {str(e)}"}


def geocode_address(address: str) -> Dict[str, Any]:
    """Geocode a physical address or place name into latitude and longitude coordinates using Google Maps Geocoding API.

    Args:
        address: The address or place to geocode (e.g., 'Golden Gate Park, San Francisco', 'Central Park, NY').

    Returns:
        A dictionary with the formatted address and location coordinates (latitude and longitude).
    """
    import os
    import urllib.parse
    import urllib.request
    import json

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not set in environment."}

    try:
        encoded_address = urllib.parse.quote(address)
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return {"error": f"Geocoding failed for '{address}': {data.get('status', 'No results')}"}

        result = data["results"][0]
        location = result.get("geometry", {}).get("location", {})
        return {
            "name": address,
            "address": result.get("formatted_address"),
            "location": {
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
            },
        }
    except Exception as e:
        return {"error": f"Error during geocoding: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "park",
    radius_meters: float = 2000.0,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Find nearby places (e.g. parks, athletic tracks, gyms, cafes) using Google Places API (New).

    Args:
        latitude: Latitude coordinate of the search center.
        longitude: Longitude coordinate of the search center.
        place_type: Place type to search for (e.g., 'park', 'athletic_field', 'gym', 'cafe', 'stadium').
        radius_meters: Search radius in meters (default 2000.0, max 50000.0).
        max_results: Maximum number of places to return (1-20).

    Returns:
        A list of nearby places with name, address, and location coordinates.
    """
    import os
    import urllib.request
    import json

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not set in environment."}

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        }
        body = {
            "includedTypes": [place_type],
            "maxResultCount": min(max(max_results, 1), 20),
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": float(radius_meters),
                }
            },
        }

        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        places = []
        for p in data.get("places", []):
            display_name = p.get("displayName", {}).get("text", "")
            formatted_address = p.get("formattedAddress", "")
            loc = p.get("location", {})
            places.append({
                "name": display_name,
                "address": formatted_address,
                "location": {
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                },
            })

        return {
            "count": len(places),
            "places": places,
        }
    except Exception as e:
        return {"error": f"Error finding nearby places: {str(e)}"}


def generate_running_image(
    prompt: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """Generate an image related to running (e.g. milestone race badge, motivational card, workout visual) using gemini-3.1-flash-lite-image in the global region.
    Saves the image artifact to the Playground Artifacts panel and uploads it to public Cloud Storage.

    Args:
        prompt: Detailed description of the running visual to generate (e.g., 'A vibrant finisher badge for a 5K runner with gold accents').

    Returns:
        A dictionary containing the public GCS URL, filename, and status.
    """
    try:
        response = image_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_part: Optional[types.Part] = None
        for part in response.parts:
            if part.inline_data:
                image_part = part
                break

        if not image_part or not image_part.inline_data:
            return {"error": "No image data was generated by the model."}

        image_bytes = image_part.inline_data.data
        mime_type = image_part.inline_data.mime_type or "image/jpeg"
        ext = "jpg" if "jpeg" in mime_type else "png"
        filename = f"run_{uuid.uuid4().hex[:8]}.{ext}"

        # 1. Save artifact so it shows up in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename, artifact_part)

        # 2. Upload the same image bytes to public Cloud Storage bucket
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "filename": filename,
            "public_url": public_url,
            "prompt": prompt,
        }
    except Exception as e:
        return {"error": f"Failed to generate and upload image: {str(e)}"}


code_executor = AgentEngineSandboxCodeExecutor(
    sandbox_resource_name="projects/1026843896280/locations/us-central1/reasoningEngines/4274094442136207360/sandboxEnvironments/5899622603122802688",
    agent_engine_resource_name="projects/1026843896280/locations/us-central1/reasoningEngines/4274094442136207360",
)


async def generate_memories_callback(callback_context: CallbackContext):
    """Save salient facts, user running preferences, goals, and favorite running locations across sessions."""
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "PaceCraft, a knowledgeable and encouraging running coach agent. "
        "You assist runners of all experience levels in reaching their running goals. "
        "You remember all user running preferences (such as preferred running surfaces, weekly mileage targets, target race distances, pace goals, walk-run ratios, injury history, running schedule) and preferred running locations (home address, favorite parks, tracks, trails) from past sessions and incorporate them automatically into your recommendations. "
        "You create personalized training plans, calculate training paces and walk-run splits, check live weather, find running spots (parks, tracks, paths) using Google Maps, recommend workouts from the catalog, log completed runs, adjust training based on user feedback, and generate motivational visual cards or finisher badges. "
        "You can execute Python code in a secure sandbox when mathematical calculations, pace split modeling, or data analysis are needed. "
        "Use your tools to query the catalog of workouts, check weather, find places, calculate paces, generate visuals, run code in the sandbox, or save custom training sessions and run logs to the database."
    ),
    workflow_description="Analyze the user request, call necessary tools, and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        list_workouts,
        get_workout,
        create_workout,
        log_completed_run,
        get_user_run_history,
        calculate_training_paces,
        get_running_weather,
        geocode_address,
        find_nearby_places,
        generate_running_image,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

