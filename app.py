import os
import json
from slack import WebClient
from flask import Flask, request, jsonify
from slackeventsapi import SlackEventAdapter
import sqlite3
import gspread
from google.oauth2.service_account import Credentials
import requests
import asyncio

# Initialize Flask app
app = Flask(__name__)

# Database configuration
DATABASE = 'messages'

# Create the table on startup
create_table()

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
                add_data_to_google_sheets("Team A", "Topic 1", "https://example.com", "Summary of the chat.")
                print(response)
                return jsonify(response)
            except Exception as e:
                return jsonify({"error": str(e)})

def add_data_to_google_sheets(team, topic, chat_link, summary):
    # Replace 'your_credentials.json' with the path to your Google Sheets API credentials file
    credentials = Credentials.from_service_account_file('your_credentials.json', scopes=['https://www.googleapis.com/auth/spreadsheets'])
    gc = gspread.authorize(credentials)

    # Replace 'Your Spreadsheet Name' with the name of your Google Sheets spreadsheet
    spreadsheet_name = 'Your Spreadsheet Name'
    
    try:
        # Open the Google Sheets spreadsheet
        spreadsheet = gc.open(spreadsheet_name)
        
        # Replace 'Your Worksheet Name' with the name of your worksheet
        worksheet_name = 'Your Worksheet Name'

        # Select the worksheet
        worksheet = spreadsheet.worksheet(worksheet_name)

        # Append a new row with the provided data
        new_row = [team, topic, chat_link, summary]
        worksheet.append_row(new_row)

        print("Data added to Google Sheets successfully.")
    except Exception as e:
        print(f"Error adding data to Google Sheets: {str(e)}")

def create_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS MessageStore (
            Team TEXT,
            Topic TEXT,
            ChatLink TEXT,
            Summary TEXT
        )
    ''')
    conn.commit()
    conn.close()


# Create a new message
@app.route('/messages', methods=['POST'])
def create_message():
    data = request.json
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO MessageStore (Team, Topic, ChatLink, Summary)
            VALUES (?, ?, ?, ?)
        ''', (data['team'], data['topic'], data['chat_link'], data['summary']))
        conn.commit()
        conn.close()
        return jsonify({"message": "Message created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get all messages
@app.route('/messages', methods=['GET'])
def get_messages():
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM MessageStore')
        messages = cursor.fetchall()
        conn.close()
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get a specific message by ID
@app.route('/messages/<int:message_id>', methods=['GET'])
def get_message(message_id):
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM MessageStore WHERE rowid = ?', (message_id,))
        message = cursor.fetchone()
        conn.close()
        if message:
            return jsonify({"message": message})
        else:
            return jsonify({"error": "Message not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Update a message by ID
@app.route('/messages/<int:message_id>', methods=['PUT'])
def update_message(message_id):
    data = request.json
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE MessageStore
            SET Team = ?, Topic = ?, ChatLink = ?, Summary = ?
            WHERE rowid = ?
        ''', (data['team'], data['topic'], data['chat_link'], data['summary'], message_id))
        conn.commit()
        conn.close()
        return jsonify({"message": "Message updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Delete a message by ID
@app.route('/messages/<int:message_id>', methods=['DELETE'])
def delete_message(message_id):
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM MessageStore WHERE rowid = ?', (message_id,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Message deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def make_post_request(url, headers, params):
    try:
        # Make the HTTP POST request
        response = requests.post(url, headers=headers, params=params)

        # Print the request details
        print(f"Request URL: {response.request.url}")
        print(f"Request Headers: {response.request.headers}")
        print(f"Request Body: {response.request.body}")

        # Print the response details
        print(f"Response Status Code: {response.status_code}")
        print(f"Response Headers: {response.headers}")
        print(f"Response Content: {response.text}")

    except requests.RequestException as e:
        print(f"Error making HTTP POST request: {e}")

# Example usage
url = "https://example.com/api/endpoint"
auth_headers = {"Authorization": "Bearer YOUR_ACCESS_TOKEN"}
request_params = {"param1": "value1", "param2": "value2"}

make_post_request(url, headers=auth_headers, params=request_params)


#knowledgeCrow create personal gsheetlink
#knowledgeCrow create team teamId gsheetlink
#knowledgeCrow get personal
#knowledgeCrow get team teamId
#knowledgeCrow delete personal
#knowledgeCrow delete team teamId

async def async_function():
    print("Async function started")
    await asyncio.sleep(2)  # Simulate an asynchronous task (e.g., I/O operation)
    print("Async function completed")

asyncio.run(async_function())

# Run the Flask app
if __name__ == "__main__":
    app.run(port=3000, debug=True)

# curl --location 'hackdaylink' \
# --header 'Content-Type: application/json' \
# --header 'Ocp-Apim-Subscription-Key: apikey' \
# --data ' 
# {
#   "displayName": "Conversation Task Example",
#   "analysisInput": {
#     "conversations": [
#       {
#         "conversationItems": [
#           {
#             "text": "Hello, you’re chatting with Rene. How may I help you?",
#             "id": "1",
#             "role": "Agent",
#             "participantId": "Agent_1"
#           },
#           {
#             "text": "Hi, I tried to set up wifi connection for Smart Brew 300 espresso machine, but it didn’t work.",
#             "id": "2",
#             "role": "Customer",
#             "participantId": "Customer_1"
#           },
#           {
#             "text": "I’m sorry to hear that. Let’s see what we can do to fix this issue. Could you please try the following steps for me? First, could you push the wifi connection button, hold for 3 seconds, then let me know if the power light is slowly blinking on and off every second?",
#             "id": "3",
#             "role": "Agent",
#             "participantId": "Agent_1"
#           },
#           {
#             "text": "Yes, I pushed the wifi connection button, and now the power light is slowly blinking.",
#             "id": "4",
#             "role": "Customer",
#             "participantId": "Customer_1"
#           },
#           {
#             "text": "Great. Thank you! Now, please check in your Contoso Coffee app. Does it prompt to ask you to connect with the machine? ",
#             "id": "5",
#             "role": "Agent",
#             "participantId": "Agent_1"
#           },
#           {
#             "text": "No. Nothing happened.",
#             "id": "6",
#             "role": "Customer",
#             "participantId": "Customer_1"
#           },
#           {
#             "text": "I’m very sorry to hear that. Let me see if there’s another way to fix the issue. Please hold on for a minute.",
#             "id": "7",
#             "role": "Agent",
#             "participantId": "Agent_1"
#           }
#         ],
#         "modality": "text",
#         "id": "conversation1",
#         "language": "en"
#       }
#     ]
#   },
#   "tasks": [
#     {
#       "taskName": "Conversation Task 1",
#       "kind": "ConversationalSummarizationTask",
#       "parameters": {
#         "summaryAspects": ["issue"]
#       }
#     },
#     {
#       "taskName": "Conversation Task 2",
#       "kind": "ConversationalSummarizationTask",
#       "parameters": {
#         "summaryAspects": ["resolution"],
#         "sentenceCount": 1
#       }
#     }
#   ]
# }
# '

