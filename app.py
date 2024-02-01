import os
import json
from slack import WebClient
from flask import Flask, request, jsonify
from slackeventsapi import SlackEventAdapter

# Initialize Flask app
app = Flask(__name__)

# Initialize Slack WebClient and Event Adapter
slack_token = os.environ["SLACK_BOT_TOKEN"]
client = WebClient(token=slack_token)
slack_events_adapter = SlackEventAdapter(os.environ["SLACK_SIGNING_SECRET"], "/slack/events", app)

# Define event handler for message events
@slack_events_adapter.on("message")
def message(event_data):
    print(event_data)
    event = event_data["event"]
    if event.get("subtype") is None and "thread_ts" in event:
        channel = event["channel"]
        thread_ts = event["thread_ts"]
        text = event["text"]
        print("passed thread check")
        if "knowledgeCrow" in text:
            print("passed trigger check")
            try:
                # Get conversation history for the thread
                result = client.conversations_replies(channel=channel, ts=thread_ts)
                messages = result["messages"]
                print("passed reply retrieval")
                # Extract user information and message text
                summary = [{"user": message.get("user", ""), "text": message.get("text", "")} for message in messages]
                print("passed summary creation")
                # Prepare JSON response
                response = {
                    "channel_id": channel,
                    "thread_ts": thread_ts,
                    "messages": summary
                }
                print(response)
                return jsonify(response)
            except Exception as e:
                return jsonify({"error": str(e)})

# Run the Flask app
if __name__ == "__main__":
    app.run(port=3000, debug=True)
