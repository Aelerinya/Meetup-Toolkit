#!/usr/bin/env python3
"""
Sync Partiful Event to LessWrong

Main script that orchestrates syncing events from Partiful to LessWrong.
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests>=2.31.0",
#     "python-dotenv>=1.0.0",
#     "click>=8.1.0",
# ]
# ///

import json
import os
import sys
import tomllib
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import click
from dotenv import load_dotenv

# Import our modules
from partiful_loader import load_partiful_event
from lesswrong_client import (
    create_lesswrong_event,
    update_lesswrong_event,
    find_event_by_partiful_id,
    build_create_post_mutation,
    build_update_post_mutation
)


def load_config() -> dict:
    """Load configuration from config.toml file.

    Returns:
        Configuration dictionary with event and lesswrong settings

    Raises:
        FileNotFoundError: If config.toml doesn't exist
        tomllib.TOMLDecodeError: If config.toml is invalid
    """
    config_path = Path(__file__).parent / "config.toml"
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def format_description(partiful_description: str, partiful_url: str) -> str:
    """Format event description for LessWrong as HTML.

    Adds RSVP instructions at the end with HTML link.

    Args:
        partiful_description: Original description from Partiful
        partiful_url: URL of Partiful event

    Returns:
        HTML description with RSVP instructions
    """
    # Split by double newlines to get paragraphs
    paragraphs = partiful_description.split("\n\n")

    # Convert each paragraph: replace single newlines with <br>, wrap in <p>
    html_paragraphs = []
    for para in paragraphs:
        if para.strip():  # Skip empty paragraphs
            # Replace single newlines with <br>
            para_with_br = para.replace("\n", "<br>")
            html_paragraphs.append(f"<p>{para_with_br}</p>")

    html_description = "".join(html_paragraphs)

    # Add RSVP line as a separate paragraph with HTML link
    rsvp_line = f'<p>RSVP and find the exact location on <a href="{partiful_url}">Partiful</a>.</p>'
    return html_description + rsvp_line


def transform_event_data(partiful_event: dict) -> dict:
    """Transform Partiful event data to LessWrong format.

    Args:
        partiful_event: Event data from Partiful

    Returns:
        Event data formatted for LessWrong
    """
    # Load configuration
    config = load_config()

    # Build Google location data from config
    google_location = {
        "formatted_address": config["event"]["location_name"],
        "geometry": {
            "location": {
                "lat": config["event"]["latitude"],
                "lng": config["event"]["longitude"]
            }
        },
        "name": config["event"]["location_name"]
    }

    lw_event = {
        "title": partiful_event["title"],
        "start_time": partiful_event["start_time"],
        "end_time": partiful_event.get("end_time"),
        "location": config["event"]["location_name"],
        "google_location": google_location,
        "description": format_description(
            partiful_event.get("description", ""),
            partiful_event["partiful_url"]
        ),
        "rsvp_link": partiful_event["partiful_url"],
        "group_id": config["lesswrong"]["group_id"],
        "contact_info": config["lesswrong"]["contact_info"],
        "types": config["lesswrong"]["types"],
    }

    return lw_event


@click.command()
@click.argument("partiful_url")
@click.option("--token", envvar="LESSWRONG_TOKEN", help="LessWrong API token (or set LESSWRONG_TOKEN env var)")
@click.option("--graphiql", is_flag=True, help="Open request in GraphiQL editor instead of executing")
@click.option("--dry-run", is_flag=True, help="Show what would happen without making changes")
def sync_event(partiful_url: str, token: Optional[str], graphiql: bool, dry_run: bool):
    """Sync a Partiful event to LessWrong.

    Creates the event as a draft on LessWrong so you can review and edit before publishing.

    Examples:
        # Create draft on LessWrong
        uv run sync_event.py https://partiful.com/e/EptusdlB9L6mm2Lfimfo

        # Preview in GraphiQL editor
        uv run sync_event.py --graphiql https://partiful.com/e/EptusdlB9L6mm2Lfimfo
    """
    # Load environment variables
    load_dotenv()

    # Get token from env if not provided (only needed for direct execution, not GraphiQL or dry-run mode)
    if not graphiql and not dry_run:
        if not token:
            token = os.getenv("LESSWRONG_TOKEN")

        if not token:
            click.echo("Error: LessWrong loginToken required", err=True)
            click.echo("\nSet LESSWRONG_TOKEN environment variable or use --token option", err=True)
            click.echo("\nTo get your loginToken:", err=True)
            click.echo("  1. Login to LessWrong in your browser", err=True)
            click.echo("  2. Open browser Developer Tools (F12)", err=True)
            click.echo("  3. Go to Network tab", err=True)
            click.echo("  4. Refresh the page", err=True)
            click.echo("  5. Find any request to /graphql", err=True)
            click.echo("  6. Look at Request Headers > Cookie", err=True)
            click.echo("  7. Copy the value after 'loginToken=' (up to the semicolon)", err=True)
            sys.exit(1)

    # For dry-run mode, get token if available (for search), but don't require it
    if dry_run and not token:
        token = os.getenv("LESSWRONG_TOKEN")

    try:
        # Step 1: Fetch Partiful event
        click.echo(f"📥 Fetching event from Partiful...")
        partiful_event = load_partiful_event(partiful_url)

        click.echo(f"✓ Loaded: {partiful_event['title']}")
        click.echo()

        # Step 2: Transform data
        click.echo("🔄 Transforming event data...")
        lw_event = transform_event_data(partiful_event)

        # Step 3: Search for existing event
        click.echo("🔍 Checking for existing event...")
        existing = find_event_by_partiful_id(
            token,
            lw_event["title"],
            partiful_event["partiful_url"]
        )

        # Display what will be created/updated
        click.echo()
        click.echo("Event details:")
        click.echo(f"  Title: {lw_event['title']}")
        click.echo(f"  Start: {lw_event['start_time']}")
        if lw_event.get('end_time'):
            click.echo(f"  End: {lw_event['end_time']}")
        if lw_event.get('location'):
            click.echo(f"  Location: {lw_event['location']}")
        click.echo(f"  RSVP: {lw_event['rsvp_link']}")

        if existing:
            click.echo()
            click.echo(f"✓ Found existing event: {existing['url']}")
        click.echo()

        # Step 4: Build mutation
        if existing:
            mutation, variables = build_update_post_mutation(existing['_id'], lw_event)
            action = "UPDATE"
        else:
            mutation, variables = build_create_post_mutation(lw_event)
            action = "CREATE"

        if graphiql:
            # Open in GraphiQL editor
            click.echo(f"🌐 Opening GraphiQL editor ({action} mode)...")

            # Construct GraphiQL URL with query and variables pre-filled
            graphiql_url = "https://www.lesswrong.com/graphiql?" + urlencode({
                "query": mutation,
                "variables": json.dumps(variables, indent=2)
            })

            click.echo()
            click.echo("=" * 70)
            click.echo(f"GRAPHIQL PREVIEW ({action})")
            click.echo("=" * 70)
            click.echo()
            click.echo("Opening GraphiQL editor in your browser...")
            click.echo()
            click.echo("The mutation and variables are pre-filled.")
            click.echo("Click the 'Play' button to execute the mutation.")
            click.echo("=" * 70)

            webbrowser.open(graphiql_url)
        else:
            if dry_run:
                # Dry run - just show what would happen
                click.echo()
                click.echo("=" * 70)
                click.echo("🔍 DRY RUN - No changes will be made")
                click.echo("=" * 70)
                click.echo()
                if existing:
                    click.echo(f"Would UPDATE existing event: {existing['url']}")
                    click.echo(f"Event ID: {existing['_id']}")
                else:
                    click.echo("Would CREATE new draft event")
                click.echo()
                click.echo("Mutation:")
                print(mutation)
                click.echo()
                click.echo("Variables:")
                print(json.dumps(variables, indent=2))
                click.echo("=" * 70)
            else:
                # Execute
                if existing:
                    click.echo("📝 Updating existing event...")
                    result = update_lesswrong_event(token, existing['_id'], lw_event)

                    click.echo()
                    click.echo("=" * 70)
                    click.echo("✅ EVENT UPDATED!")
                    click.echo("=" * 70)
                    click.echo()
                    click.echo(f"Event URL: {result.get('url', 'N/A')}")
                    click.echo()
                    click.echo("The event has been updated successfully.")
                    click.echo("=" * 70)
                else:
                    click.echo("📝 Creating new draft...")
                    result = create_lesswrong_event(token, lw_event)

                    click.echo()
                    click.echo("=" * 70)
                    click.echo("✅ DRAFT CREATED!")
                    click.echo("=" * 70)
                    click.echo()
                    click.echo(f"Draft URL: {result.get('url', 'N/A')}")
                    click.echo()
                    click.echo("The event has been created as a draft.")
                    click.echo("You can now review and edit it before publishing.")
                    click.echo("=" * 70)

    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    sync_event()
