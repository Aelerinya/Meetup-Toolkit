#!/usr/bin/env python3
"""
Partiful Event Loader

Fetches event data from Partiful API. Can be imported or run standalone.
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///

import json
import sys
from typing import Optional
from urllib.parse import urlparse

import requests


def extract_event_id(partiful_url: str) -> str:
    """Extract event ID from Partiful URL.

    Args:
        partiful_url: Partiful event URL (e.g., https://partiful.com/e/EptusdlB9L6mm2Lfimfo)

    Returns:
        Event ID string

    Raises:
        ValueError: If URL format is invalid
    """
    parsed = urlparse(partiful_url)

    # Handle both full URLs and just the event ID
    if parsed.netloc == "partiful.com" or parsed.netloc == "www.partiful.com":
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) >= 2 and path_parts[0] == "e":
            return path_parts[1]
    elif not parsed.netloc and not parsed.scheme:
        # Might be just the event ID
        return partiful_url.strip("/")

    raise ValueError(f"Invalid Partiful URL format: {partiful_url}")


def fetch_partiful_event(event_id: str) -> dict:
    """Fetch event data from Partiful API.

    Args:
        event_id: Partiful event ID

    Returns:
        Raw event data from Partiful API

    Raises:
        requests.RequestException: If API request fails
        ValueError: If API returns an error
    """
    endpoint = "https://api.partiful.com/getEventInfo"

    payload = {
        "data": {
            "params": {
                "eventId": event_id
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Meetup-Toolkit/1.0"
    }

    response = requests.post(endpoint, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()

    # Check for API errors
    if "error" in data:
        raise ValueError(f"Partiful API error: {data['error']}")

    return data


def parse_partiful_event(raw_data: dict) -> dict:
    """Parse and normalize Partiful event data.

    Args:
        raw_data: Raw event data from Partiful API

    Returns:
        Normalized event dictionary with standardized fields
    """
    # Navigate to the actual event data
    event_data = raw_data.get("result", {}).get("data", {}).get("event", {})

    # Extract location info
    location_info = event_data.get("locationInfo", {})
    maps_info = location_info.get("mapsInfo", {})

    # Format location from available data
    location = None
    if maps_info.get("addressLines"):
        location = ", ".join(maps_info["addressLines"])
    elif maps_info.get("approximateLocation"):
        # Remove newlines and format nicely
        location = maps_info["approximateLocation"].replace("\n", ", ")

    # Build normalized event dict
    parsed = {
        "partiful_id": event_data.get("id"),
        "title": event_data.get("title"),
        "description": event_data.get("description", ""),
        "start_time": event_data.get("startDate"),
        "end_time": event_data.get("endDate"),
        "timezone": event_data.get("timezone"),
        "location": location,
        "location_details": {
            "approximate": maps_info.get("approximateLocation"),
            "address_lines": maps_info.get("addressLines", []),
            "lat": maps_info.get("lat"),
            "lng": maps_info.get("lng"),
        },
        "capacity": event_data.get("maxCapacity"),
        "visibility": event_data.get("visibility"),
        "partiful_url": event_data.get("publicShortUrl") or f"https://partiful.com/e/{event_data.get('id')}",
    }

    return parsed


def load_partiful_event(partiful_url: str) -> dict:
    """Main entry point: Extract ID, fetch, and parse event.

    This is the primary function other scripts should import.

    Args:
        partiful_url: Partiful event URL or event ID

    Returns:
        Parsed event data dictionary
    """
    event_id = extract_event_id(partiful_url)
    raw_data = fetch_partiful_event(event_id)
    return parse_partiful_event(raw_data)


def main():
    """CLI interface for standalone usage."""
    if len(sys.argv) < 2:
        print("Usage: uv run partiful_loader.py <partiful_url>")
        print("\nExample:")
        print("  uv run partiful_loader.py https://partiful.com/e/EptusdlB9L6mm2Lfimfo")
        sys.exit(1)

    partiful_url = sys.argv[1]

    try:
        print(f"Fetching event from: {partiful_url}\n")
        event_data = load_partiful_event(partiful_url)

        print("=" * 70)
        print("PARTIFUL EVENT DATA")
        print("=" * 70)
        print(json.dumps(event_data, indent=2, ensure_ascii=False))
        print("=" * 70)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
