from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("weather")

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"
WEATHER_API_KEY=os.getenv("WEATHER_API_KEY")
API_US_GOV_KEY=os.getenv("API_US_GOV_KEY")
API_US_GOV_MAIL=os.getenv("API_US_GOV_MAIL")

async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None
        
def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
Event: {props.get("event", "Unknown")}
Area: {props.get("areaDesc", "Unknown")}
Severity: {props.get("severity", "Unknown")}
Description: {props.get("description", "No description available")}
Instructions: {props.get("instruction", "No specific instructions provided")}
"""

@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state.

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)


@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a location.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
    """
    # First get the forecast grid endpoint
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        return "Unable to fetch forecast data for this location."

    # Get the forecast URL from the points response
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        return "Unable to fetch detailed forecast."

    # Format the periods into a readable forecast
    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # Only show next 5 periods
        forecast = f"""
{period["name"]}:
Temperature: {period["temperature"]}°{period["temperatureUnit"]}
Wind: {period["windSpeed"]} {period["windDirection"]}
Forecast: {period["detailedForecast"]}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)

@mcp.tool()
async def get_city_weather(city: str) -> str:
    print("API Key : ", WEATHER_API_KEY)
    forecast_data = await make_nws_request("http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}".format(WEATHER_API_KEY=WEATHER_API_KEY,city=city))
    return forecast_data


@mcp.tool()
async def get_jobs_in_city(city: str, state: str = None) -> str:
    """Get federal job listings in a US city using USAJobs API.

    Args:
        city: Name of the city (e.g. "New York", "Los Angeles")
        state: Optional two-letter state code (e.g. "NY", "CA")
    """
    if not API_US_GOV_KEY:
        return "API_US_GOV_KEY not configured. Please set it in your .env file."
    
    headers = {
        "User-Agent": API_US_GOV_MAIL,
        "Authorization-Key": API_US_GOV_KEY,
        "Host": "data.usajobs.gov",
        "Accept": "application/json"
    }
    
    # Build location query
    location = city if not state else f"{city}, {state}"
    
    # USAJobs API with authentication
    url = f"https://data.usajobs.gov/api/search?LocationName={location}&ResultsPerPage=10"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            return f"Unable to fetch job listings: {str(e)}"
    
    search_result = data.get("SearchResult", {})
    results = search_result.get("SearchResultItems", [])
    
    if not results:
        return f"No federal job listings found in {location}."
    
    jobs = []
    for item in results[:10]:
        job = item.get("MatchedObjectDescriptor", {})
        position = job.get("PositionTitle", "Unknown")
        org = job.get("OrganizationName", "Unknown")
        salary_min = job.get("PositionRemuneration", [{}])[0].get("MinimumRange", "N/A") if job.get("PositionRemuneration") else "N/A"
        salary_max = job.get("PositionRemuneration", [{}])[0].get("MaximumRange", "N/A") if job.get("PositionRemuneration") else "N/A"
        location_info = job.get("PositionLocationDisplay", "Unknown")
        url = job.get("PositionURI", "")
        
        jobs.append(f"""
Position: {position}
Organization: {org}
Salary Range: ${salary_min} - ${salary_max}
Location: {location_info}
Apply: {url}
""")
    
    return f"Federal Jobs in {location}:\n" + "\n---\n".join(jobs)


async def fetch_city_weather_data(city: str) -> dict[str, Any]:
    """Fetch weather data for a city."""
    url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            current = data.get("current", {})
            return {
                "temperature_c": current.get("temp_c"),
                "temperature_f": current.get("temp_f"),
                "condition": current.get("condition", {}).get("text"),
                "humidity": current.get("humidity"),
                "wind_kph": current.get("wind_kph"),
                "feels_like_c": current.get("feelslike_c"),
                "uv_index": current.get("uv"),
            }
        except Exception:
            return {"error": "Unable to fetch weather data"}


async def fetch_city_jobs_data(city: str, country: str = None) -> list[dict[str, Any]]:
    """Fetch job listings for a city."""
    jobs = []
    
    # For US cities, use USAJobs API
    if country and country.lower() in ["united states", "usa", "us"]:
        if not API_US_GOV_KEY:
            return [{"error": "API_US_GOV_KEY not configured"}]
        
        headers = {
            "User-Agent": API_US_GOV_MAIL or "weather-app/1.0",
            "Authorization-Key": API_US_GOV_KEY,
            "Host": "data.usajobs.gov",
            "Accept": "application/json"
        }
        
        url = f"https://data.usajobs.gov/api/search?LocationName={city}&ResultsPerPage=5"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("SearchResult", {}).get("SearchResultItems", [])
                for item in results[:5]:
                    job = item.get("MatchedObjectDescriptor", {})
                    salary_min = job.get("PositionRemuneration", [{}])[0].get("MinimumRange", "N/A") if job.get("PositionRemuneration") else "N/A"
                    salary_max = job.get("PositionRemuneration", [{}])[0].get("MaximumRange", "N/A") if job.get("PositionRemuneration") else "N/A"
                    
                    jobs.append({
                        "position": job.get("PositionTitle", "Unknown"),
                        "organization": job.get("OrganizationName", "Unknown"),
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "location": job.get("PositionLocationDisplay", "Unknown"),
                        "url": job.get("PositionURI", "")
                    })
            except Exception:
                return [{"error": "Unable to fetch job listings"}]
    
    # For other countries, use Adzuna API (free tier) or return placeholder
    if not jobs:
        jobs = [{"info": "Job data available for US cities only via USAJobs API"}]
    
    return jobs


async def fetch_city_cost_of_living(city: str) -> dict[str, Any]:
    """Fetch cost of living data using Numbeo-style estimates."""
    # Using a free API for city statistics
    url = f"https://api.api-ninjas.com/v1/city?name={city}"
    headers = {"X-Api-Key": os.getenv("API_NINJAS_KEY", "")}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                if data:
                    city_data = data[0]
                    return {
                        "population": city_data.get("population"),
                        "is_capital": city_data.get("is_capital", False),
                        "latitude": city_data.get("latitude"),
                        "longitude": city_data.get("longitude"),
                    }
        except Exception:
            pass
    
    return {"info": "Detailed city statistics unavailable"}


async def fetch_city_quality_data(city: str, country: str) -> dict[str, Any]:
    """Fetch quality of life indicators for a city."""
    # Teleport API for quality of life (free)
    slug = city.lower().replace(" ", "-")
    url = f"https://api.teleport.org/api/urban_areas/slug:{slug}/scores/"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                categories = data.get("categories", [])
                scores = {}
                for cat in categories:
                    scores[cat.get("name", "").lower().replace(" ", "_")] = round(cat.get("score_out_of_10", 0), 1)
                return {
                    "teleport_score": round(data.get("teleport_city_score", 0), 1),
                    "categories": scores,
                    "summary": data.get("summary", "")[:300] if data.get("summary") else None
                }
        except Exception:
            pass
    
    return {"info": "Quality of life data unavailable for this city"}


# Default countries to analyze for livability reports
DEFAULT_COUNTRIES = [
    "United States",
]


@mcp.tool()
async def get_cities_livability_report(max_cities_per_country: int = 3, countries: list[str] = None) -> str:
    """Get comprehensive livability data for multiple cities across multiple countries.
    
    Fetches weather, job opportunities, population, and quality of life scores
    to help people evaluate cities for living across different countries.

    Args:
        max_cities_per_country: Maximum number of cities to analyze per country (default 3, max 5)
        countries: Optional list of countries to analyze. If not provided, uses default list of popular countries.
    """
    import asyncio
    import json
    
    max_cities_per_country = min(max_cities_per_country, 5)  # Cap at 5 per country to avoid timeout
    
    # Use provided countries or default list
    target_countries = countries if countries else DEFAULT_COUNTRIES
    
    # Fetch all countries and their cities
    cities_url = "https://countriesnow.space/api/v0.1/countries"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(cities_url, timeout=60.0)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            return json.dumps({"error": True, "msg": f"Unable to fetch countries: {str(e)}"}, indent=2)
    
    if data.get("error"):
        return json.dumps({"error": True, "msg": data.get("msg", "Unknown error")}, indent=2)
    
    all_countries_data = data.get("data", [])
    
    if not all_countries_data:
        return json.dumps({"error": True, "msg": "No countries data found."}, indent=2)
    
    # Create a lookup dict for countries
    country_cities_map = {item["country"]: item["cities"] for item in all_countries_data}
    
    # Filter to target countries that exist in the data
    selected_countries = []
    for country in target_countries:
        if country in country_cities_map:
            selected_countries.append({
                "country": country,
                "cities": country_cities_map[country][:max_cities_per_country]
            })
    
    if not selected_countries:
        return json.dumps({"error": True, "msg": "None of the specified countries were found."}, indent=2)
    
    # Fetch data for each city concurrently
    async def get_city_complete_data(city_name: str, country: str) -> dict[str, Any]:
        weather_task = fetch_city_weather_data(city_name)
        jobs_task = fetch_city_jobs_data(city_name, country)
        stats_task = fetch_city_cost_of_living(city_name)
        quality_task = fetch_city_quality_data(city_name, country)
        
        weather, jobs, stats, quality = await asyncio.gather(
            weather_task, jobs_task, stats_task, quality_task
        )
        
        return {
            "name": city_name,
            "country": country,
            "weather": weather,
            "job_opportunities": jobs,
            "city_stats": stats,
            "quality_of_life": quality
        }
    
    # Process all cities across all countries
    all_results = []
    
    for country_data in selected_countries:
        country = country_data["country"]
        cities = country_data["cities"]
        
        # Process cities in batches of 3 to avoid rate limiting
        batch_size = 3
        country_results = []
        
        for i in range(0, len(cities), batch_size):
            batch = cities[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[get_city_complete_data(city, country) for city in batch]
            )
            country_results.extend(batch_results)
        
        all_results.append({
            "country": country,
            "total_cities_available": len(country_cities_map.get(country, [])),
            "cities_analyzed": len(country_results),
            "cities": country_results
        })
    
    report = {
        "error": False,
        "msg": "Livability report generated successfully",
        "report_title": "Global Cities Livability Report",
        "total_countries_analyzed": len(selected_countries),
        "total_cities_analyzed": sum(len(c["cities"]) for c in all_results),
        "data": all_results
    }
    
    return json.dumps(report, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_city_full_profile(city: str, country: str = None) -> str:
    """Get a complete profile for a single city with all available data.
    
    Fetches weather, jobs, population, quality of life, and other metrics
    to provide a comprehensive view of the city for potential residents.

    Args:
        city: Name of the city (e.g. "Paris", "New York", "Tokyo")
        country: Optional country name for better accuracy
    """
    import asyncio
    import json
    
    # Fetch all data concurrently
    weather_task = fetch_city_weather_data(city)
    jobs_task = fetch_city_jobs_data(city, country)
    stats_task = fetch_city_cost_of_living(city)
    quality_task = fetch_city_quality_data(city, country or "")
    
    weather, jobs, stats, quality = await asyncio.gather(
        weather_task, jobs_task, stats_task, quality_task
    )
    
    profile = {
        "city": city,
        "country": country,
        "current_weather": weather,
        "job_opportunities": jobs,
        "city_statistics": stats,
        "quality_of_life": quality,
        "recommendation_factors": {
            "has_weather_data": "error" not in weather,
            "has_job_data": len(jobs) > 0 and "error" not in jobs[0],
            "has_quality_scores": "teleport_score" in quality,
            "has_population_data": "population" in stats
        }
    }
    
    return json.dumps(profile, indent=2, ensure_ascii=False)


@mcp.tool()
async def generate_livability_csv(report_json: str) -> str:
    """Generate a CSV from the livability report JSON data.
    
    Takes the JSON result from get_cities_livability_report and converts it
    to a CSV format for easy viewing in spreadsheets.

    Args:
        report_json: The JSON string result from get_cities_livability_report
    """
    import json
    import csv
    import io
    
    # Parse the JSON
    try:
        data = json.loads(report_json) if isinstance(report_json, str) else report_json
    except json.JSONDecodeError as e:
        return f"Error parsing JSON: {str(e)}"
    
    if data.get("error"):
        return f"Error in report data: {data.get('msg', 'Unknown error')}"
    
    # Create CSV in memory
    output = io.StringIO()
    
    # Define CSV headers
    headers = [
        "City",
        "Country",
        # Weather
        "Temperature (°C)",
        "Temperature (°F)",
        "Feels Like (°C)",
        "Condition",
        "Humidity (%)",
        "Wind (kph)",
        "UV Index",
        # City Stats
        "Population",
        "Is Capital",
        "Latitude",
        "Longitude",
        # Quality of Life
        "Teleport Score",
        "Housing Score",
        "Cost of Living Score",
        "Safety Score",
        "Healthcare Score",
        "Education Score",
        "Environment Score",
        "Economy Score",
        "Taxation Score",
        "Internet Access Score",
        "Leisure & Culture Score",
        "Tolerance Score",
        "Outdoors Score",
        # Jobs
        "Job Opportunities Count",
        "Top Job Position",
        "Top Job Salary Min",
        "Top Job Salary Max",
    ]
    
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    
    # Process each country and city
    for country_data in data.get("data", []):
        country = country_data.get("country", "Unknown")
        
        for city in country_data.get("cities", []):
            weather = city.get("weather", {})
            stats = city.get("city_stats", {})
            quality = city.get("quality_of_life", {})
            categories = quality.get("categories", {})
            jobs = city.get("job_opportunities", [])
            
            # Get top job info
            top_job = jobs[0] if jobs and isinstance(jobs, list) and len(jobs) > 0 else {}
            job_position = top_job.get("position", "N/A") if isinstance(top_job, dict) else "N/A"
            job_salary_min = top_job.get("salary_min", "N/A") if isinstance(top_job, dict) else "N/A"
            job_salary_max = top_job.get("salary_max", "N/A") if isinstance(top_job, dict) else "N/A"
            
            row = [
                city.get("name", "Unknown"),
                country,
                # Weather
                weather.get("temperature_c", "N/A"),
                weather.get("temperature_f", "N/A"),
                weather.get("feels_like_c", "N/A"),
                weather.get("condition", "N/A"),
                weather.get("humidity", "N/A"),
                weather.get("wind_kph", "N/A"),
                weather.get("uv_index", "N/A"),
                # City Stats
                stats.get("population", "N/A"),
                stats.get("is_capital", "N/A"),
                stats.get("latitude", "N/A"),
                stats.get("longitude", "N/A"),
                # Quality of Life
                quality.get("teleport_score", "N/A"),
                categories.get("housing", "N/A"),
                categories.get("cost_of_living", "N/A"),
                categories.get("safety", "N/A"),
                categories.get("healthcare", "N/A"),
                categories.get("education", "N/A"),
                categories.get("environmental_quality", "N/A"),
                categories.get("economy", "N/A"),
                categories.get("taxation", "N/A"),
                categories.get("internet_access", "N/A"),
                categories.get("leisure_&_culture", "N/A"),
                categories.get("tolerance", "N/A"),
                categories.get("outdoors", "N/A"),
                # Jobs
                len(jobs) if isinstance(jobs, list) else 0,
                job_position,
                job_salary_min,
                job_salary_max,
            ]
            
            writer.writerow(row)
    
    csv_content = output.getvalue()
    output.close()
    
    return csv_content


def main(host: str = "127.0.0.1", port: int = 8080, stateless: bool = False):
    # Initialize and run the server
    print(f"Running mcp server on {host}:{port} (stateless={stateless})")
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.settings.stateless_http = stateless
    
    # Allow connections from Docker networks
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*", 
            "localhost:*", 
            "[::1]:*",
            "172.17.0.1:*",  # Docker bridge
            "host.docker.internal:*",
            f"{host}:{port}",
            "*:*"  # Allow all hosts (remove for production)
        ],
        allowed_origins=[
            "http://127.0.0.1:*", 
            "http://localhost:*", 
            "http://[::1]:*",
            "http://172.17.0.1:*",
            "http://host.docker.internal:*",
            "*"  # Allow all origins (remove for production)
        ]
    )
    
    mcp.run(transport="streamable-http")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Weather MCP Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--stateless", action="store_true", help="Run in stateless mode (no sessions)")
    args = parser.parse_args()
    main(host=args.host, port=args.port, stateless=args.stateless)