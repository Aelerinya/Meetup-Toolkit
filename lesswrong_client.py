#!/usr/bin/env python3
"""
LessWrong GraphQL Client

Creates events on LessWrong via GraphQL API.
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

import requests


LESSWRONG_GRAPHQL_ENDPOINT = "https://www.lesswrong.com/graphql"


def graphql_request(query: str, variables: dict, login_token: str, endpoint: str = LESSWRONG_GRAPHQL_ENDPOINT) -> dict:
    """Execute a GraphQL request with authentication.

    Args:
        query: GraphQL query or mutation string
        variables: Variables for the query/mutation
        login_token: LessWrong loginToken cookie value
        endpoint: GraphQL endpoint URL

    Returns:
        Response data from GraphQL API

    Raises:
        requests.RequestException: If request fails
        ValueError: If GraphQL returns errors
    """
    headers = {
        "Content-Type": "application/json",
    }

    cookies = {
        "loginToken": login_token
    }

    payload = {
        "query": query,
        "variables": variables
    }

    response = requests.post(endpoint, json=payload, headers=headers, cookies=cookies)

    # Try to get JSON response even on error status
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        response.raise_for_status()  # Raise the HTTP error
        raise

    # Check for GraphQL errors
    if "errors" in data:
        errors = data["errors"]
        error_messages = [e.get("message", str(e)) for e in errors]
        raise ValueError(f"GraphQL errors: {'; '.join(error_messages)}")

    # Check HTTP status after we've checked for GraphQL errors
    response.raise_for_status()

    return data


def introspect_schema(login_token: str) -> dict:
    """Query GraphQL endpoint for schema information.

    Discovers available types, mutations, and their fields.

    Args:
        login_token: LessWrong loginToken cookie value

    Returns:
        Schema introspection data
    """
    introspection_query = """
    query IntrospectionQuery {
      __schema {
        mutationType {
          fields {
            name
            args {
              name
              type {
                name
                kind
                ofType {
                  name
                  kind
                }
              }
            }
          }
        }
        types {
          name
          kind
          fields {
            name
            type {
              name
              kind
            }
          }
          inputFields {
            name
            type {
              name
              kind
              ofType {
                name
                kind
              }
            }
          }
        }
      }
    }
    """

    return graphql_request(introspection_query, {}, login_token)


def find_event_by_partiful_id(login_token: str, title: str, partiful_url: str) -> Optional[dict]:
    """Search for existing LessWrong event linked to a Partiful event.

    Strategy:
    1. Query user's draft posts (including draft events)
    2. Filter to events with matching title
    3. Check Partiful URL in eventRegistrationLink field to disambiguate
    4. Return event data if found

    Args:
        login_token: LessWrong loginToken cookie value
        title: Event title to filter by
        partiful_url: Partiful event URL to match for disambiguation

    Returns:
        Event data if found, None otherwise

    Raises:
        ValueError: If multiple events with same Partiful URL found
    """
    query = """
    query FindEvent($title: String!) {
      posts(selector: {
        drafts: {
          includeDraftEvents: true
          filter: $title
        }
      }) {
        results {
          _id
          title
          slug
          url
          isEvent
          eventRegistrationLink
          contents {
            markdown
          }
          startTime
          endTime
          location
          draft
        }
      }
    }
    """

    # Execute query with title filter
    variables = {"title": json.dumps({"title": title})}
    result = graphql_request(query, variables, login_token)
    data = result.get("data")
    if not data:
        return None

    posts_output = data.get("posts")
    if not posts_output:
        return None

    all_posts = posts_output.get("results", [])

    # Filter to events with matching title
    posts = [p for p in all_posts if p.get("isEvent") and p.get("title") == title]

    # Find matching event(s) by Partiful URL in eventRegistrationLink
    matches = [post for post in posts if post.get("eventRegistrationLink") == partiful_url]

    # Abort if multiple events have the same Partiful URL (data integrity issue)
    if len(matches) > 1:
        raise ValueError(
            f"Found {len(matches)} events with the same Partiful URL. "
            "This indicates a data integrity issue. "
            "Please manually resolve the duplicates on LessWrong."
        )

    if matches:
        return matches[0]

    # Fallback: check if Partiful URL is in description (for backward compatibility)
    fallback_matches = [
        post for post in posts
        if partiful_url in post.get("contents", {}).get("markdown", "")
    ]

    if len(fallback_matches) > 1:
        raise ValueError(
            f"Found {len(fallback_matches)} events with Partiful URL in description. "
            "This indicates a data integrity issue. "
            "Please manually resolve the duplicates on LessWrong."
        )

    if fallback_matches:
        return fallback_matches[0]

    return None


def build_create_post_mutation(event_data: dict) -> tuple[str, dict]:
    """Build GraphQL mutation for creating an event post.

    Args:
        event_data: Event data dictionary

    Returns:
        Tuple of (mutation_string, variables_dict)
    """
    mutation = """
    mutation CreatePost($data: CreatePostDataInput!) {
      createPost(data: $data) {
        data {
          _id
          slug
          url
          title
          isEvent
          startTime
          endTime
          location
          eventRegistrationLink
          draft
          createdAt
        }
      }
    }
    """

    # Build the post data
    post_data = {
        "title": event_data["title"],
        "isEvent": True,
        "draft": True,  # Always create as draft
    }

    # Add optional fields if present
    if event_data.get("start_time"):
        post_data["startTime"] = event_data["start_time"]

    if event_data.get("end_time"):
        post_data["endTime"] = event_data["end_time"]

    if event_data.get("location"):
        post_data["location"] = event_data["location"]

    if event_data.get("google_location"):
        post_data["googleLocation"] = event_data["google_location"]

    if event_data.get("rsvp_link"):
        post_data["eventRegistrationLink"] = event_data["rsvp_link"]

    if event_data.get("group_id"):
        post_data["groupId"] = event_data["group_id"]

    if event_data.get("contact_info"):
        post_data["contactInfo"] = event_data["contact_info"]

    if event_data.get("types"):
        post_data["types"] = event_data["types"]

    if event_data.get("description"):
        # LessWrong uses contents.originalContents for the description
        post_data["contents"] = {
            "originalContents": {
                "type": "html",
                "data": event_data["description"]
            }
        }

    variables = {
        "data": post_data
    }

    return mutation, variables


def build_update_post_mutation(event_id: str, event_data: dict) -> tuple[str, dict]:
    """Build GraphQL mutation for updating an existing event.

    Args:
        event_id: LessWrong event _id
        event_data: Updated event data (same format as create)

    Returns:
        (mutation_string, variables_dict)
    """
    mutation = """
    mutation UpdatePost($selector: SelectorInput!, $data: UpdatePostDataInput!) {
      updatePost(selector: $selector, data: $data) {
        data {
          _id
          slug
          url
          title
          isEvent
          startTime
          endTime
          location
          eventRegistrationLink
          draft
        }
      }
    }
    """

    # Build update data (similar to create, but with selector)
    update_data = {
        "title": event_data["title"],
        "startTime": event_data["start_time"],
    }

    if event_data.get("end_time"):
        update_data["endTime"] = event_data["end_time"]

    if event_data.get("location"):
        update_data["location"] = event_data["location"]

    if event_data.get("google_location"):
        update_data["googleLocation"] = event_data["google_location"]

    if event_data.get("rsvp_link"):
        update_data["eventRegistrationLink"] = event_data["rsvp_link"]

    if event_data.get("group_id"):
        update_data["groupId"] = event_data["group_id"]

    if event_data.get("contact_info"):
        update_data["contactInfo"] = event_data["contact_info"]

    if event_data.get("types"):
        update_data["types"] = event_data["types"]

    if event_data.get("description"):
        update_data["contents"] = {
            "originalContents": {
                "type": "html",
                "data": event_data["description"]
            }
        }

    variables = {
        "selector": {"_id": event_id},
        "data": update_data
    }

    return mutation, variables


def update_lesswrong_event(login_token: str, event_id: str, event_data: dict) -> dict:
    """Update existing LessWrong event.

    Args:
        login_token: LessWrong loginToken cookie value
        event_id: LessWrong event _id to update
        event_data: Updated event data

    Returns:
        Updated event data including URL

    Raises:
        ValueError: If update fails
    """
    mutation, variables = build_update_post_mutation(event_id, event_data)

    try:
        result = graphql_request(mutation, variables, login_token)
        return result["data"]["updatePost"]["data"]
    except Exception as e:
        raise ValueError(f"Failed to update LessWrong event: {e}")


def create_lesswrong_event(login_token: str, event_data: dict) -> dict:
    """Create an event on LessWrong using GraphQL mutation.

    Args:
        login_token: LessWrong loginToken cookie value
        event_data: Event data dictionary with keys:
            - title (required)
            - start_time (optional, ISO 8601 string)
            - end_time (optional, ISO 8601 string)
            - location (optional)
            - description (optional)

    Returns:
        Created event data including URL

    Raises:
        ValueError: If required fields are missing or API returns errors
    """
    if not event_data.get("title"):
        raise ValueError("Event title is required")

    mutation, variables = build_create_post_mutation(event_data)

    try:
        result = graphql_request(mutation, variables, login_token)
        created = result.get("data", {}).get("createPost", {}).get("data")
        return created
    except Exception as e:
        raise ValueError(f"Failed to create LessWrong event: {e}")


def main():
    """CLI interface for testing."""
    if len(sys.argv) < 2:
        print("Usage: uv run lesswrong_client.py <command> [args]")
        print("\nCommands:")
        print("  introspect <token>       - Show GraphQL schema introspection")
        print("  create <token> <json>    - Create event from JSON data")
        sys.exit(1)

    command = sys.argv[1]

    if command == "introspect":
        if len(sys.argv) < 3:
            print("Error: loginToken required")
            print("Usage: uv run lesswrong_client.py introspect <loginToken>")
            sys.exit(1)

        login_token = sys.argv[2]
        try:
            schema = introspect_schema(login_token)
            print(json.dumps(schema, indent=2))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif command == "create":
        if len(sys.argv) < 4:
            print("Error: loginToken and event data required")
            print("Usage: uv run lesswrong_client.py create <loginToken> '<json>'")
            sys.exit(1)

        login_token = sys.argv[2]
        event_json = sys.argv[3]

        try:
            event_data = json.loads(event_json)
            result = create_lesswrong_event(login_token, event_data)

            print("=" * 70)
            print("EVENT CREATED")
            print("=" * 70)
            print(json.dumps(result, indent=2))
            print("=" * 70)
            print(f"\nDraft URL: {result.get('url', 'N/A')}")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
